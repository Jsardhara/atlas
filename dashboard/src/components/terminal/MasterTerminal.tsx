"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Send, ChevronDown } from "lucide-react";
import { useAtlasStore } from "../../store";
import { useWebSocket, WSMessage } from "../../hooks/useWebSocket";
import { api } from "../../lib/api";

const AGENTS = ["commander", "oracle", "guardian", "trader", "sage", "architect"];
const ICONS: Record<string, string> = {
  commander: "⚔️", oracle: "🔮", guardian: "🛡️",
  trader: "📊", sage: "📚", architect: "🏗️", system: "⚙️", user: "👤",
};

interface ChatMsg {
  role: "user" | "assistant";
  agent?: string;
  content: string;
  ts: string;
}

const EVENT_LABELS: Record<string, string> = {
  market_signal: "Signal",
  trade_approved: "Approved",
  trade_rejected: "Rejected",
  order_placed: "Order",
  position_opened: "Opened",
  position_closed: "Closed",
  learning_insight: "Insight",
  strategy_proposed: "Strategy",
  backtest_complete: "Backtest",
  agent_status: "Status",
  alert_created: "Alert",
  pipeline_decision: "Decision",
  heartbeat: "Heartbeat",
};

export function MasterTerminal() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [selectedAgent, setSelectedAgent] = useState<string>("commander");
  const [waiting, setWaiting] = useState(false);
  const { recentEvents } = useAtlasStore();
  const sessionId = useRef(`terminal-${Date.now()}`);
  const chatBottom = useRef<HTMLDivElement>(null);

  const handleWS = useCallback((msg: WSMessage) => {
    if (msg.message_type === "chat_response") {
      const sid = msg.payload?.session_id as string;
      if (sid === sessionId.current) {
        setMessages((prev) => [...prev, {
          role: "assistant",
          agent: msg.source_agent,
          content: msg.payload.content as string,
          ts: new Date().toISOString(),
        }]);
        setWaiting(false);
      }
    }
  }, []);

  useWebSocket(handleWS);

  useEffect(() => {
    chatBottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || waiting) return;
    let content = input.trim();
    let target = selectedAgent;

    // Parse @agent prefix
    if (content.startsWith("@")) {
      const parts = content.split(" ", 2);
      const agent = parts[0].slice(1).toLowerCase();
      if (AGENTS.includes(agent)) {
        target = agent;
        content = parts[1] || "";
      }
    }

    const displayContent = target !== selectedAgent
      ? input.trim()
      : `@${target} ${content}`;

    setInput("");
    setMessages((prev) => [...prev, {
      role: "user", content: displayContent, ts: new Date().toISOString()
    }]);
    setWaiting(true);
    await api.sendTerminalMessage(displayContent, sessionId.current);
  };

  return (
    <div className="grid grid-cols-[1fr_420px] gap-4 h-[calc(100vh-8rem)]">
      {/* Left: Chat */}
      <div className="flex flex-col bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="flex items-center gap-3 p-4 border-b border-gray-800">
          <span className="text-sm font-semibold text-white">Master Control Terminal</span>
          <div className="ml-auto flex items-center gap-2">
            <span className="text-xs text-gray-500">Route to:</span>
            <div className="relative">
              <select
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
                className="appearance-none bg-gray-800 border border-gray-700 text-sm text-white px-3 py-1.5 rounded-lg pr-7 focus:outline-none"
              >
                {AGENTS.map((a) => (
                  <option key={a} value={a}>{ICONS[a]} {a.charAt(0).toUpperCase() + a.slice(1)}</option>
                ))}
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-3 scrollbar-thin">
          {messages.length === 0 && (
            <div className="text-center text-gray-600 text-sm mt-12">
              <div className="text-2xl mb-2">⚔️</div>
              Type a message or use <span className="font-mono text-violet-400">@agent</span> to route to a specific agent
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} gap-2`}>
              {msg.role === "assistant" && (
                <span className="text-lg shrink-0 mt-0.5">{ICONS[msg.agent || ""] || "🤖"}</span>
              )}
              <div className={`max-w-[85%] rounded-xl px-4 py-2.5 text-sm ${
                msg.role === "user" ? "bg-violet-600/30 text-violet-100" : "bg-gray-800 text-gray-200"
              }`}>
                {msg.role === "assistant" && msg.agent && (
                  <div className="text-xs text-gray-500 mb-1 font-medium capitalize">{msg.agent}</div>
                )}
                <div className="whitespace-pre-wrap">{msg.content}</div>
              </div>
            </div>
          ))}
          {waiting && (
            <div className="flex justify-start gap-2">
              <span className="text-lg">{ICONS[selectedAgent]}</span>
              <div className="bg-gray-800 rounded-xl px-4 py-3">
                <div className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s` }} />
                  ))}
                </div>
              </div>
            </div>
          )}
          <div ref={chatBottom} />
        </div>

        <div className="p-4 border-t border-gray-800">
          <div className="text-xs text-gray-600 mb-2">
            Tip: prefix with <span className="font-mono text-violet-400">@oracle</span>, <span className="font-mono text-violet-400">@sage</span>, etc. to route to a specific agent
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={`Message ${selectedAgent}... or @agent message`}
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-violet-500"
            />
            <button
              type="submit"
              disabled={!input.trim() || waiting}
              className="bg-violet-600 hover:bg-violet-500 disabled:opacity-40 p-2 rounded-lg"
            >
              <Send size={16} />
            </button>
          </form>
        </div>
      </div>

      {/* Right: Live event feed */}
      <div className="flex flex-col bg-gray-900 rounded-xl border border-gray-800 overflow-hidden">
        <div className="p-4 border-b border-gray-800 flex items-center gap-2">
          <span className="live-dot w-2 h-2 rounded-full bg-emerald-400 inline-block" />
          <span className="text-sm font-semibold text-white">Live Agent Feed</span>
          <span className="ml-auto text-xs text-gray-500">{recentEvents.length} events</span>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin">
          {recentEvents.map((event, i) => (
            <div key={i} className="px-4 py-2.5 border-b border-gray-800/50 hover:bg-gray-800/30">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-base">{ICONS[event.source_agent] || "⚙️"}</span>
                <span className="text-xs font-medium capitalize text-gray-300">{event.source_agent}</span>
                <span className="ml-auto text-xs bg-gray-800 px-1.5 py-0.5 rounded text-gray-400">
                  {EVENT_LABELS[event.message_type] || event.message_type}
                </span>
              </div>
              <div className="text-xs text-gray-500 truncate">
                {(event.payload?.activity as string) ||
                 (event.payload?.pair as string) ||
                 (event.payload?.content as string) ||
                 event.message_type}
              </div>
            </div>
          ))}
          {recentEvents.length === 0 && (
            <div className="text-center text-gray-600 text-sm mt-12">
              Waiting for agent events...
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
