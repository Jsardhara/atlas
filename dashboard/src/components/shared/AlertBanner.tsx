"use client";
import { useEffect, useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { useAtlasStore } from "../../store";

export function AlertBanner() {
  const { alerts, dismissAlert } = useAtlasStore();
  const [countdowns, setCountdowns] = useState<Record<string, number>>({});

  useEffect(() => {
    const timer = setInterval(() => {
      setCountdowns((prev) => {
        const next = { ...prev };
        for (const a of alerts) {
          if (!(a.id in next)) next[a.id] = a.countdown_secs;
          else if (next[a.id] > 0) next[a.id]--;
        }
        return next;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [alerts]);

  if (alerts.length === 0) return null;

  const topAlert = alerts[0];
  const countdown = countdowns[topAlert.id] ?? topAlert.countdown_secs;
  const colorClass = topAlert.severity === "critical"
    ? "border-red-600 bg-red-950/50"
    : topAlert.severity === "warning"
    ? "border-amber-600 bg-amber-950/50"
    : "border-blue-600 bg-blue-950/50";

  return (
    <div className={`border-b ${colorClass} px-6 py-3 flex items-center gap-4`}>
      <AlertTriangle size={16} className={
        topAlert.severity === "critical" ? "text-red-400" : "text-amber-400"
      } />
      <div className="flex-1 min-w-0">
        <span className="font-medium text-sm">{topAlert.title}</span>
        <span className="text-gray-400 text-sm ml-2">{topAlert.message}</span>
      </div>
      {topAlert.auto_action && (
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-xs text-gray-400">
            Auto: {topAlert.auto_action} in <span className="font-mono font-bold text-amber-300">{countdown}s</span>
          </span>
          <button
            onClick={() => dismissAlert(topAlert.id)}
            className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded"
          >
            Override
          </button>
        </div>
      )}
      <button onClick={() => dismissAlert(topAlert.id)} className="text-gray-500 hover:text-gray-300">
        <X size={14} />
      </button>
    </div>
  );
}
