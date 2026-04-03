"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type {
  Thread,
  Event,
  ReadyPacket,
  RoutingRecord,
  TRMContext,
} from "@/types/trm";
import type { ThreadDecision, EventDecision } from "@/types/trm";
import type { LiveWSMessage, PipelineStageDefinition } from "@/types/websocket";
import { API_BASE, WS_BASE } from "@/lib/api";

export type LiveStatus = "loading" | "connecting" | "running" | "ready" | "empty" | "error";

export type StageState = PipelineStageDefinition & { count: number };

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

// ── Fetchers ────────────────────────────────────────────────────────

async function fetchThreads(): Promise<Thread[]> {
  const res = await fetch(`${API_BASE}/api/live/threads`);
  if (!res.ok) throw new Error("Failed to fetch threads");
  return res.json();
}

async function fetchEvents(): Promise<Event[]> {
  const res = await fetch(`${API_BASE}/api/live/events`);
  if (!res.ok) throw new Error("Failed to fetch events");
  return res.json();
}

async function fetchTransmissions(): Promise<TransmissionRow[]> {
  const res = await fetch(`${API_BASE}/api/live/transmissions`);
  if (!res.ok) throw new Error("Failed to fetch transmissions");
  return res.json();
}

// ── Hook ────────────────────────────────────────────────────────────

export function useLiveData() {
  const queryClient = useQueryClient();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [wsConnected, setWsConnected] = useState(false);
  const [incomingPacket, setIncomingPacket] = useState<ReadyPacket | null>(null);
  const [wsError, setWsError] = useState<string | null>(null);
  const [stages, setStages] = useState<StageState[]>([]);

  // Hydration queries — fetch on mount, stale after 30s
  const threads = useQuery({
    queryKey: ["live", "threads"],
    queryFn: fetchThreads,
    refetchInterval: wsConnected ? false : 5000,
    retry: false,
  });

  const events = useQuery({
    queryKey: ["live", "events"],
    queryFn: fetchEvents,
    refetchInterval: wsConnected ? false : 5000,
    retry: false,
  });

  const transmissions = useQuery({
    queryKey: ["live", "transmissions"],
    queryFn: fetchTransmissions,
    refetchInterval: wsConnected ? false : 5000,
    retry: false,
  });

  // ── WebSocket connection ────────────────────────────────────────

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(`${WS_BASE}/ws/live/mock`);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      setWsError(null);
    };

    ws.onmessage = (event) => {
      const msg: LiveWSMessage = JSON.parse(event.data);

      const incrementStage = (messageType: string) => {
        setStages((prev) =>
          prev.map((s) =>
            s.message_type === messageType ? { ...s, count: s.count + 1 } : s,
          ),
        );
      };

      switch (msg.type) {
        case "pipeline_started":
          setStages(msg.stages.map((s) => ({ ...s, count: 0 })));
          break;

        case "packet_captured":
        case "packet_preprocessed":
          incrementStage(msg.type);
          break;

        case "packet_routed": {
          incrementStage(msg.type);
          // Update context directly from the message
          const ctx = msg.context as TRMContext;
          queryClient.setQueryData(["live", "threads"], ctx.active_threads);
          queryClient.setQueryData(["live", "events"], ctx.active_events);

          // Append to transmissions cache
          queryClient.setQueryData<TransmissionRow[]>(
            ["live", "transmissions"],
            (prev) => {
              const row: TransmissionRow = {
                id: msg.routing_record.packet_id,
                timestamp: "",
                text: "",
                status: "routed",
                thread_id: msg.routing_record.thread_id ?? null,
                event_id: msg.routing_record.event_id ?? null,
                thread_decision: msg.routing_record.thread_decision,
                event_decision: msg.routing_record.event_decision,
                metadata: {},
              };
              return [...(prev ?? []), row];
            },
          );

          setIncomingPacket(msg.incoming_packet);
          break;
        }

        case "pipeline_complete":
          // Re-fetch everything from DB for final consistency
          queryClient.invalidateQueries({ queryKey: ["live"] });
          setIncomingPacket(null);
          break;

        case "pipeline_error":
          setWsError(msg.error);
          break;
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      // Reconnect after 2s
      reconnectTimer.current = setTimeout(connect, 2000);
    };

    ws.onerror = () => {
      // onclose will fire after this
    };
  }, [queryClient]);

  useEffect(() => {
    connect();

    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);

  // ── Derive state ────────────────────────────────────────────────

  const context: TRMContext | null = useMemo(() => {
    const t = threads.data;
    const e = events.data;
    if (!t && !e) return null;
    return {
      active_threads: t ?? [],
      active_events: e ?? [],
      packets_to_resolve: [],
      buffers_remaining: 5,
    };
  }, [threads.data, events.data]);

  const routingRecords: RoutingRecord[] = useMemo(() => {
    const tx = transmissions.data;
    if (!tx) return [];
    return tx
      .filter((t) => t.thread_decision)
      .map((t) => ({
        packet_id: t.id,
        thread_decision: (t.thread_decision ?? "unknown") as ThreadDecision,
        thread_id: t.thread_id,
        event_decision: (t.event_decision ?? "unknown") as EventDecision,
        event_id: t.event_id,
      }));
  }, [transmissions.data]);

  const latestPacketId = useMemo(() => {
    const tx = transmissions.data;
    if (!tx || tx.length === 0) return null;
    return tx[tx.length - 1].id;
  }, [transmissions.data]);

  // Status derivation
  const isLoading = threads.isLoading || events.isLoading || transmissions.isLoading;
  const hasError = threads.isError || events.isError || transmissions.isError || wsError !== null;
  const isEmpty =
    !isLoading &&
    (threads.data?.length ?? 0) === 0 &&
    (transmissions.data?.length ?? 0) === 0;

  let status: LiveStatus;
  if (hasError) status = "error";
  else if (isLoading) status = "loading";
  else if (isEmpty) status = "empty";
  else status = "ready";

  return {
    status,
    context,
    routingRecords,
    latestPacketId,
    incomingPacket,
    stages,
    error: wsError ?? threads.error?.message ?? events.error?.message ?? transmissions.error?.message ?? null,
  };
}
