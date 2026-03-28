export interface ReadyPacket {
  id: string;
  timestamp: string;
  text: string;
  metadata: Record<string, unknown>;
}

export type ThreadDecision = "new" | "existing" | "buffer" | "unknown";
export type EventDecision = "new" | "existing" | "none" | "unknown";

export interface Thread {
  thread_id: string;
  label: string;
  packets: ReadyPacket[];
  event_ids: string[];
  status: string;
}

export interface Event {
  event_id: string;
  label: string;
  opened_at: string;
  thread_ids: string[];
  status: string;
}

export interface RoutingRecord {
  packet_id: string;
  thread_decision: ThreadDecision;
  thread_id: string | null;
  event_decision: EventDecision;
  event_id: string | null;
}

export interface TRMContext {
  active_threads: Thread[];
  active_events: Event[];
  packets_to_resolve: ReadyPacket[];
  buffers_remaining: number;
}
