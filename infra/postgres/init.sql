-- =============================================================================
-- ATLAS Database Schema
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Append-only event log (source of truth for all agent activity)
-- ---------------------------------------------------------------------------
CREATE TABLE events (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source         TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    payload        JSONB NOT NULL DEFAULT '{}',
    correlation_id UUID
);
CREATE INDEX events_type_time ON events(event_type, occurred_at DESC);
CREATE INDEX events_source_time ON events(source, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- Agent registry and state
-- ---------------------------------------------------------------------------
CREATE TABLE agents (
    id              TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    model           TEXT NOT NULL,
    personality     TEXT,
    state           TEXT NOT NULL DEFAULT 'running',
    config          JSONB NOT NULL DEFAULT '{}',
    last_heartbeat  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now()
);

INSERT INTO agents (id, display_name, model, personality) VALUES
  ('oracle',    'Oracle',    'claude-sonnet-4-6', 'Sharp, unemotional market analyst. Speaks in structured numbered points. Never hedges — uses confidence scores.'),
  ('guardian',  'Guardian',  'claude-haiku-4-5',  'Risk-obsessed, skeptical validator. Lists risks first. Only approves trades that survive rigorous scrutiny.'),
  ('trader',    'Trader',    'claude-sonnet-4-6', 'Cold and precise executor. Never second-guesses approved trades. Focuses on optimal order placement.'),
  ('sage',      'Sage',      'claude-haiku-4-5',  'Philosophical and methodical performance analyst. Looks for deep patterns. Speaks in paragraphs.'),
  ('architect', 'Architect', 'claude-opus-4-7',   'Creative but rigorous strategy designer. Draws on academic research and quantitative finance. Writes complete working code.');

-- ---------------------------------------------------------------------------
-- LLM call audit log (cost tracking parity with Jarvis).
-- DDL kept in sync with agents/shared/claude_client._LLM_CALLS_DDL.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_calls (
    id                 UUID PRIMARY KEY,
    ts                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    agent_id           TEXT NOT NULL,
    model              TEXT NOT NULL,
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd_estimate  NUMERIC(12, 6) NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS llm_calls_agent_ts ON llm_calls(agent_id, ts DESC);
CREATE INDEX IF NOT EXISTS llm_calls_ts ON llm_calls(ts DESC);

-- ---------------------------------------------------------------------------
-- Agent persistent memory (key-value per agent, cross-agent context sharing)
-- ---------------------------------------------------------------------------
CREATE TABLE agent_memory (
    agent_id    TEXT NOT NULL REFERENCES agents(id),
    memory_key  TEXT NOT NULL,
    value       JSONB NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (agent_id, memory_key)
);

-- ---------------------------------------------------------------------------
-- Dashboard alerts (from Commander hybrid mode)
-- ---------------------------------------------------------------------------
CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ DEFAULT now(),
    severity        TEXT NOT NULL DEFAULT 'info',  -- info|warning|critical
    title           TEXT NOT NULL,
    message         TEXT NOT NULL,
    agent_id        TEXT REFERENCES agents(id),
    auto_action     TEXT,                           -- what Commander will do after countdown
    countdown_secs  INTEGER DEFAULT 30,
    status          TEXT DEFAULT 'pending',         -- pending|actioned|overridden|expired
    resolved_at     TIMESTAMPTZ
);
CREATE INDEX alerts_status ON alerts(status, created_at DESC);

-- ---------------------------------------------------------------------------
-- Market signals from Oracle
-- ---------------------------------------------------------------------------
CREATE TABLE signals (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ DEFAULT now(),
    pair             TEXT NOT NULL,
    direction        TEXT NOT NULL,     -- LONG | SHORT | NEUTRAL
    confidence       NUMERIC(4,3),
    reasoning        TEXT,
    entry_price      NUMERIC,
    stop_loss        NUMERIC,
    take_profit      NUMERIC,
    status           TEXT DEFAULT 'pending',  -- pending|approved|rejected|modified|expired
    guardian_notes   TEXT,
    modified_params  JSONB,
    freqtrade_signal JSONB
);
CREATE INDEX signals_pair_status ON signals(pair, status, created_at DESC);

-- ---------------------------------------------------------------------------
-- Full trade lifecycle
-- ---------------------------------------------------------------------------
CREATE TABLE trades (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_id         UUID REFERENCES signals(id),
    broker_order_id   TEXT UNIQUE,
    pair              TEXT NOT NULL,
    side              TEXT NOT NULL,        -- buy | sell
    order_type        TEXT NOT NULL,        -- market | limit
    leverage          NUMERIC DEFAULT 1,
    requested_size    NUMERIC NOT NULL,
    filled_size       NUMERIC,
    entry_price       NUMERIC,
    exit_price        NUMERIC,
    stop_loss         NUMERIC,
    take_profit       NUMERIC,
    status            TEXT NOT NULL DEFAULT 'pending',  -- pending|open|closed|cancelled|error
    pnl_usd           NUMERIC,
    pnl_pct           NUMERIC,
    fees_usd          NUMERIC,
    opened_at         TIMESTAMPTZ,
    closed_at         TIMESTAMPTZ,
    close_reason      TEXT,
    is_paper          BOOLEAN NOT NULL DEFAULT true,
    guardian_approved BOOLEAN,
    agent_notes       JSONB DEFAULT '{}'
);
CREATE INDEX trades_status_time ON trades(status, opened_at DESC);
CREATE INDEX trades_pair ON trades(pair);
CREATE INDEX trades_paper ON trades(is_paper, status);

-- ---------------------------------------------------------------------------
-- Strategy repository
-- ---------------------------------------------------------------------------
CREATE TABLE strategies (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL UNIQUE,
    version             INTEGER DEFAULT 1,
    code                TEXT NOT NULL,
    status              TEXT DEFAULT 'proposed',  -- proposed|testing|active|archived
    author              TEXT DEFAULT 'architect',
    backtest_results    JSONB,
    performance_metrics JSONB,
    created_at          TIMESTAMPTZ DEFAULT now(),
    activated_at        TIMESTAMPTZ,
    proposed_by         TEXT
);

-- ---------------------------------------------------------------------------
-- Backtest runs
-- ---------------------------------------------------------------------------
CREATE TABLE backtests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    strategy_id     UUID REFERENCES strategies(id),
    triggered_by    TEXT,
    timerange       TEXT NOT NULL,
    config_snapshot JSONB,
    status          TEXT DEFAULT 'running',  -- running|completed|failed
    results         JSONB,
    sharpe_ratio    NUMERIC,
    max_drawdown    NUMERIC,
    total_return    NUMERIC,
    win_rate        NUMERIC,
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ
);

