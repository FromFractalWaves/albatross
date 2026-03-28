"use client";

import { useEffect, useReducer } from "react";
import type { ReadyPacket, RoutingRecord, TRMContext } from "@/types/trm";
import type { WSMessage } from "@/types/websocket";

const WS_BASE = "ws://localhost:8000";

export type RunStatus = "idle" | "connecting" | "running" | "complete" | "error";

interface RunState {
  status: RunStatus;
  context: TRMContext | null;
  routingRecords: RoutingRecord[];
  latestPacketId: string | null;
  incomingPacket: ReadyPacket | null;
  error: string | null;
  scenario: { tier: string; name: string } | null;
}

type Action =
  | { type: "connect" }
  | { type: "run_started"; scenario: { tier: string; name: string } }
  | { type: "packet_routed"; record: RoutingRecord; context: TRMContext; incomingPacket: ReadyPacket | null }
  | { type: "run_complete"; records: RoutingRecord[] }
  | { type: "run_error"; error: string }
  | { type: "ws_error" };

const initialState: RunState = {
  status: "idle",
  context: null,
  routingRecords: [],
  latestPacketId: null,
  incomingPacket: null,
  error: null,
  scenario: null,
};

function reducer(state: RunState, action: Action): RunState {
  switch (action.type) {
    case "connect":
      return { ...initialState, status: "connecting" };
    case "run_started":
      return { ...state, status: "running", scenario: action.scenario };
    case "packet_routed":
      return {
        ...state,
        context: action.context,
        routingRecords: [...state.routingRecords, action.record],
        latestPacketId: action.record.packet_id,
        incomingPacket: action.incomingPacket,
      };
    case "run_complete":
      return {
        ...state,
        status: "complete",
        routingRecords: action.records,
        latestPacketId: null,
        incomingPacket: null,
      };
    case "run_error":
      return { ...state, status: "error", error: action.error };
    case "ws_error":
      return { ...state, status: "error", error: "WebSocket connection error" };
    default:
      return state;
  }
}

export function useRunSocket(runId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    if (!runId) return;

    dispatch({ type: "connect" });
    const ws = new WebSocket(`${WS_BASE}/ws/runs/${runId}`);

    ws.onmessage = (event) => {
      const msg: WSMessage = JSON.parse(event.data);
      switch (msg.type) {
        case "run_started":
          dispatch({ type: "run_started", scenario: msg.scenario });
          break;
        case "packet_routed":
          dispatch({
            type: "packet_routed",
            record: msg.routing_record,
            context: msg.context,
            incomingPacket: msg.incoming_packet,
          });
          break;
        case "run_complete":
          dispatch({ type: "run_complete", records: msg.routing_records });
          break;
        case "run_error":
          dispatch({ type: "run_error", error: msg.error });
          break;
      }
    };

    ws.onerror = () => {
      dispatch({ type: "ws_error" });
    };

    return () => {
      ws.close();
    };
  }, [runId]);

  return state;
}
