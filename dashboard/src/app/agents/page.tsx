"use client";
import { useEffect, useState } from "react";
import { api, type Agent } from "../../lib/api";
import { AgentCard } from "../../components/agents/AgentCard";

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);

  const load = async () => setAgents(await api.getAgents().catch(() => []));
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, []);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Agents</h1>
      <p className="text-gray-400 text-sm">
        All 6 agents run in parallel. Click an agent to open its dedicated chat window and activity log.
        Use the <a href="/terminal" className="text-violet-400 underline">Terminal</a> to talk to all agents from one place.
      </p>
      <div className="grid grid-cols-3 gap-4">
        {agents.map((agent) => (
          <AgentCard key={agent.id} agent={agent} onRefresh={load} />
        ))}
      </div>
    </div>
  );
}
