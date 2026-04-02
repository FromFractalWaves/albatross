import type { ReadyPacket, RoutingRecord, TRMContext } from "./trm";

export interface RunStartedMessage {
  type: "run_started";
  run_id: string;
  scenario: { tier: string; name: string };
}

export interface PacketRoutedMessage {
  type: "packet_routed";
  packet_id: string;
  routing_record: RoutingRecord;
  context: TRMContext;
  incoming_packet: ReadyPacket | null;
}

export interface RunCompleteMessage {
  type: "run_complete";
  run_id: string;
  total_packets: number;
  routing_records: RoutingRecord[];
}

export interface RunErrorMessage {
  type: "run_error";
  run_id: string;
  error: string;
}

export type WSMessage =
  | RunStartedMessage
  | PacketRoutedMessage
  | RunCompleteMessage
  | RunErrorMessage;

// ── Live pipeline messages ──────────────────────────────────────────

export interface PipelineStartedMessage {
  type: "pipeline_started";
  total_packets: number;
}

export interface PacketCapturedMessage {
  type: "packet_captured";
  packet_id: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface PacketPreprocessedMessage {
  type: "packet_preprocessed";
  packet_id: string;
  text: string;
}

export interface LivePacketRoutedMessage {
  type: "packet_routed";
  packet_id: string;
  routing_record: RoutingRecord;
  context: TRMContext;
  incoming_packet: ReadyPacket | null;
}

export interface PipelineCompleteMessage {
  type: "pipeline_complete";
  total_packets: number;
  routing_records: RoutingRecord[];
}

export interface PipelineErrorMessage {
  type: "pipeline_error";
  error: string;
}

export type LiveWSMessage =
  | PipelineStartedMessage
  | PacketCapturedMessage
  | PacketPreprocessedMessage
  | LivePacketRoutedMessage
  | PipelineCompleteMessage
  | PipelineErrorMessage;