-- ---------------------------------------------------------------------------
-- Agent chat history (individual agent pages + master terminal)
-- ---------------------------------------------------------------------------
CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL,
    role        TEXT NOT NULL,   -- user | assistant
    agent_id    TEXT REFERENCES agents(id),
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX chat_session ON chat_messages(session_id, created_at);

-- ---------------------------------------------------------------------------
-- Portfolio snapshots (time-series for equity curve)
-- ---------------------------------------------------------------------------
CREATE TABLE portfolio_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_at     TIMESTAMPTZ DEFAULT now(),
    total_usd       NUMERIC NOT NULL,
    available_usd   NUMERIC NOT NULL,
    open_positions  JSONB NOT NULL DEFAULT '[]',
    realized_pnl    NUMERIC DEFAULT 0,
    unrealized_pnl  NUMERIC DEFAULT 0,
    is_paper        BOOLEAN NOT NULL DEFAULT true
);
CREATE INDEX portfolio_time ON portfolio_snapshots(snapshot_at DESC);

-- ---------------------------------------------------------------------------
-- Paper trading readiness tracker
-- ---------------------------------------------------------------------------
CREATE TABLE paper_trading_stats (
    id                  SERIAL PRIMARY KEY,
    updated_at          TIMESTAMPTZ DEFAULT now(),
    total_trades        INTEGER DEFAULT 0,
    days_active         INTEGER DEFAULT 0,
    win_rate_30         NUMERIC DEFAULT 0,    -- win rate over last 30 trades
    total_pnl_pct       NUMERIC DEFAULT 0,    -- total P&L as % of starting portfolio
    max_drawdown_pct    NUMERIC DEFAULT 0,
    live_trading_ready  BOOLEAN DEFAULT false
);
INSERT INTO paper_trading_stats DEFAULT VALUES;
