"use client";
import { useCallback } from "react";
import { useWebSocket, WSMessage } from "../../hooks/useWebSocket";
import { useAtlasStore } from "../../store";

export function WSProvider({ children }: { children: React.ReactNode }) {
  const { updateAgentActivity, addEvent, addAlert } = useAtlasStore();

  const handleMessage = useCallback((msg: WSMessage) => {
    addEvent(msg);

    if (msg.message_type === "agent_status" && msg.source_agent) {
      const activity = (msg.payload?.activity as string) || "";
      updateAgentActivity(msg.source_agent, activity);
    }

    if (msg.message_type === "alert_created") {
      const p = msg.payload as Record<string, unknown>;
      addAlert({
        id: p.alert_id as string,
        severity: p.severity as string,
        title: p.title as string,
        message: p.message as string,
        auto_action: p.auto_action as string | null,
        countdown_secs: p.countdown_secs as number,
        status: "pending",
        created_at: msg.timestamp,
      });
    }
  }, [updateAgentActivity, addEvent, addAlert]);

  useWebSocket(handleMessage);
  return <>{children}</>;
}
