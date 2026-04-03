"use client";

import { use, useCallback, useEffect, useMemo, useState } from "react";
import { useLiveData } from "@/hooks/useLiveData";
import { API_BASE } from "@/lib/api";
import { buildThreadColorMap } from "@/lib/threadColors";
import { buildDecisionMap } from "@/lib/packetDecisions";
import { TopBar } from "@/components/TopBar";
import { ThreadLane } from "@/components/ThreadLane";
import { EventCard } from "@/components/EventCard";
import { TimelineRow } from "@/components/TimelineRow";
import { SectionHeader } from "@/components/SectionHeader";
import { TabBar } from "@/components/TabBar";
import { ContextInspector } from "@/components/ContextInspector";
import { PipelineStages } from "@/components/PipelineStages";

type Tab = "live" | "events" | "timeline";

const sourceLabels: Record<string, string> = {
  mock: "Mock Pipeline",
};

export default function LivePage({
  params,
}: {
  params: Promise<{ source: string }>;
}) {
  const { source } = use(params);
  const { status, context, routingRecords, latestPacketId, incomingPacket, stages } = useLiveData();

  const [activeTab, setActiveTab] = useState<Tab>("live");
  const [pipelineStatus, setPipelineStatus] = useState<"running" | "stopped" | "unknown">("unknown");
  const [pipelineLoading, setPipelineLoading] = useState(false);

  const sourceLabel = sourceLabels[source] ?? source;

  useEffect(() => {
    if (source !== "mock") return;
    let active = true;
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/mock/status`);
        const data = await res.json();
        if (active) setPipelineStatus(data.status);
      } catch {
        if (active) setPipelineStatus("unknown");
      }
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => { active = false; clearInterval(id); };
  }, [source]);

  const startPipeline = useCallback(async () => {
    setPipelineLoading(true);
    try {
      await fetch(`${API_BASE}/api/mock/start`, { method: "POST" });
      setPipelineStatus("running");
    } catch { /* ignore */ }
    setPipelineLoading(false);
  }, []);

  const stopPipeline = useCallback(async () => {
    setPipelineLoading(true);
    try {
      await fetch(`${API_BASE}/api/mock/stop`, { method: "POST" });
      setPipelineStatus("stopped");
    } catch { /* ignore */ }
    setPipelineLoading(false);
  }, []);

  const threadColorMap = useMemo(
    () => buildThreadColorMap(context?.active_threads.map((t) => t.thread_id) ?? []),
    [context?.active_threads]
  );

  const decisionMap = useMemo(() => buildDecisionMap(routingRecords), [routingRecords]);

  const timelinePackets = useMemo(() => {
    if (!context?.active_threads) return [];
    const all: { packet: (typeof context.active_threads)[0]["packets"][0]; threadId: string }[] = [];
    for (const thread of context.active_threads) {
      for (const packet of thread.packets) {
        all.push({ packet, threadId: thread.thread_id });
      }
    }
    all.sort((a, b) => {
      const numA = parseInt(a.packet.id.replace(/\D/g, ""), 10) || 0;
      const numB = parseInt(b.packet.id.replace(/\D/g, ""), 10) || 0;
      return numA - numB;
    });
    return all;
  }, [context?.active_threads]);

  const topBarStatus = status === "ready" || status === "empty" ? "running" : status === "loading" ? "connecting" : "error";

  const tabs: { id: Tab; label: string; disabled: boolean }[] = [
    { id: "live", label: "LIVE", disabled: false },
    { id: "events", label: "EVENTS", disabled: false },
    { id: "timeline", label: "TIMELINE", disabled: false },
  ];

  return (
    <div className="min-h-screen bg-base">
      <TopBar
        scenarioName={`Live — ${sourceLabel}`}
        status={topBarStatus}
        packetsRouted={routingRecords.length}
        totalPackets={null}
        buffersRemaining={context?.buffers_remaining ?? 5}
        speedFactor={null}
        hideBuffers
      />

      <PipelineStages stages={stages} />

      <div className="flex flex-col gap-3.5 p-4 px-5">
        {/* Pipeline Controls (mock source only) */}
        {source === "mock" && (
          <div className="flex items-center gap-3 px-1">
            <div className="flex items-center gap-1.5">
              <span
                className={`inline-block w-2 h-2 rounded-full ${
                  pipelineStatus === "running" ? "bg-accent-green animate-pulse-dot" : "bg-text-muted"
                }`}
              />
              <span className="text-[11px] font-mono uppercase tracking-[0.06em] text-text-muted">
                Pipeline {pipelineStatus}
              </span>
            </div>
            <button
              onClick={startPipeline}
              disabled={pipelineLoading || pipelineStatus === "running"}
              className="px-3 py-1 text-[11px] font-mono font-semibold uppercase tracking-[0.06em] rounded bg-accent-green/15 text-accent-green hover:bg-accent-green/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Start Mock Pipeline
            </button>
            <button
              onClick={stopPipeline}
              disabled={pipelineLoading || pipelineStatus === "stopped"}
              className="px-3 py-1 text-[11px] font-mono font-semibold uppercase tracking-[0.06em] rounded bg-accent-red/15 text-accent-red hover:bg-accent-red/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Stop
            </button>
          </div>
        )}

        {/* Tab Bar */}
        <TabBar
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as Tab)}
        />

        {/* Loading state */}
        {status === "loading" && (
          <div className="text-text-muted text-sm px-1">Loading pipeline state...</div>
        )}

        {/* LIVE tab content */}
        <div className={activeTab === "live" ? "" : "hidden"}>
          {context?.active_threads.length ? (
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
          ) : (
            <div className="text-text-muted text-sm px-1">No data yet. Start the pipeline to begin.</div>
          )}
        </div>

        {/* EVENTS tab content */}
        <div className={activeTab === "events" ? "" : "hidden"}>
          {context?.active_events.length ? (
            <div className="flex flex-col gap-3.5 max-w-[600px]">
              {context.active_events.map((event) => (
                <EventCard
                  key={event.event_id}
                  event={event}
                  threadColorMap={threadColorMap}
                />
              ))}
            </div>
          ) : (
            <div className="text-text-muted text-sm px-1">No events yet.</div>
          )}
        </div>

        {/* TIMELINE tab content */}
        <div className={activeTab === "timeline" ? "" : "hidden"}>
          {timelinePackets.length ? (
            <div className="bg-surface rounded-lg border border-border overflow-hidden">
              <SectionHeader title="Timeline" count={timelinePackets.length} />
              <div className="divide-y divide-border-subtle">
                {timelinePackets.map(({ packet, threadId }) => (
                  <TimelineRow
                    key={packet.id}
                    packet={packet}
                    threadColor={threadColorMap.get(threadId) ?? "#3b82f6"}
                    threadId={threadId}
                    decisions={decisionMap.get(packet.id)}
                    isLatest={packet.id === latestPacketId}
                  />
                ))}
              </div>
            </div>
          ) : (
            <div className="text-text-muted text-sm px-1">No transmissions yet.</div>
          )}
        </div>

        {/* Context Inspector */}
        <ContextInspector context={context} incomingPacket={incomingPacket} />
      </div>
    </div>
  );
}
