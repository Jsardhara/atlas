"""Trader Kraken execution layer — places and monitors orders."""
import logging
import uuid
from datetime import datetime

from sqlalchemy import text

from shared.config import Settings
from shared.db import get_session
from shared.kraken_client import KrakenClient

logger = logging.getLogger(__name__)


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    if avg_win <= 0 or avg_loss <= 0:
        return 0.02
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    return max(0.005, min(kelly, 0.05))  # cap at 5% of portfolio


class KrakenExecutor:
    def __init__(self, kraken: KrakenClient, settings: Settings):
        self.kraken = kraken
        self.settings = settings

    async def size_position(self, signal: dict) -> dict:
        """Calculate position size using Kelly criterion + risk limits."""
        async with get_session() as sess:
            # Get portfolio size
            snap = await sess.execute(text(
                "SELECT total_usd FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
            ))
            row = snap.fetchone()
            portfolio_usd = float(row[0]) if row else 1000.0

            # Get recent win stats
            stats = await sess.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE pnl_usd > 0)::float / NULLIF(COUNT(*), 0) as win_rate,
                    ABS(AVG(pnl_pct) FILTER (WHERE pnl_usd > 0)) as avg_win,
                    ABS(AVG(pnl_pct) FILTER (WHERE pnl_usd < 0)) as avg_loss
                FROM trades WHERE status = 'closed' AND closed_at >= now() - interval '30 days'
            """))
            s = stats.fetchone()
            wr = float(s[0] or 0.5)
            aw = float(s[1] or 0.02)
            al = float(s[2] or 0.02)

        fraction = kelly_fraction(wr, aw, al)
        size_usd = portfolio_usd * fraction

        # Determine leverage based on confidence
        confidence = signal.get("confidence", 0.6)
        leverage = 1
        if confidence >= 0.8:
            leverage = min(3, self.settings.max_leverage)
        elif confidence >= 0.7:
            leverage = min(2, self.settings.max_leverage)

        return {
            "size_usd": round(size_usd, 2),
            "leverage": leverage,
            "portfolio_usd": portfolio_usd,
            "kelly_fraction": round(fraction, 4),
        }

    async def execute_trade(self, signal: dict, sizing: dict) -> dict:
        pair = signal["pair"]
        direction = signal["direction"]
        side = "buy" if direction == "LONG" else "sell"

        # Convert USD size to base currency volume
        ticker = await self.kraken.get_ticker(pair.replace("/", ""))
        current_price = float(ticker.get("c", [signal.get("entry_price", 1)])[0]) if ticker else signal.get("entry_price", 1)
        volume = sizing["size_usd"] / current_price if current_price else 0.001

        order_result = await self.kraken.place_order(
            pair=pair.replace("/", ""),
            side=side,
            order_type="limit" if signal.get("entry_price") else "market",
            volume=round(volume, 6),
            price=signal.get("entry_price"),
            leverage=sizing["leverage"],
            validate=not self.settings.live_trading_enabled,
        )

        # Persist trade to DB
        trade_id = str(uuid.uuid4())
        is_paper = not self.settings.live_trading_enabled
        kraken_id = order_result.get("txid", [trade_id])[0] if isinstance(
            order_result.get("txid"), list) else order_result.get("txid", trade_id)

        async with get_session() as sess:
            await sess.execute(text("""
                INSERT INTO trades (id, signal_id, kraken_order_id, pair, side, order_type,
                                    leverage, requested_size, entry_price, stop_loss, take_profit,
                                    status, is_paper, guardian_approved, opened_at)
                VALUES (:id, :signal_id::uuid, :kraken_id, :pair, :side, :order_type,
                        :leverage, :size, :entry, :sl, :tp,
                        'open', :paper, true, now())
            """), {
                "id": trade_id,
                "signal_id": signal.get("signal_id"),
                "kraken_id": kraken_id,
                "pair": pair,
                "side": side,
                "order_type": "limit" if signal.get("entry_price") else "market",
                "leverage": sizing["leverage"],
                "size": sizing["size_usd"],
                "entry": signal.get("entry_price") or current_price,
                "sl": signal.get("stop_loss"),
                "tp": signal.get("take_profit"),
                "paper": is_paper,
            })
            await sess.commit()

        logger.info("[Trader] Trade %s placed: %s %s %s vol=%.6f leverage=%dx paper=%s",
                    trade_id, side, pair, "PAPER" if is_paper else "LIVE",
                    volume, sizing["leverage"], is_paper)

        return {"trade_id": trade_id, "kraken_order_id": kraken_id,
                "pair": pair, "side": side, "size_usd": sizing["size_usd"],
                "leverage": sizing["leverage"], "is_paper": is_paper,
                "order_result": order_result}

    async def close_trade(self, trade_id: str) -> dict:
        async with get_session() as sess:
            row = await sess.execute(text(
                "SELECT pair, side, filled_size, entry_price FROM trades WHERE id = :id"
            ), {"id": trade_id})
            trade = row.fetchone()
            if not trade:
                return {"error": "Trade not found"}

        close_side = "sell" if trade.side == "buy" else "buy"
        result = await self.kraken.place_order(
            pair=trade.pair.replace("/", ""),
            side=close_side,
            order_type="market",
            volume=float(trade.filled_size or 0.001),
            validate=not self.settings.live_trading_enabled,
        )

        # Update trade in DB
        async with get_session() as sess:
            ticker = await self.kraken.get_ticker(trade.pair.replace("/", ""))
            exit_price = float(ticker.get("c", [trade.entry_price])[0]) if ticker else float(trade.entry_price or 0)
            entry = float(trade.entry_price or exit_price)
            pnl_pct = (exit_price - entry) / entry if trade.side == "buy" else (entry - exit_price) / entry
            pnl_usd = pnl_pct * float(trade.filled_size or 0.001) * entry

            await sess.execute(text("""
                UPDATE trades
                SET status = 'closed', exit_price = :exit, pnl_usd = :pnl_usd,
                    pnl_pct = :pnl_pct, closed_at = now(), close_reason = 'manual'
                WHERE id = :id
            """), {"exit": exit_price, "pnl_usd": round(pnl_usd, 4),
                   "pnl_pct": round(pnl_pct, 6), "id": trade_id})
            await sess.commit()

        return {"trade_id": trade_id, "status": "closed", "exit_price": exit_price}
