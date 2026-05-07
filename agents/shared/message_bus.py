"""Redis Streams message bus — fan-out to all agent consumer groups."""
import asyncio
import logging
from typing import Callable

import redis.asyncio as aioredis

from .protocols import AgentID, AtlasMessage

logger = logging.getLogger(__name__)

STREAM_KEY = "atlas:events"
CONSUMER_GROUPS = [agent.value for agent in AgentID if agent not in (AgentID.SYSTEM, AgentID.USER)]


class MessageBus:
    def __init__(self, redis_url: str):
        self._url = redis_url
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self._url, decode_responses=True)
        await self._ensure_groups()

    async def _ensure_groups(self) -> None:
        for group in CONSUMER_GROUPS:
            try:
                await self._redis.xgroup_create(STREAM_KEY, group, id="0", mkstream=True)
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def publish(self, msg: AtlasMessage) -> str:
        data = {
            "json": msg.model_dump_json(),
            "type": msg.message_type.value,
            "source": msg.source_agent.value,
            "target": msg.target_agent.value if msg.target_agent else "",
            "priority": str(msg.priority),
        }
        msg_id = await self._redis.xadd(STREAM_KEY, data, maxlen=10000, approximate=True)
        return msg_id

    async def consume(
        self,
        agent_id: AgentID,
        handler: Callable[[AtlasMessage], None],
        batch_size: int = 10,
    ) -> None:
        group = agent_id.value
        consumer = f"{group}-consumer"
        while True:
            try:
                results = await self._redis.xreadgroup(
                    group, consumer, {STREAM_KEY: ">"}, count=batch_size, block=1000
                )
                if results:
                    for _, messages in results:
                        for msg_id, fields in messages:
                            try:
                                msg = AtlasMessage.model_validate_json(fields["json"])
                                if msg.target_agent is None or msg.target_agent == agent_id:
                                    await handler(msg)
                                await self._redis.xack(STREAM_KEY, group, msg_id)
                            except Exception as e:
                                logger.error("Error processing message %s: %s", msg_id, e)
                                await self._redis.xack(STREAM_KEY, group, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Bus consume error: %s", e)
                await asyncio.sleep(2)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
