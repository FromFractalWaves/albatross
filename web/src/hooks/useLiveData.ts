"use client";

import { useEffect, useReducer, useRef } from "react";
import type { Thread, Event, RoutingRecord, TRMContext } from "@/types/trm";
import type { ThreadDecision, EventDecision } from "@/types/trm";
import { API_BASE } from "@/lib/api";

export type LiveStatus = "loading" | "ready" | "empty" | "error";

interface LiveState {
  status: LiveStatus;
  context: TRMContext | null;
  routingRecords: RoutingRecord[];
  latestPacketId: string | null;
  error: string | null;
}

type Action =
  | { type: "loading" }
  | { type: "loaded"; threads: Thread[]; events: Event[]; transmissions: TransmissionRow[] }
  | { type: "error"; error: string };

interface TransmissionRow {
  id: string;
  timestamp: string;
  text: string;
  status: string;
  thread_id: string | null;
  event_id: string | null;
  thread_decision: string | null;
  event_decision: string | null;
  metadata: Record<string, unknown>;
}

const initialState: LiveState = {
  status: "loading",
  context: null,
  routingRecords: [],
  latestPacketId: null,
  error: null,
};

function reducer(state: LiveState, action: Action): LiveState {
  switch (action.type) {
    case "loading":
      return { ...state, status: "loading" };
    case "loaded": {
      const { threads, events, transmissions } = action;

      const context: TRMContext = {
        active_threads: threads,
        active_events: events,
        packets_to_resolve: [],
        buffers_remaining: 5,
      };

      const routingRecords: RoutingRecord[] = transmissions
        .filter((t) => t.thread_decision)
        .map((t) => ({
          packet_id: t.id,
          thread_decision: (t.thread_decision ?? "unknown") as ThreadDecision,
          thread_id: t.thread_id,
          event_decision: (t.event_decision ?? "unknown") as EventDecision,
          event_id: t.event_id,
        }));

      const latestPacketId = transmissions.length > 0
        ? transmissions[transmissions.length - 1].id
        : null;

      const status = threads.length === 0 && transmissions.length === 0 ? "empty" : "ready";

      return { status, context, routingRecords, latestPacketId, error: null };
    }
    case "error":
      return { ...state, status: "error", error: action.error };
    default:
      return state;
  }
}

const POLL_INTERVAL = 3000;

export function useLiveData() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const activeRef = useRef(true);

  useEffect(() => {
    activeRef.current = true;

    const fetchAll = async () => {
      try {
        const [threadsRes, eventsRes, transmissionsRes] = await Promise.all([
          fetch(`${API_BASE}/api/live/threads`),
          fetch(`${API_BASE}/api/live/events`),
          fetch(`${API_BASE}/api/live/transmissions`),
        ]);

        if (!activeRef.current) return;

        if (!threadsRes.ok || !eventsRes.ok || !transmissionsRes.ok) return;

        const [threads, events, transmissions] = await Promise.all([
          threadsRes.json(),
          eventsRes.json(),
          transmissionsRes.json(),
        ]);

        if (!activeRef.current) return;

        dispatch({ type: "loaded", threads, events, transmissions });
      } catch {
        // Network error — API may not be up yet. Stay in current state and retry on next poll.
      }
    };

    fetchAll();
    const interval = setInterval(fetchAll, POLL_INTERVAL);

    return () => {
      activeRef.current = false;
      clearInterval(interval);
    };
  }, []);

  return state;
}
