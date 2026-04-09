"use client";
import { useEffect, useState } from "react";
import { api, type Agent, type TradeStats, type PaperReadiness } from "../lib/api";
import { useAtlasStore } from "../store";
import { AgentCard } from "../components/agents/AgentCard";
import { CheckCircle, XCircle, Clock } from "lucide-react";

export default function Overview() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [readiness, setReadiness] = useState<PaperReadiness | null>(null);
  const { recentEvents, setOpenTradeCount } = useAtlasStore();

  const load = async () => {
    const [a, s, r] = await Promise.all([
      api.getAgents().catch(() => []),
      api.getTradeStats().catch(() => null),
      api.getPaperReadiness().catch(() => null),
    ]);
    setAgents(a);
    setStats(s);
    setReadiness(r);
  };

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">ATLAS Overview</h1>
        <span className="text-xs bg-amber-900/40 border border-amber-700/40 text-amber-300 px-3 py-1 rounded-full">
          📄 Paper Trading Mode
        </span>
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: "Total Trades", value: stats.total, color: "text-white" },
            { label: "Win Rate", value: `${(stats.win_rate * 100).toFixed(1)}%`, color: stats.win_rate >= 0.52 ? "text-emerald-400" : "text-red-400" },
            { label: "Total P&L", value: `$${stats.total_pnl_usd?.toFixed(2) ?? "0.00"}`, color: (stats.total_pnl_usd ?? 0) >= 0 ? "text-emerald-400" : "text-red-400" },
            { label: "Avg P&L/Trade", value: `$${stats.avg_pnl_usd?.toFixed(2) ?? "0.00"}`, color: (stats.avg_pnl_usd ?? 0) >= 0 ? "text-emerald-400" : "text-red-400" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="text-xs text-gray-500 mb-1">{label}</div>
              <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Paper Trading Readiness */}
      {readiness && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">Live Trading Readiness</h2>
            {readiness.live_trading_ready
              ? <span className="text-xs bg-emerald-900/40 border border-emerald-700 text-emerald-300 px-2 py-1 rounded-full">🟢 Ready to unlock</span>
              : <span className="text-xs bg-gray-800 text-gray-400 px-2 py-1 rounded-full">In progress</span>
            }
          </div>
          <div className="grid grid-cols-5 gap-3">
            {[
              { label: "Trades", current: readiness.total_trades, target: readiness.thresholds.trades_target, format: (v: number) => String(v) },
              { label: "Days Active", current: readiness.days_active, target: readiness.thresholds.days_target, format: (v: number) => String(v) },
              { label: "Win Rate", current: readiness.win_rate_30, target: readiness.thresholds.win_rate_target, format: (v: number) => `${(v * 100).toFixed(1)}%` },
              { label: "Total P&L", current: readiness.total_pnl_pct, target: readiness.thresholds.pnl_target, format: (v: number) => `${(v * 100).toFixed(1)}%` },
              { label: "Max Drawdown", current: readiness.max_drawdown_pct, target: readiness.thresholds.drawdown_limit, format: (v: number) => `${(v * 100).toFixed(1)}%`, invert: true },
            ].map(({ label, current, target, format, invert }) => {
              const passed = invert ? current <= target : current >= target;
              const pct = invert
                ? Math.max(0, Math.min(100, (1 - current / target) * 100))
                : Math.min(100, (current / target) * 100);
              return (
                <div key={label} className="bg-gray-800/50 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-gray-400">{label}</span>
                    {passed ? <CheckCircle size={12} className="text-emerald-400" /> : <Clock size={12} className="text-gray-500" />}
                  </div>
                  <div className={`text-lg font-bold font-mono ${passed ? "text-emerald-400" : "text-gray-300"}`}>
                    {format(current)}
                  </div>
                  <div className="text-xs text-gray-600 mb-2">target: {format(target)}</div>
                  <div className="h-1 bg-gray-700 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${passed ? "bg-emerald-500" : "bg-violet-500"}`}
                      style={{ width: `${pct}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Agent Grid */}
      <div>
        <h2 className="font-semibold text-white mb-3">Agents</h2>
        <div className="grid grid-cols-3 gap-4">
          {agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} onRefresh={load} />
          ))}
        </div>
      </div>

      {/* Live activity strip */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-800">
          <span className="live-dot w-2 h-2 rounded-full bg-emerald-400 inline-block" />
          <span className="text-sm font-medium text-white">Live Activity</span>
        </div>
        <div className="max-h-48 overflow-y-auto scrollbar-thin">
          {recentEvents.slice(0, 20).map((ev, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-2 border-b border-gray-800/50 text-xs">
              <span className="text-gray-500 font-mono">{new Date(ev.timestamp).toLocaleTimeString()}</span>
              <span className="font-medium capitalize text-gray-300 w-20 shrink-0">{ev.source_agent}</span>
              <span className="text-gray-500 truncate">
                {(ev.payload?.activity as string) || (ev.payload?.pair as string) || ev.message_type}
              </span>
            </div>
          ))}
          {recentEvents.length === 0 && (
            <div className="text-center text-gray-600 py-6 text-xs">No activity yet</div>
          )}
        </div>
      </div>
    </div>
  );
}
