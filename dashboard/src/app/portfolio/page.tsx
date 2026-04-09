"use client";
import { useEffect, useState } from "react";
import { api, type Portfolio, type PortfolioSnapshot } from "../../lib/api";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { format } from "date-fns";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [history, setHistory] = useState<PortfolioSnapshot[]>([]);

  const load = async () => {
    const [p, h] = await Promise.all([
      api.getPortfolio().catch(() => null),
      api.getPortfolioHistory().catch(() => []),
    ]);
    setPortfolio(p);
    setHistory(h);
  };

  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);

  const chartData = history.map((s) => ({
    time: format(new Date(s.snapshot_at), "MM/dd HH:mm"),
    equity: Number(s.total_usd.toFixed(2)),
    realized: Number(s.realized_pnl.toFixed(2)),
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Portfolio</h1>

      {/* Summary cards */}
      {portfolio && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: "Total Equity", value: `$${portfolio.total_usd?.toFixed(2) ?? "—"}`, color: "text-white" },
            { label: "Available", value: `$${portfolio.available_usd?.toFixed(2) ?? "—"}`, color: "text-gray-300" },
            { label: "Realized P&L", value: `$${portfolio.realized_pnl?.toFixed(2) ?? "0.00"}`, color: (portfolio.realized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400" },
            { label: "Unrealized P&L", value: `$${portfolio.unrealized_pnl?.toFixed(2) ?? "0.00"}`, color: (portfolio.unrealized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-red-400" },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <div className="text-xs text-gray-500 mb-1">{label}</div>
              <div className={`text-2xl font-bold font-mono ${color}`}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Equity curve */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="font-semibold text-white mb-4">Equity Curve</h2>
        {chartData.length > 1 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="time" tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} />
              <YAxis tick={{ fill: "#6b7280", fontSize: 11 }} tickLine={false} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                contentStyle={{ backgroundColor: "#111827", border: "1px solid #374151", borderRadius: "8px" }}
                labelStyle={{ color: "#9ca3af" }}
              />
              <Line type="monotone" dataKey="equity" stroke="#8b5cf6" strokeWidth={2} dot={false} name="Equity" />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-48 flex items-center justify-center text-gray-600 text-sm">
            Not enough data yet — trades will populate this chart
          </div>
        )}
      </div>
    </div>
  );
}
