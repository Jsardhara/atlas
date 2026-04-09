const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  // Agents
  getAgents: () => request<Agent[]>("/agents"),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${id}`),
  pauseAgent: (id: string) => request(`/agents/${id}/pause`, { method: "POST" }),
  resumeAgent: (id: string) => request(`/agents/${id}/resume`, { method: "POST" }),
  getAgentMemory: (id: string) => request(`/agents/${id}/memory`),
  chatWithAgent: (id: string, content: string, sessionId?: string) =>
    request(`/agents/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ content, session_id: sessionId }),
    }),

  // Trades
  getTrades: (params?: { status?: string; pair?: string; limit?: number }) => {
    const q = new URLSearchParams(params as Record<string, string>).toString();
    return request<Trade[]>(`/trades${q ? `?${q}` : ""}`);
  },
  getOpenTrades: () => request<Trade[]>("/trades/open"),
  getTradeStats: () => request<TradeStats>("/trades/stats"),
  closeTrade: (id: string) => request(`/trades/${id}/close`, { method: "POST" }),

  // Portfolio
  getPortfolio: () => request<Portfolio>("/portfolio"),
  getPortfolioHistory: () => request<PortfolioSnapshot[]>("/portfolio/history"),

  // Signals
  getSignals: () => request<Signal[]>("/signals"),
  getActiveSignals: () => request<Signal[]>("/signals/active"),
  overrideSignal: (id: string, action: "approve" | "reject") =>
    request(`/signals/${id}/override?action=${action}`, { method: "POST" }),

  // Strategies
  getStrategies: () => request<Strategy[]>("/strategies"),
  getStrategy: (id: string) => request<StrategyDetail>(`/strategies/${id}`),
  activateStrategy: (id: string) => request(`/strategies/${id}/activate`, { method: "POST" }),
  generateStrategy: () => request("/strategies/generate", { method: "POST" }),

  // Terminal
  sendTerminalMessage: (content: string, sessionId?: string) =>
    request("/terminal/message", {
      method: "POST",
      body: JSON.stringify({ content, session_id: sessionId }),
    }),

  // System
  getHealth: () => request<SystemHealth>("/system/health"),
  getAlerts: () => request<Alert[]>("/system/alerts"),
  getPaperReadiness: () => request<PaperReadiness>("/system/paper-readiness"),
};

// Types
export interface Agent {
  id: string;
  display_name: string;
  model: string;
  state: "running" | "paused" | "error";
  last_heartbeat: string | null;
  config: Record<string, unknown>;
}

export interface AgentDetail extends Agent {
  personality: string;
  recent_activity: ActivityEntry[];
}

export interface ActivityEntry {
  event_type: string;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface Trade {
  id: string;
  pair: string;
  side: string;
  order_type: string;
  leverage: number;
  requested_size: number;
  entry_price: number | null;
  exit_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  status: string;
  pnl_usd: number | null;
  pnl_pct: number | null;
  opened_at: string | null;
  closed_at: string | null;
  close_reason: string | null;
  is_paper: boolean;
}

export interface TradeStats {
  total: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_pnl_usd: number;
  total_pnl_usd: number;
}

export interface Portfolio {
  total_usd: number;
  available_usd: number;
  realized_pnl: number;
  unrealized_pnl: number;
  open_positions: Trade[];
  is_paper: boolean;
}

export interface PortfolioSnapshot {
  snapshot_at: string;
  total_usd: number;
  realized_pnl: number;
  unrealized_pnl: number;
}

export interface Signal {
  id: string;
  pair: string;
  direction: string;
  confidence: number;
  reasoning: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  status: string;
  created_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  version: number;
  status: string;
  performance_metrics: Record<string, number> | null;
  created_at: string;
}

export interface StrategyDetail extends Strategy {
  code: string;
  backtests: Backtest[];
}

export interface Backtest {
  id: string;
  timerange: string;
  status: string;
  sharpe_ratio: number | null;
  max_drawdown: number | null;
  total_return: number | null;
  win_rate: number | null;
  completed_at: string | null;
}

export interface SystemHealth {
  status: string;
  postgres: string;
  redis: string;
  agents: Record<string, { state: string; last_heartbeat: string | null }>;
}

export interface Alert {
  id: string;
  severity: string;
  title: string;
  message: string;
  auto_action: string | null;
  countdown_secs: number;
  status: string;
  created_at: string;
}

export interface PaperReadiness {
  total_trades: number;
  days_active: number;
  win_rate_30: number;
  total_pnl_pct: number;
  max_drawdown_pct: number;
  live_trading_ready: boolean;
  thresholds: {
    trades_target: number;
    days_target: number;
    win_rate_target: number;
    pnl_target: number;
    drawdown_limit: number;
  };
}
