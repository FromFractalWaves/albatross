"use client";

import { use, useMemo, useState } from "react";
import { useRunSocket } from "@/hooks/useRunSocket";
import { buildThreadColorMap } from "@/lib/threadColors";
import { buildDecisionMap } from "@/lib/packetDecisions";
import { TopBar } from "@/components/TopBar";
import { IncomingBanner } from "@/components/IncomingBanner";
import { ThreadLane } from "@/components/ThreadLane";
import { ContextInspector } from "@/components/ContextInspector";

type Tab = "live" | "events" | "timeline";

export default function RunPage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = use(params);
  const { status, context, routingRecords, latestPacketId, incomingPacket, error, scenario } =
    useRunSocket(runId);

  const [activeTab, setActiveTab] = useState<Tab>("live");

  const threadColorMap = useMemo(
    () => buildThreadColorMap(context?.active_threads.map((t) => t.thread_id) ?? []),
    [context?.active_threads]
  );

  const decisionMap = useMemo(() => buildDecisionMap(routingRecords), [routingRecords]);

  const totalPackets = status === "complete" ? routingRecords.length : null;
  const scenarioName = scenario ? `${scenario.tier}/${scenario.name}` : null;

  const tabs: { id: Tab; label: string; disabled: boolean }[] = [
    { id: "live", label: "LIVE", disabled: false },
    { id: "events", label: "EVENTS", disabled: true },
    { id: "timeline", label: "TIMELINE", disabled: true },
  ];

  return (
    <div className="min-h-screen bg-base">
      <TopBar
        scenarioName={scenarioName}
        status={status}
        packetsRouted={routingRecords.length}
        totalPackets={totalPackets}
        buffersRemaining={context?.buffers_remaining ?? 5}
        speedFactor={20}
      />

      <div className="flex flex-col gap-3.5 p-4 px-5">
        {/* Incoming Banner */}
        {incomingPacket && status === "running" && (
          <IncomingBanner packet={incomingPacket} />
        )}

        {/* Tab Bar */}
        <div className="flex gap-0.5">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => !tab.disabled && setActiveTab(tab.id)}
              disabled={tab.disabled}
              className={`px-3.5 py-1.5 text-[11px] font-semibold font-mono uppercase tracking-[0.06em] rounded-[5px] border-none transition-all duration-150 ${
                activeTab === tab.id
                  ? "bg-elevated text-text-primary"
                  : tab.disabled
                    ? "text-text-muted opacity-50 cursor-not-allowed"
                    : "text-text-muted cursor-pointer hover:text-text-secondary"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* LIVE tab content */}
        {activeTab === "live" && (
          <>
            {error && (
              <div className="text-accent-red text-sm px-1">Error: {error}</div>
            )}

            {status === "idle" || status === "connecting" ? (
              <div className="text-text-muted text-sm px-1">
                {status === "idle" ? "Waiting for run to start..." : "Connecting..."}
              </div>
            ) : context?.active_threads.length ? (
              <div className="flex flex-wrap gap-3.5 items-start">
                {context.active_threads.map((thread) => (
                  <ThreadLane
                    key={thread.thread_id}
                    thread={thread}
                    color={threadColorMap.get(thread.thread_id) ?? "#3b82f6"}
                    latestPacketId={latestPacketId}
                    decisionMap={decisionMap}
                  />
                ))}
              </div>
            ) : null}
          </>
        )}

        {/* Context Inspector */}
        <ContextInspector context={context} incomingPacket={incomingPacket} />
      </div>
    </div>
  );
}
