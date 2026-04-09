"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { Send } from "lucide-react";
import { useWebSocket, WSMessage } from "../../hooks/useWebSocket";
import { api } from "../../lib/api";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

const AGENT_ICONS: Record<string, string> = {
  commander: "⚔️", oracle: "🔮", guardian: "🛡️",
  trader: "📊", sage: "📚", architect: "🏗️",
};

export function AgentChat({ agentId, agentName }: { agentId: string; agentName: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [waiting, setWaiting] = useState(false);
  const sessionId = useRef(`chat-${agentId}-${Date.now()}`);
  const bottomRef = useRef<HTMLDivElement>(null);

  const handleWS = useCallback((msg: WSMessage) => {
    if (
      msg.message_type === "chat_response" &&
      msg.source_agent === agentId &&
      (msg.payload?.session_id as string) === sessionId.current
    ) {
      setMessages((prev) => [...prev, {
        role: "assistant",
        content: msg.payload.content as string,
        timestamp: new Date().toISOString(),
      }]);
      setWaiting(false);
    }
  }, [agentId]);

  useWebSocket(handleWS);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || waiting) return;
    const content = input.trim();
    setInput("");
    setMessages((prev) => [...prev, {
      role: "user", content, timestamp: new Date().toISOString()
    }]);
    setWaiting(true);
    await api.chatWithAgent(agentId, content, sessionId.current);
  };

  return (
    <div className="flex flex-col h-full bg-gray-900 rounded-xl border border-gray-800">
      {/* Header */}
      <div className="flex items-center gap-3 p-4 border-b border-gray-800">
        <span className="text-xl">{AGENT_ICONS[agentId] || "🤖"}</span>
        <div>
          <div className="font-semibold text-sm">{agentName}</div>
          <div className="text-xs text-gray-500">Individual chat session</div>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {messages.length === 0 && (
          <div className="text-center text-gray-600 text-sm mt-8">
            Start a conversation with {agentName}
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm ${
              msg.role === "user"
                ? "bg-violet-600/30 text-violet-100"
                : "bg-gray-800 text-gray-200"
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {waiting && (
          <div className="flex justify-start">
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
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-800">
        <form onSubmit={(e) => { e.preventDefault(); send(); }} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={`Ask ${agentName}...`}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-violet-500"
          />
          <button
            type="submit"
            disabled={!input.trim() || waiting}
            className="bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed p-2 rounded-lg"
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
