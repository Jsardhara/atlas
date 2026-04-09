"use client";
import Link from "next/link";
import { clsx } from "clsx";
import { Pause, Play, MessageSquare } from "lucide-react";
import type { Agent } from "../../lib/api";
import { useAtlasStore } from "../../store";
import { api } from "../../lib/api";

const AGENT_ICONS: Record<string, string> = {
  commander: "⚔️", oracle: "🔮", guardian: "🛡️",
  trader: "📊", sage: "📚", architect: "🏗️",
};

const AGENT_COLORS: Record<string, string> = {
  commander: "border-violet-600/40 bg-violet-600/5",
  oracle: "border-blue-600/40 bg-blue-600/5",
  guardian: "border-amber-600/40 bg-amber-600/5",
  trader: "border-emerald-600/40 bg-emerald-600/5",
  sage: "border-pink-600/40 bg-pink-600/5",
  architect: "border-indigo-600/40 bg-indigo-600/5",
};

export function AgentCard({ agent, onRefresh }: { agent: Agent; onRefresh: () => void }) {
  const { agents } = useAtlasStore();
  const liveActivity = agents[agent.id]?.activity;

  const handleToggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (agent.state === "running") await api.pauseAgent(agent.id);
    else await api.resumeAgent(agent.id);
    onRefresh();
  };

  return (
    <Link href={`/agents/${agent.id}`}>
      <div className={clsx(
        "border rounded-xl p-5 cursor-pointer transition-all hover:scale-[1.01] hover:border-opacity-70",
        AGENT_COLORS[agent.id] || "border-gray-700 bg-gray-800/30",
      )}>
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{AGENT_ICONS[agent.id] || "🤖"}</span>
            <div>
              <div className="font-semibold text-white">{agent.display_name}</div>
              <div className="text-xs text-gray-500 font-mono truncate max-w-[140px]">{agent.model}</div>
            </div>
          </div>
          <StatusDot state={agent.state} />
        </div>

        {/* Live activity */}
        <div className="min-h-[2rem] mb-4">
          {liveActivity ? (
            <div className="flex items-center gap-2 text-xs text-gray-300">
              {agent.state === "running" && (
                <span className="live-dot w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" />
              )}
              <span className="truncate">{liveActivity}</span>
            </div>
          ) : (
            <div className="text-xs text-gray-600 italic">Waiting for activity...</div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={handleToggle}
            className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 px-2.5 py-1.5 rounded-lg"
          >
            {agent.state === "running" ? <Pause size={12} /> : <Play size={12} />}
            {agent.state === "running" ? "Pause" : "Resume"}
          </button>
          <span className="flex items-center gap-1.5 text-xs text-gray-500 ml-auto">
            <MessageSquare size={12} />
            Chat
          </span>
        </div>
      </div>
    </Link>
  );
}

function StatusDot({ state }: { state: string }) {
  return (
    <div className={clsx(
      "w-2 h-2 rounded-full shrink-0 mt-1",
      state === "running" ? "bg-emerald-400 live-dot" :
      state === "paused" ? "bg-amber-400" : "bg-red-400"
    )} />
  );
}
