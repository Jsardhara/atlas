"""Commander alert manager — creates DB alerts and publishes to the dashboard."""
import json
import logging
from datetime import datetime

from sqlalchemy import text

from shared.db import get_session
from shared.message_bus import MessageBus
from shared.protocols import AgentID, AtlasMessage, MessageType

logger = logging.getLogger(__name__)


class AlertManager:
    def __init__(self, bus: MessageBus):
        self.bus = bus

    async def create_alert(
        self,
        title: str,
        message: str,
        severity: str = "warning",  # info | warning | critical
        auto_action: str | None = None,
        countdown_secs: int = 30,
    ) -> str:
        async with get_session() as sess:
            row = await sess.execute(text("""
                INSERT INTO alerts (severity, title, message, auto_action, countdown_secs)
                VALUES (:sev, :title, :msg, :action, :countdown)
                RETURNING id
            """), {
                "sev": severity,
                "title": title,
                "msg": message,
                "action": auto_action,
                "countdown": countdown_secs,
            })
            alert_id = str(row.fetchone()[0])
            await sess.commit()

        # Broadcast to dashboard via bus
        await self.bus.publish(AtlasMessage(
            source_agent=AgentID.COMMANDER,
            message_type=MessageType.ALERT_CREATED,
            payload={
                "alert_id": alert_id,
                "severity": severity,
                "title": title,
                "message": message,
                "auto_action": auto_action,
                "countdown_secs": countdown_secs,
            },
            priority=5 if severity == "critical" else 4,
        ))
        logger.warning("[Commander] Alert created: %s — %s", severity.upper(), title)
        return alert_id

    async def resolve_alert(self, alert_id: str, resolution: str = "actioned") -> None:
        async with get_session() as sess:
            await sess.execute(text("""
                UPDATE alerts SET status = :res, resolved_at = now() WHERE id = :id
            """), {"res": resolution, "id": alert_id})
            await sess.commit()

        await self.bus.publish(AtlasMessage(
            source_agent=AgentID.COMMANDER,
            message_type=MessageType.ALERT_RESOLVED,
            payload={"alert_id": alert_id, "resolution": resolution},
        ))
