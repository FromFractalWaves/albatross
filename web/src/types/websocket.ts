import type { RoutingRecord, TRMContext } from "./trm";

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
