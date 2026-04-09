from enum import Enum
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
import uuid


class AgentID(str, Enum):
    COMMANDER = "commander"
    ORACLE = "oracle"
    GUARDIAN = "guardian"
    TRADER = "trader"
    SAGE = "sage"
    ARCHITECT = "architect"
    SYSTEM = "system"
    USER = "user"


class MessageType(str, Enum):
    # Heartbeat / status
    HEARTBEAT = "heartbeat"
    AGENT_STATUS = "agent_status"

    # Oracle outputs
    MARKET_SIGNAL = "market_signal"
    RESEARCH_UPDATE = "research_update"

    # Guardian outputs
    TRADE_APPROVED = "trade_approved"
    TRADE_REJECTED = "trade_rejected"
    TRADE_MODIFIED = "trade_modified"

    # Trader outputs
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"

    # Sage outputs
    LEARNING_INSIGHT = "learning_insight"
    PERFORMANCE_REPORT = "performance_report"

    # Architect outputs
    STRATEGY_PROPOSED = "strategy_proposed"
    BACKTEST_STARTED = "backtest_started"
    BACKTEST_COMPLETE = "backtest_complete"

    # Commander outputs
    AGENT_COMMAND = "agent_command"       # pause/resume/configure another agent
    ALERT_CREATED = "alert_created"
    ALERT_RESOLVED = "alert_resolved"
    PIPELINE_DECISION = "pipeline_decision"  # advance/block a signal

    # User / system
    USER_COMMAND = "user_command"
    CHAT_MESSAGE = "chat_message"
    CHAT_RESPONSE = "chat_response"
    SYSTEM_EVENT = "system_event"


class AgentCommand(str, Enum):
    PAUSE = "pause"
    RESUME = "resume"
    CONFIGURE = "configure"
    RESTART = "restart"


class AgentState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STARTING = "starting"


class AtlasMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_agent: AgentID
    target_agent: AgentID | None = None   # None = broadcast
    message_type: MessageType
    payload: dict[str, Any] = Field(default_factory=dict)
    correlation_id: str | None = None
    priority: int = Field(default=3, ge=1, le=5)  # 5 = critical


class MarketSignal(BaseModel):
    signal_id: str
    pair: str
    direction: str          # LONG | SHORT | NEUTRAL
    confidence: float       # 0.0 – 1.0
    reasoning: str
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    timeframe: str = "5m"
    sources: list[str] = Field(default_factory=list)


class TradeDecision(BaseModel):
    signal_id: str
    approved: bool
    reasoning: str
    modified_params: dict[str, Any] | None = None
    risk_score: int = Field(ge=1, le=10)


class OrderParams(BaseModel):
    trade_id: str
    pair: str
    side: str               # buy | sell
    order_type: str         # market | limit
    size_usd: float
    leverage: int = 1
    limit_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
