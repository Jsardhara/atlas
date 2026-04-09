"use client";
import { useEffect, useState, useCallback } from "react";
import { api, type Trade } from "../../lib/api";
import { useAtlasStore } from "../../store";
import { useWebSocket, WSMessage } from "../../hooks/useWebSocket";
import { TrendingUp, TrendingDown, X } from "lucide-react";
import { clsx } from "clsx";

export default function TradesPage() {
  const [openTrades, setOpenTrades] = useState<Trade[]>([]);
  const [allTrades, setAllTrades] = useState<Trade[]>([]);
  const { setOpenTradeCount } = useAtlasStore();

  const load = async () => {
    const [open, all] = await Promise.all([
      api.getOpenTrades().catch(() => []),
      api.getTrades({ limit: 100 }).catch(() => []),
    ]);
    setOpenTrades(open);
    setAllTrades(all);
    setOpenTradeCount(open.length);
  };

  // Live refresh on position events
  const handleWS = useCallback((msg: WSMessage) => {
    if (["position_opened", "position_closed", "order_placed"].includes(msg.message_type)) {
      load();
    }
  }, []);
  useWebSocket(handleWS);

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Trades</h1>

      {/* Open positions */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Open Positions ({openTrades.length})
        </h2>
        {openTrades.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-gray-600 text-sm">
            No open positions
          </div>
        ) : (
          <div className="space-y-2">
            {openTrades.map((t) => (
              <OpenPositionRow key={t.id} trade={t} onClose={load} />
            ))}
          </div>
        )}
      </div>

      {/* Trade history */}
      <div>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Trade History ({allTrades.filter(t => t.status === "closed").length})
        </h2>
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-xs text-gray-500 uppercase">
                {["Pair", "Side", "Leverage", "Size", "Entry", "Exit", "P&L", "Status", "Opened", "Mode"].map((h) => (
                  <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {allTrades.map((t) => (
                <TradeRow key={t.id} trade={t} />
              ))}
            </tbody>
          </table>
          {allTrades.length === 0 && (
            <div className="text-center text-gray-600 py-8 text-sm">No trades yet</div>
          )}
        </div>
      </div>
    </div>
  );
}

function OpenPositionRow({ trade, onClose }: { trade: Trade; onClose: () => void }) {
  const pnl = trade.pnl_usd ?? 0;
  const isPos = pnl >= 0;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center gap-4">
      <div className="flex items-center gap-2">
        {trade.side === "buy"
          ? <TrendingUp size={16} className="text-emerald-400" />
          : <TrendingDown size={16} className="text-red-400" />
        }
        <span className="font-semibold text-white">{trade.pair}</span>
      </div>
      <span className={`text-xs px-2 py-0.5 rounded ${trade.side === "buy" ? "bg-emerald-900/40 text-emerald-400" : "bg-red-900/40 text-red-400"}`}>
        {trade.side === "buy" ? "LONG" : "SHORT"} {trade.leverage}x
      </span>
      <div className="text-sm text-gray-400">
        Entry: <span className="text-white font-mono">${trade.entry_price?.toFixed(2) ?? "—"}</span>
      </div>
      <div className="text-sm text-gray-400">
        Size: <span className="text-white font-mono">${trade.requested_size?.toFixed(2) ?? "—"}</span>
      </div>
      <div className={`text-sm font-mono font-semibold ${isPos ? "text-emerald-400" : "text-red-400"}`}>
        {isPos ? "+" : ""}{pnl.toFixed(2)} USD
      </div>
      {trade.is_paper && (
        <span className="text-xs bg-amber-900/30 text-amber-400 border border-amber-700/40 px-2 py-0.5 rounded">PAPER</span>
      )}
      <button
        onClick={async () => { await api.closeTrade(trade.id); onClose(); }}
        className="ml-auto flex items-center gap-1.5 text-xs bg-red-900/30 hover:bg-red-900/50 text-red-400 border border-red-700/40 px-2.5 py-1 rounded-lg"
      >
        <X size={12} /> Close
      </button>
    </div>
  );
}

function TradeRow({ trade }: { trade: Trade }) {
  const pnl = trade.pnl_usd ?? 0;
  const isPos = pnl >= 0;

  return (
    <tr className="border-b border-gray-800/50 hover:bg-gray-800/20 text-xs">
      <td className="px-4 py-3 font-medium text-white">{trade.pair}</td>
      <td className="px-4 py-3">
        <span className={trade.side === "buy" ? "text-emerald-400" : "text-red-400"}>
          {trade.side === "buy" ? "LONG" : "SHORT"}
        </span>
      </td>
      <td className="px-4 py-3 text-gray-400">{trade.leverage}x</td>
      <td className="px-4 py-3 font-mono text-gray-300">${trade.requested_size?.toFixed(2)}</td>
      <td className="px-4 py-3 font-mono text-gray-300">${trade.entry_price?.toFixed(2) ?? "—"}</td>
      <td className="px-4 py-3 font-mono text-gray-300">${trade.exit_price?.toFixed(2) ?? "—"}</td>
      <td className={clsx("px-4 py-3 font-mono font-semibold", isPos ? "text-emerald-400" : "text-red-400")}>
        {isPos ? "+" : ""}{pnl.toFixed(2)}
      </td>
      <td className="px-4 py-3">
        <span className={clsx("px-1.5 py-0.5 rounded text-xs", {
          "bg-emerald-900/30 text-emerald-400": trade.status === "open",
          "bg-gray-800 text-gray-400": trade.status === "closed",
          "bg-red-900/30 text-red-400": trade.status === "error",
        })}>
          {trade.status}
        </span>
      </td>
      <td className="px-4 py-3 text-gray-500">
        {trade.opened_at ? new Date(trade.opened_at).toLocaleString() : "—"}
      </td>
      <td className="px-4 py-3">
        {trade.is_paper && <span className="text-amber-500 text-xs">paper</span>}
      </td>
    </tr>
  );
}
