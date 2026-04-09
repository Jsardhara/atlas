"""Hard rule validators — no LLM, pure logic."""
from dataclasses import dataclass

from sqlalchemy import text

from shared.db import get_session


@dataclass
class ValidationResult:
    passed: bool
    reason: str


async def validate_hard_rules(signal: dict, settings) -> ValidationResult:
    pair = signal.get("pair", "")
    confidence = signal.get("confidence", 0)

    # Min confidence check
    if confidence < 0.6:
        return ValidationResult(False, f"Confidence {confidence:.2f} below minimum 0.60")

    async with get_session() as sess:
        # Max open trades
        count_row = await sess.execute(text(
            "SELECT COUNT(*) FROM trades WHERE status = 'open'"
        ))
        open_count = count_row.scalar()
        if open_count >= 3:
            return ValidationResult(False, f"Max open trades reached ({open_count}/3)")

        # Duplicate pair
        dup = await sess.execute(text(
            "SELECT id FROM trades WHERE pair = :pair AND status = 'open' LIMIT 1"
        ), {"pair": pair})
        if dup.fetchone():
            return ValidationResult(False, f"Already have open position in {pair}")

        # Daily loss circuit breaker
        loss_row = await sess.execute(text("""
            SELECT COALESCE(SUM(ABS(pnl_usd)), 0)
            FROM trades WHERE pnl_usd < 0 AND closed_at >= CURRENT_DATE
        """))
        daily_loss = float(loss_row.scalar())
        if daily_loss >= settings.daily_loss_limit_usd:
            return ValidationResult(False, f"Daily loss limit hit (${daily_loss:.2f})")

        # Portfolio risk check
        portfolio_row = await sess.execute(text(
            "SELECT total_usd FROM portfolio_snapshots ORDER BY snapshot_at DESC LIMIT 1"
        ))
        portfolio_row = portfolio_row.fetchone()
        if portfolio_row:
            total = float(portfolio_row[0])
            entry = signal.get("entry_price", 0)
            stop = signal.get("stop_loss", 0)
            if entry and stop:
                risk_pct = abs(entry - stop) / entry
                if risk_pct > settings.max_portfolio_risk_pct:
                    return ValidationResult(False,
                        f"Risk per trade {risk_pct:.1%} exceeds max {settings.max_portfolio_risk_pct:.1%}")

    return ValidationResult(True, "All hard rules passed")
