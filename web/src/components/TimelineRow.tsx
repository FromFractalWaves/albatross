import type { ReadyPacket } from "@/types/trm";
import type { PacketDecisions } from "@/lib/packetDecisions";
import { DecisionBadge } from "./DecisionBadge";

interface TimelineRowProps {
  packet: ReadyPacket;
  threadColor: string;
  threadId: string;
  decisions?: PacketDecisions;
  isLatest: boolean;
}

export function TimelineRow({ packet, threadColor, threadId, decisions, isLatest }: TimelineRowProps) {
  const speaker = (packet.metadata?.speaker as string) ?? "unknown";
  const time = packet.timestamp.includes("T")
    ? packet.timestamp.split("T")[1]?.slice(0, 8)
    : packet.timestamp;

  return (
    <div
      className="px-3.5 py-2 flex items-center gap-2.5 transition-all duration-200 border-l-2"
      style={{
        borderColor: isLatest ? threadColor : "transparent",
        backgroundColor: isLatest ? `${threadColor}08` : "transparent",
      }}
    >
      <span className="text-[10px] font-mono text-text-muted w-[52px] shrink-0">{packet.id}</span>
      <div
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: threadColor }}
      />
      <span
        className="text-[11px] font-mono font-semibold w-[50px] shrink-0"
        style={{ color: threadColor }}
      >
        {speaker}
      </span>
      <span className="text-[10px] font-mono text-text-muted shrink-0">{time}</span>
      <span className="text-xs text-text-primary flex-1 truncate">{packet.text}</span>
      {decisions && (
        <div className="flex gap-1.5 shrink-0">
          <DecisionBadge decision={decisions.thread_decision} type="thr" />
          <DecisionBadge decision={decisions.event_decision} type="evt" />
        </div>
      )}
    </div>
  );
}
