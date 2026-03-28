import type { RoutingRecord } from "@/types/trm";

export interface PacketDecisions {
  thread_decision: string;
  event_decision: string;
  thread_id: string | null;
  event_id: string | null;
}

export function buildDecisionMap(records: RoutingRecord[]): Map<string, PacketDecisions> {
  const map = new Map<string, PacketDecisions>();
  for (const r of records) {
    map.set(r.packet_id, {
      thread_decision: r.thread_decision,
      event_decision: r.event_decision,
      thread_id: r.thread_id,
      event_id: r.event_id,
    });
  }
  return map;
}
