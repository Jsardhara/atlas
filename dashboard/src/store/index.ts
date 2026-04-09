"use client";
import { create } from "zustand";
import type { WSMessage } from "../hooks/useWebSocket";
import type { Agent, Alert } from "../lib/api";

interface AtlasStore {
  agents: Record<string, Agent & { activity?: string }>;
  alerts: Alert[];
  recentEvents: WSMessage[];
  openTradeCount: number;

  updateAgentActivity: (agentId: string, activity: string) => void;
  addEvent: (msg: WSMessage) => void;
  addAlert: (alert: Alert) => void;
  dismissAlert: (alertId: string) => void;
  setOpenTradeCount: (n: number) => void;
}

export const useAtlasStore = create<AtlasStore>((set) => ({
  agents: {},
  alerts: [],
  recentEvents: [],
  openTradeCount: 0,

  updateAgentActivity: (agentId, activity) =>
    set((s) => ({
      agents: {
        ...s.agents,
        [agentId]: { ...(s.agents[agentId] || {} as Agent), activity },
      },
    })),

  addEvent: (msg) =>
    set((s) => ({
      recentEvents: [msg, ...s.recentEvents].slice(0, 100),
    })),

  addAlert: (alert) =>
    set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 20) })),

  dismissAlert: (alertId) =>
    set((s) => ({ alerts: s.alerts.filter((a) => a.id !== alertId) })),

  setOpenTradeCount: (n) => set({ openTradeCount: n }),
}));
