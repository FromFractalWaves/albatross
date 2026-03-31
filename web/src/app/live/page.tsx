"use client";

import { useMemo, useState } from "react";
import { useLiveData } from "@/hooks/useLiveData";
import { buildThreadColorMap } from "@/lib/threadColors";
import { buildDecisionMap } from "@/lib/packetDecisions";
import { TopBar } from "@/components/TopBar";
import { ThreadLane } from "@/components/ThreadLane";
import { EventCard } from "@/components/EventCard";
import { TimelineRow } from "@/components/TimelineRow";
import { SectionHeader } from "@/components/SectionHeader";
import { TabBar } from "@/components/TabBar";
import { ContextInspector } from "@/components/ContextInspector";

type Tab = "live" | "events" | "timeline";

export default function LivePage() {
  const { status, context, routingRecords, latestPacketId, error } = useLiveData();

  const [activeTab, setActiveTab] = useState<Tab>("live");

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
        scenarioName="Live Pipeline"
        status={topBarStatus}
        packetsRouted={routingRecords.length}
        totalPackets={null}
        buffersRemaining={context?.buffers_remaining ?? 5}
        speedFactor={null}
      />

      <div className="flex flex-col gap-3.5 p-4 px-5">
        {/* Tab Bar */}
        <TabBar
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as Tab)}
        />

        {/* Error display */}
        {error && (
          <div className="text-accent-red text-sm px-1">Error: {error}</div>
        )}

        {/* Loading state */}
        {status === "loading" && (
          <div className="text-text-muted text-sm px-1">Loading pipeline state...</div>
        )}

        {/* Empty state */}
        {status === "empty" && (
          <div className="text-text-muted text-sm px-1">
            No routed packets yet. Start the pipeline to see data here.
          </div>
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
          ) : null}
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
            <div className="text-text-muted text-sm px-1">No packets routed yet.</div>
          )}
        </div>

        {/* Context Inspector */}
        <ContextInspector context={context} incomingPacket={null} />
      </div>
    </div>
  );
}
