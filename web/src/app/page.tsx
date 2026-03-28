"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

const API_BASE = "http://localhost:8000";

export default function Home() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function startRun() {
    setLoading(true);
    setError(null);
    try {
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
      router.push(`/run/${data.run_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to start run");
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-base flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">TRM</h1>
        <p className="text-sm text-text-secondary">Thread Routing Module</p>
        <button
          onClick={startRun}
          disabled={loading}
          className="px-6 py-2.5 bg-accent-blue text-text-inverse font-mono text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? "Starting..." : "Start Run — scenario_02_interleaved"}
        </button>
        {error && <p className="text-accent-red text-sm">{error}</p>}
      </div>
    </div>
  );
}
