"use client";
import { useEffect, useState } from "react";
import { api, type Strategy, type StrategyDetail } from "../../lib/api";
import { CheckCircle, XCircle, Clock, Code, RefreshCw } from "lucide-react";
import { clsx } from "clsx";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selected, setSelected] = useState<StrategyDetail | null>(null);
  const [generating, setGenerating] = useState(false);

  const load = async () => setStrategies(await api.getStrategies().catch(() => []));

  useEffect(() => { load(); }, []);

  const openStrategy = async (id: string) => {
    setSelected(await api.getStrategy(id).catch(() => null));
  };

  const handleGenerate = async () => {
    setGenerating(true);
    await api.generateStrategy().catch(() => {});
    setTimeout(() => { setGenerating(false); load(); }, 3000);
  };

  const handleActivate = async (id: string) => {
    await api.activateStrategy(id);
    load();
    if (selected?.id === id) openStrategy(id);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Strategies</h1>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg"
        >
          <RefreshCw size={14} className={generating ? "animate-spin" : ""} />
          {generating ? "Generating..." : "Generate New Strategy"}
        </button>
      </div>

      <div className="grid grid-cols-[300px_1fr] gap-4">
        {/* List */}
        <div className="space-y-2">
          {strategies.map((s) => (
            <div
              key={s.id}
              onClick={() => openStrategy(s.id)}
              className={clsx(
                "bg-gray-900 border rounded-xl p-4 cursor-pointer transition-all hover:border-gray-600",
                selected?.id === s.id ? "border-violet-600/60" : "border-gray-800"
              )}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="font-medium text-sm text-white truncate">{s.name}</span>
                <StatusIcon status={s.status} />
              </div>
              <div className="text-xs text-gray-500">v{s.version} · {s.status}</div>
              {s.performance_metrics && (
                <div className="flex gap-3 mt-2 text-xs text-gray-400 font-mono">
                  <span>WR: {((s.performance_metrics.win_rate ?? 0) * 100).toFixed(0)}%</span>
                  <span>Sharpe: {(s.performance_metrics.sharpe_ratio ?? 0).toFixed(2)}</span>
                </div>
              )}
            </div>
          ))}
          {strategies.length === 0 && (
            <div className="text-center text-gray-600 text-sm py-8 bg-gray-900 border border-gray-800 rounded-xl">
              No strategies yet.<br />Click "Generate" to create one.
            </div>
          )}
        </div>

        {/* Detail */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          {selected ? (
            <div className="flex flex-col h-full">
              <div className="flex items-center gap-3 p-4 border-b border-gray-800">
                <Code size={16} className="text-violet-400" />
                <span className="font-semibold text-white">{selected.name}</span>
                <span className="text-xs text-gray-500">v{selected.version}</span>
                <div className="ml-auto flex gap-2">
                  {selected.status === "testing" || selected.status === "proposed" ? (
                    <button
                      onClick={() => handleActivate(selected.id)}
                      className="text-xs bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded-lg"
                    >
                      Activate
                    </button>
                  ) : null}
                </div>
              </div>

              {/* Backtest metrics */}
              {selected.backtests.length > 0 && (
                <div className="p-4 border-b border-gray-800 grid grid-cols-4 gap-3">
                  {[
                    { label: "Win Rate", value: `${((selected.backtests[0].win_rate ?? 0) * 100).toFixed(1)}%` },
                    { label: "Total Return", value: `${((selected.backtests[0].total_return ?? 0) * 100).toFixed(2)}%` },
                    { label: "Max Drawdown", value: `${((selected.backtests[0].max_drawdown ?? 0) * 100).toFixed(1)}%` },
                    { label: "Sharpe", value: (selected.backtests[0].sharpe_ratio ?? 0).toFixed(2) },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-800/50 rounded-lg p-3 text-center">
                      <div className="text-xs text-gray-500 mb-1">{label}</div>
                      <div className="text-sm font-bold font-mono text-white">{value}</div>
                    </div>
                  ))}
                </div>
              )}

              {/* Code */}
              <div className="flex-1 overflow-auto p-4">
                <pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap leading-relaxed">
                  {selected.code}
                </pre>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-center h-48 text-gray-600 text-sm">
              Select a strategy to view details
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StatusIcon({ status }: { status: string }) {
  if (status === "active") return <CheckCircle size={14} className="text-emerald-400 shrink-0" />;
  if (status === "archived") return <XCircle size={14} className="text-gray-600 shrink-0" />;
  return <Clock size={14} className="text-amber-400 shrink-0" />;
}
