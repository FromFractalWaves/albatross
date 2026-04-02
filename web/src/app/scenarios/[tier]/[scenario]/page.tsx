"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { HubTopBar } from "@/components/HubTopBar";
import { Badge } from "@/components/Badge";
import { SectionHeader } from "@/components/SectionHeader";
import type { ScenarioDetail } from "@/types/scenarios";

export default function ScenarioDetailPage({
  params,
}: {
  params: Promise<{ tier: string; scenario: string }>;
}) {
  const { tier, scenario } = use(params);
  const router = useRouter();

  const [detail, setDetail] = useState<ScenarioDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [speedFactor, setSpeedFactor] = useState(20);
  const [bufferCount, setBufferCount] = useState(5);
  const [running, setRunning] = useState(false);
  const [expectedOpen, setExpectedOpen] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/scenarios/${tier}/${scenario}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Scenario not found (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setDetail(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(e instanceof Error ? e.message : "Failed to load scenario");
        setLoading(false);
      });
  }, [tier, scenario]);

  async function handleRun() {
    setRunning(true);
    try {
      const res = await fetch(`${API_BASE}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source: "scenario",
          tier,
          scenario,
          speed_factor: speedFactor,
          buffer_count: bufferCount,
        }),
      });
      const data = await res.json();
      router.push(`/run/${data.run_id}`);
    } catch {
      setError("Failed to start run");
      setRunning(false);
    }
  }

  return (
    <div className="min-h-screen bg-base">
      <HubTopBar />

      <div className="max-w-4xl mx-auto px-5 py-4 flex flex-col gap-4">
        {/* Back link */}
        <Link
          href="/trm"
          className="text-[11px] font-mono uppercase tracking-[0.06em] text-text-muted hover:text-text-secondary transition-colors"
        >
          ← Back to Scenarios
        </Link>

        {loading && (
          <div className="text-text-muted text-sm">Loading...</div>
        )}

        {error && (
          <div className="text-accent-red text-sm">Error: {error}</div>
        )}

        {detail && (
          <>
            {/* Title */}
            <div className="flex items-center gap-2.5">
              <h1 className="text-lg font-bold text-text-primary font-mono">
                {detail.name}
              </h1>
              <Badge color="#a855f7">{detail.tier.replace(/_/g, " ")}</Badge>
            </div>

            {/* README */}
            <div className="bg-surface rounded-lg border border-border overflow-hidden">
              <SectionHeader title="README" />
              <div className="px-4 py-3">
                {detail.readme ? (
                  <pre className="whitespace-pre-wrap text-[13px] text-text-secondary font-mono leading-relaxed m-0">
                    {detail.readme}
                  </pre>
                ) : (
                  <span className="text-text-muted text-sm">No README available.</span>
                )}
              </div>
            </div>

            {/* Packets */}
            <div className="bg-surface rounded-lg border border-border overflow-hidden">
              <SectionHeader title="Packets" count={detail.packets.length} />
              <div>
                {detail.packets.map((pkt, i) => {
                  const speaker = (pkt.metadata?.speaker as string) ?? "unknown";
                  const time = pkt.timestamp.includes("T")
                    ? pkt.timestamp.split("T")[1]?.slice(0, 8)
                    : pkt.timestamp;
                  const truncText =
                    pkt.text.length > 120
                      ? pkt.text.slice(0, 120) + "…"
                      : pkt.text;

                  return (
                    <div
                      key={pkt.id}
                      className={`px-3.5 py-2.5 ${
                        i < detail.packets.length - 1 ? "border-b border-border-subtle" : ""
                      }`}
                    >
                      <div className="flex items-center gap-1.5 mb-1">
                        <span className="text-[10px] font-mono text-text-muted">{pkt.id}</span>
                        <span className="text-[11px] font-semibold text-accent-cyan">{speaker}</span>
                        <span className="text-[10px] font-mono text-text-muted">{time}</span>
                      </div>
                      <p className="text-[13px] text-text-primary leading-[1.45] m-0">
                        {truncText}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Expected Output */}
            {detail.expected_output && (
              <div className="bg-surface rounded-lg border border-border overflow-hidden">
                <SectionHeader
                  title="Expected Output"
                  action={
                    <button
                      onClick={() => setExpectedOpen(!expectedOpen)}
                      className="text-[10px] font-mono text-text-muted hover:text-text-secondary transition-colors"
                    >
                      {expectedOpen ? "HIDE" : "SHOW"}
                    </button>
                  }
                />
                {expectedOpen && (
                  <pre className="text-[11px] font-mono text-text-secondary bg-base p-3 leading-[1.6] overflow-x-auto m-0 whitespace-pre-wrap max-h-[400px] overflow-y-auto">
                    {JSON.stringify(detail.expected_output, null, 2)}
                  </pre>
                )}
              </div>
            )}

            {/* Run Configuration */}
            <div className="bg-surface rounded-lg border border-border overflow-hidden">
              <SectionHeader title="Run Configuration" />
              <div className="flex gap-6 px-4 py-3">
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] font-mono uppercase text-text-muted tracking-[0.06em]">
                    Speed Factor
                  </span>
                  <input
                    type="number"
                    value={speedFactor}
                    onChange={(e) => setSpeedFactor(Number(e.target.value))}
                    min={1}
                    step={1}
                    className="bg-base border border-border rounded px-3 py-1.5 text-[13px] font-mono text-text-primary w-24 focus:border-accent-blue focus:outline-none"
                  />
                </label>
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] font-mono uppercase text-text-muted tracking-[0.06em]">
                    Buffer Count
                  </span>
                  <input
                    type="number"
                    value={bufferCount}
                    onChange={(e) => setBufferCount(Number(e.target.value))}
                    min={1}
                    max={10}
                    step={1}
                    className="bg-base border border-border rounded px-3 py-1.5 text-[13px] font-mono text-text-primary w-24 focus:border-accent-blue focus:outline-none"
                  />
                </label>
              </div>
              <div className="px-4 pb-3">
                <button
                  onClick={handleRun}
                  disabled={running}
                  className="w-full px-6 py-2.5 bg-accent-blue text-text-inverse font-mono text-sm font-semibold rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {running ? "Starting..." : "Run This Scenario"}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
