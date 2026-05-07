# ATLAS — Autonomous Trading & Learning Agent System

A multi-agent AI trading system that researches markets, validates risk, executes trades, and learns from outcomes — all orchestrated through a real-time dashboard.

> **Default mode: Paper trading (LIVE_TRADING_ENABLED=false)**  
> No real money moves until you explicitly flip that flag.

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Dashboard (Next.js)            │
│              Real-time charts & terminal         │
└───────────────────┬─────────────────────────────┘
                    │ WebSocket / REST
┌───────────────────▼─────────────────────────────┐
│                 FastAPI Backend                  │
│          REST API + WebSocket gateway            │
└──┬──────────┬──────────┬──────────┬─────────────┘
   │          │          │          │
┌──▼──┐  ┌───▼──┐  ┌────▼──┐  ┌───▼────┐  ┌──────┐
│Oracle│  │Guard-│  │Trader │  │  Sage  │  │Archi-│
│      │  │ ian  │  │       │  │(learns)│  │ tect │
└──────┘  └──────┘  └───────┘  └────────┘  └──────┘
        All agents report to → Commander
                    │
          ┌─────────▼────────┐
          │    Freqtrade      │  ← strategy engine
          │    (FreqAI)       │
          └─────────┬────────┘
                    │
              Alpaca Brokerage
```

### Agents

| Agent | Role |
|-------|------|
| **Commander** | Orchestrates all agents; enforces circuit breakers and escalation rules |
| **Oracle** | Researches news, sentiment, and on-chain signals every 15 minutes |
| **Guardian** | Hard-rule risk validator — blocks any trade that violates limits |
| **Trader** | Executes orders on Alpaca using Kelly criterion position sizing |
| **Sage** | Analyzes trade patterns and feeds learnings back to the system |
| **Architect** | Generates and backtests new strategies using Freqtrade/FreqAI |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Compose v2)
- [Git](https://git-scm.com/)
- An [Alpaca](https://alpaca.markets/) account (free paper-trading account works)
- An [OpenRouter](https://openrouter.ai/) API key (free tier works)

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/Jsardhara/atlas.git
cd atlas
```

### 2. Configure your environment

Create `.env` at the repo root and fill in:

```env
OPENROUTER_API_KEY=sk-or-...       # from openrouter.ai — free models work
ALPACA_API_KEY=PK...               # from app.alpaca.markets > Profile > API Keys
ALPACA_SECRET_KEY=...
ALPACA_PAPER=true                  # keep true to paper-trade only
ALPACA_DATA_FEED=iex               # iex (free) | sip (paid)
```

Run `python scripts/gen_secrets.py` to fill the four random secrets
(POSTGRES_PASSWORD, JWT_SECRET_KEY, API_ADMIN_PASSWORD, ATLAS_BEARER_TOKEN).

Everything else has safe defaults. Change passwords before exposing to the internet.

### 3. Start the system

```bash
docker compose up --build -d
```

First run takes ~5 minutes to build all images. After that, subsequent starts are fast.

### 4. Open the dashboard

```
http://localhost:3000
```

The dashboard shows agent status, live trades, portfolio, and the master terminal.

---

## Dashboard Pages

| Page | URL | What it shows |
|------|-----|----------------|
| Overview | `/` | System health, agent cards, live activity feed |
| Agents | `/agents` | Per-agent status, controls, and chat interface |
| Terminal | `/terminal` | Master terminal — type `@oracle what is BTC sentiment?` |
| Trades | `/trades` | Open and closed positions |
| Portfolio | `/portfolio` | Balance, P&L, allocation chart |
| Strategies | `/strategies` | Backtest results, active strategies |

---

## Talking to Agents

From the Terminal page, use `@agentname message` syntax:

```
@commander status
@oracle analyze ETH/USD sentiment
@guardian check current risk limits
@architect backtest RSI strategy on BTC/USD
@sage what patterns have been profitable this week?
```

You can also chat with individual agents from the Agents page.

---

## API

The REST API runs at `http://localhost:8000`. Interactive docs are at:

```
http://localhost:8000/docs
```

Key endpoints:

```
GET  /system/health          — system status and paper-readiness check
GET  /agents/                — list all agents and their state
POST /agents/{id}/chat       — send a message to an agent
GET  /trades/                — list trades
GET  /portfolio/             — portfolio summary
GET  /strategies/            — list strategies and backtest results
```

---

## Safety Limits (default values in .env.example)

| Limit | Default |
|-------|---------|
| Live trading | **Disabled** |
| Daily loss limit | $50 |
| Max portfolio risk | 10% |
| Max leverage | 5x |
| Commander alert threshold | 5% drawdown |

Guardian enforces these as hard rules — trades that violate them are blocked, not just warned about.

---

## Enabling Live Trading

**Only do this when you are confident in paper-trading results.**

1. Set `ALPACA_PAPER=false` in `.env` (and ensure your Alpaca account is funded)
2. Set `LIVE_TRADING_ENABLED=true` in `.env`
3. Set conservative limits (`DAILY_LOSS_LIMIT_USD`, `MAX_PORTFOLIO_RISK_PCT`)
4. Restart: `docker compose up -d`

The Guardian agent will still enforce all configured risk limits.

---

## Remote Access (Cloudflare Tunnel)

To access your dashboard from outside your home network:

1. Create a free [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
2. Set `CF_TUNNEL_TOKEN=your_token` in `.env`
3. Start with the remote profile:

```bash
docker compose --profile remote up -d
```

---

## Useful Commands

```bash
# Start everything
docker compose up -d

# Stop everything
docker compose down

# Watch logs for all services
docker compose logs -f

# Watch a specific agent
docker compose logs -f agent-commander

# Restart a single agent (after code change)
docker compose up -d --no-deps --build agent-oracle

# Full reset (deletes all data)
docker compose down -v
```

---

## Project Structure

```
atlas/
├── agents/
│   ├── commander/     # Orchestrator agent
│   ├── oracle/        # Market research agent
│   ├── guardian/      # Risk validation agent
│   ├── trader/        # Trade execution agent
│   ├── sage/          # Learning and pattern analysis agent
│   ├── architect/     # Strategy generation and backtesting agent
│   └── shared/        # Shared base class, DB, Alpaca client, OpenRouter client
├── api/               # FastAPI backend
│   ├── routers/       # REST endpoints
│   └── websocket/     # Real-time WebSocket gateway
├── dashboard/         # Next.js frontend
│   └── src/
│       ├── components/
│       ├── hooks/
│       └── store/
├── infra/
│   ├── nginx/         # Reverse proxy config
│   ├── postgres/      # Database schema
│   └── redis/         # Cache config
├── docker-compose.yml
├── .env               # Local secrets (gitignored)
└── scripts/setup.sh   # One-time setup helper
```

---

## Troubleshooting

**Dashboard won't load**  
→ Check `docker compose logs dashboard` — usually a missing env var or the API isn't healthy yet.

**Agents keep restarting**  
→ Check `docker compose logs agent-commander` — usually a missing API key or DB not ready.

**Trades not executing**  
→ Confirm `LIVE_TRADING_ENABLED=true` and `ALPACA_PAPER=false` in `.env`, then restart.

**System health shows red**  
→ Visit `http://localhost:8000/system/health` to see which check is failing.

---

## License

MIT
