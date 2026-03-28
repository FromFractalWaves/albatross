"use client";

import { useState } from "react";
import { useRunSocket } from "@/hooks/useRunSocket";

const API_BASE = "http://localhost:8000";

export default function Home() {
  const [runId, setRunId] = useState<string | null>(null);
  const { status, context, routingRecords, error, scenario } =
    useRunSocket(runId);

  const isActive = status === "connecting" || status === "running";

  async function startRun() {
    const res = await fetch(`${API_BASE}/api/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: "scenario",
        tier: "tier_one",
        scenario: "scenario_02_interleaved",
        speed_factor: 20.0,
      }),
    });
    const data = await res.json();
    setRunId(data.run_id);
  }

  return (
    <div>
      <h1>TRM — Raw WebSocket View</h1>

      <button onClick={startRun} disabled={isActive}>
        {isActive ? "Run in progress..." : "Start Run"}
      </button>

      <p>
        <strong>Status:</strong> {status}
        {scenario && (
          <>
            {" "}
            | <strong>Scenario:</strong> {scenario.tier}/{scenario.name}
          </>
        )}
        {" "}| <strong>Packets routed:</strong> {routingRecords.length}
      </p>

      {error && (
        <p style={{ color: "red" }}>
          <strong>Error:</strong> {error}
        </p>
      )}

      {routingRecords.length > 0 && (
        <div>
          <h2>Latest Routing Record</h2>
          <pre>
            {JSON.stringify(routingRecords[routingRecords.length - 1], null, 2)}
          </pre>
        </div>
      )}

      {context && (
        <div>
          <h2>TRM Context</h2>
          <pre>{JSON.stringify(context, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
