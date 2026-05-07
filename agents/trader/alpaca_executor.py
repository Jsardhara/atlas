"""Trader Alpaca execution layer — places and monitors orders.

Public methods: ``size_position``, ``execute_trade``, ``close_trade``.
DB column ``broker_order_id`` is broker-agnostic.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from shared.alpaca_client import AlpacaClient
from shared.config import Settings
from shared.db import get_session

logger = logging.getLogger(__name__)


SHORT_MIN_LEVERAGE = 2
LONG_CASH_LEVERAGE = 1


def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float) -> float:
    if avg_win <= 0 or avg_loss <= 0:
        return 0.02
    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    return max(0.005, min(kelly, 0.05))


def _resolve_side_and_leverage(
    direction: str,
    requested_leverage: int,
    max_leverage: int,
) -> tuple[str, int]:
    """LONG → buy, SHORT → sell. Alpaca handles margin server-side.

    Leverage is informational on Alpaca (margin is tied to the account, not
    the order), but Guardian still enforces caps so we keep the same value
    flowing through the Trade record.
    """
    direction = (direction or "").upper()
    if direction == "SHORT":
        leverage = max(SHORT_MIN_LEVERAGE, requested_leverage)
        return "sell", min(leverage, max_leverage)
    if direction == "LONG":
        if requested_leverage <= 1:
            return "buy", LONG_CASH_LEVERAGE
        return "buy", min(requested_leverage, max_leverage)
    raise ValueError(f"Unsupported direction: {direction!r}")


class AlpacaExecutor:
    def __init__(self, alpaca: AlpacaClient, settings: Settings):
        self.alpaca = alpaca
        self.settings = settings

    async def size_position(self, signal: dict) -> dict:
        """Kelly + confidence-based leverage."""
        async with get_session() as sess:
            snap = await sess.execute(text(
                "SELECT total_usd FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
            ))
            row = snap.fetchone()
            portfolio_usd = float(row[0]) if row else 1000.0

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

        confidence = signal.get("confidence", 0.6)
        direction = (signal.get("direction") or "").upper()
        if confidence >= 0.8:
            requested = min(3, self.settings.max_leverage)
        elif confidence >= 0.7:
            requested = min(2, self.settings.max_leverage)
        else:
            requested = 1
        if direction == "SHORT":
            requested = max(requested, SHORT_MIN_LEVERAGE)
        if "leverage" in signal:
            try:
                requested = max(requested, int(signal["leverage"]))
            except (TypeError, ValueError):
                pass
        requested = min(requested, self.settings.max_leverage)

        return {
            "size_usd": round(size_usd, 2),
            "leverage": requested,
            "portfolio_usd": portfolio_usd,
            "kelly_fraction": round(fraction, 4),
        }

    async def execute_trade(
        self,
        signal: dict,
        sizing: dict,
        shortable_set: set[str] | None = None,
    ) -> dict:
        pair = signal["pair"]
        direction = (signal.get("direction") or "").upper()

        if direction == "SHORT" and shortable_set is not None:
            altname = pair.replace("/", "")
            if altname not in shortable_set and pair not in shortable_set:
                return {
                    "error": f"SHORT rejected: {pair} not in shortable set",
                    "rejected": True,
                }

        side, effective_leverage = _resolve_side_and_leverage(
            direction,
            sizing.get("leverage", 1),
            self.settings.max_leverage,
        )
        sizing = {**sizing, "leverage": effective_leverage}

        ticker = await self.alpaca.get_ticker(pair)
        try:
            current_price = float(ticker.get("c", [signal.get("entry_price", 1)])[0])
        except (IndexError, TypeError):
            current_price = float(signal.get("entry_price") or 1.0)
        volume = sizing["size_usd"] / current_price if current_price else 0.001

        order_result = await self.alpaca.place_order(
            pair=pair,
            side=side,
            order_type="limit" if signal.get("entry_price") else "market",
            volume=round(volume, 6),
            price=signal.get("entry_price"),
            leverage=sizing["leverage"],
            validate=not self.settings.live_trading_enabled,
        )

        trade_id = str(uuid.uuid4())
        is_paper = not self.settings.live_trading_enabled or self.settings.alpaca_paper
        broker_id = (
            order_result.get("txid", [trade_id])[0]
            if isinstance(order_result.get("txid"), list)
            else order_result.get("txid", trade_id)
        )

        async with get_session() as sess:
            await sess.execute(text("""
                INSERT INTO trades (id, signal_id, broker_order_id, pair, side, order_type,
                                    leverage, requested_size, filled_size, entry_price,
                                    stop_loss, take_profit, status, is_paper,
                                    guardian_approved, opened_at)
                VALUES (:id, CAST(:signal_id AS uuid), :broker_id, :pair, :side, :order_type,
                        :leverage, :size, :filled, :entry, :sl, :tp,
                        'open', :paper, true, now())
            """), {
                "id": trade_id,
                "signal_id": signal.get("signal_id"),
                "broker_id": broker_id,
                "pair": pair,
                "side": side,
                "order_type": "limit" if signal.get("entry_price") else "market",
                "leverage": sizing["leverage"],
                "size": sizing["size_usd"],
                "filled": round(volume, 6),
                "entry": signal.get("entry_price") or current_price,
                "sl": signal.get("stop_loss"),
                "tp": signal.get("take_profit"),
                "paper": is_paper,
            })
            await sess.commit()

        logger.info(
            "[Trader] Trade %s placed: %s %s %s vol=%.6f leverage=%dx paper=%s",
            trade_id, side, pair, "PAPER" if is_paper else "LIVE",
            volume, sizing["leverage"], is_paper,
        )

        return {
            "trade_id": trade_id,
            "broker_order_id": broker_id,
            "pair": pair,
            "side": side,
            "size_usd": sizing["size_usd"],
            "leverage": sizing["leverage"],
            "is_paper": is_paper,
            "order_result": order_result,
        }

    async def close_trade(self, trade_id: str) -> dict:
        async with get_session() as sess:
            row = await sess.execute(text(
                "SELECT pair, side, filled_size, requested_size, entry_price "
                "FROM trades WHERE id = :id"
            ), {"id": trade_id})
            trade = row.fetchone()
            if not trade:
                return {"error": "Trade not found"}

        entry = float(trade.entry_price or 1)
        if trade.filled_size:
            volume = float(trade.filled_size)
        elif trade.requested_size and entry:
            volume = float(trade.requested_size) / entry
        else:
            volume = 0.001

        close_side = "sell" if trade.side == "buy" else "buy"
        await self.alpaca.place_order(
            pair=trade.pair,
            side=close_side,
            order_type="market",
            volume=round(volume, 6),
            validate=not self.settings.live_trading_enabled,
        )

        async with get_session() as sess:
            ticker = await self.alpaca.get_ticker(trade.pair)
            try:
                exit_price = float(ticker.get("c", [entry])[0])
            except (IndexError, TypeError):
                exit_price = entry
            pnl_pct = (
                (exit_price - entry) / entry
                if trade.side == "buy"
                else (entry - exit_price) / entry
            )
            pnl_usd = pnl_pct * volume * entry

            await sess.execute(text("""
                UPDATE trades
                SET status = 'closed', exit_price = :exit, pnl_usd = :pnl_usd,
                    pnl_pct = :pnl_pct, closed_at = now(), close_reason = 'manual'
                WHERE id = :id
            """), {
                "exit": exit_price,
                "pnl_usd": round(pnl_usd, 4),
                "pnl_pct": round(pnl_pct, 6),
                "id": trade_id,
            })
            await sess.commit()

        return {"trade_id": trade_id, "status": "closed", "exit_price": exit_price}
