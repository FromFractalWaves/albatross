export interface ScenarioSummary {
  name: string;
  path: string;
}

export interface TierGroup {
  tier: string;
  scenarios: ScenarioSummary[];
}

export interface ScenarioDetail {
  tier: string;
  name: string;
  readme: string | null;
  packets: ScenarioPacket[];
  expected_output: ExpectedOutput | null;
}

export interface ScenarioPacket {
  id: string;
  timestamp: string;
  text: string;
  metadata: Record<string, unknown>;
}

export interface ExpectedOutput {
  threads: unknown[];
  events: unknown[];
  routing_records: unknown[];
}
