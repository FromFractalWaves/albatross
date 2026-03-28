import type { ReadyPacket } from "@/types/trm";
import type { PacketDecisions } from "@/lib/packetDecisions";
import { DecisionBadge } from "./DecisionBadge";

interface PacketCardProps {
  packet: ReadyPacket;
  threadColor: string;
  isLatest: boolean;
  decisions?: PacketDecisions;
}

export function PacketCard({ packet, threadColor, isLatest, decisions }: PacketCardProps) {
  const speaker = (packet.metadata?.speaker as string) ?? "unknown";
  const time = packet.timestamp.includes("T")
    ? packet.timestamp.split("T")[1]?.slice(0, 8)
    : packet.timestamp;

  return (
    <div
      className="px-3 py-2.5 transition-all duration-200 border-l-2"
      style={{
        borderColor: isLatest ? threadColor : "transparent",
        backgroundColor: isLatest ? `${threadColor}08` : "transparent",
      }}
    >
      <div className="flex items-center gap-1.5 mb-1">
        <span className="text-[10px] font-mono text-text-muted">{packet.id}</span>
        <span className="text-[11px] font-semibold" style={{ color: threadColor }}>
          {speaker}
        </span>
        <span className="text-[10px] font-mono text-text-muted">{time}</span>
      </div>
      <p className="text-[13px] text-text-primary leading-[1.45] m-0 mb-1.5">{packet.text}</p>
      {decisions && (
        <div className="flex gap-1.5">
          <DecisionBadge decision={decisions.thread_decision} type="thr" />
          <DecisionBadge decision={decisions.event_decision} type="evt" />
        </div>
      )}
    </div>
  );
}
