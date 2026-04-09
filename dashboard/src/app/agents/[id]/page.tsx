"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type AgentDetail } from "../../../lib/api";
import { AgentChat } from "../../../components/agents/AgentChat";
import { Pause, Play, RefreshCw } from "lucide-react";

export default function AgentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [agent, setAgent] = useState<AgentDetail | null>(null);
  const [memory, setMemory] = useState<Record<string, unknown>>({});

  const load = async () => {
    const [a, m] = await Promise.all([
      api.getAgent(id).catch(() => null),
      api.getAgentMemory(id).catch(() => ({})),
    ]);
    setAgent(a);
    setMemory(m as Record<string, unknown>);
  };

  useEffect(() => { load(); }, [id]);

  const toggle = async () => {
    if (!agent) return;
    if (agent.state === "running") await api.pauseAgent(id);
    else await api.resumeAgent(id);
    load();
  };

  if (!agent) return <div className="text-gray-500 p-8">Loading...</div>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-white capitalize">{agent.display_name}</h1>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${
          agent.state === "running" ? "text-emerald-400 border-emerald-700 bg-emerald-950/40" :
          agent.state === "paused" ? "text-amber-400 border-amber-700" :
          "text-red-400 border-red-700"
        }`}>{agent.state}</span>
        <span className="text-xs text-gray-500 font-mono">{agent.model}</span>
        <div className="ml-auto flex gap-2">
          <button onClick={toggle} className="flex items-center gap-1.5 text-xs bg-gray-800 hover:bg-gray-700 px-3 py-1.5 rounded-lg">
            {agent.state === "running" ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Resume</>}
          </button>
          <button onClick={load} className="p-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg">
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-[1fr_380px] gap-4" style={{ height: "calc(100vh - 12rem)" }}>
        {/* Chat */}
        <AgentChat agentId={id} agentName={agent.display_name} />

        {/* Right panel: activity + memory */}
        <div className="flex flex-col gap-4 overflow-hidden">
          {/* Activity log */}
          <div className="flex-1 bg-gray-900 border border-gray-800 rounded-xl overflow-hidden flex flex-col">
            <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold text-white">
              Activity Log
            </div>
            <div className="flex-1 overflow-y-auto scrollbar-thin">
              {agent.recent_activity.map((ev, i) => (
                <div key={i} className="px-4 py-2.5 border-b border-gray-800/50 hover:bg-gray-800/20">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">
                      {ev.event_type}
                    </span>
                    <span className="text-xs text-gray-600 ml-auto">
                      {new Date(ev.occurred_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="text-xs text-gray-500 truncate">
                    {(ev.payload?.activity as string) || (ev.payload?.pair as string) || JSON.stringify(ev.payload).slice(0, 80)}
                  </div>
                </div>
              ))}
              {agent.recent_activity.length === 0 && (
                <div className="text-center text-gray-600 text-xs py-8">No activity recorded</div>
              )}
            </div>
          </div>

          {/* Memory viewer */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden max-h-52">
            <div className="px-4 py-3 border-b border-gray-800 text-sm font-semibold text-white">
              Agent Memory
            </div>
            <div className="overflow-y-auto scrollbar-thin max-h-40">
              {Object.entries(memory).map(([key, val]) => (
                <div key={key} className="px-4 py-2 border-b border-gray-800/50">
                  <div className="text-xs font-medium text-violet-400 mb-0.5">{key}</div>
                  <div className="text-xs text-gray-500 truncate">
                    {JSON.stringify((val as Record<string, unknown>)?.value || val).slice(0, 100)}
                  </div>
                </div>
              ))}
              {Object.keys(memory).length === 0 && (
                <div className="text-center text-gray-600 text-xs py-4">No memories yet</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
