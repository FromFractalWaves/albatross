import type { Thread } from "@/types/trm";
import type { PacketDecisions } from "@/lib/packetDecisions";
import { Badge } from "./Badge";
import { PacketCard } from "./PacketCard";

interface ThreadLaneProps {
  thread: Thread;
  color: string;
  latestPacketId: string | null;
  decisionMap: Map<string, PacketDecisions>;
}

export function ThreadLane({ thread, color, latestPacketId, decisionMap }: ThreadLaneProps) {
  return (
    <div className="flex-1 min-w-[340px] bg-surface rounded-lg border border-border overflow-hidden flex flex-col">
      {/* Header */}
      <div className="px-3.5 py-3 border-b border-border-subtle flex items-start gap-2.5">
        <div
          className="w-2 h-2 rounded-full mt-1 shrink-0"
          style={{
            backgroundColor: color,
            boxShadow: `0 0 8px ${color}40`,
          }}
        />
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[11px] font-mono font-semibold" style={{ color }}>
              {thread.thread_id}
            </span>
            <Badge variant="outline">{thread.status}</Badge>
          </div>
          <span className="text-xs text-text-secondary leading-[1.4]">{thread.label}</span>
        </div>
        <span className="text-[10px] font-mono text-text-muted bg-elevated px-1.5 py-0.5 rounded">
          {thread.packets.length} pkts
        </span>
      </div>

      {/* Packets */}
      <div className="flex-1 overflow-auto">
        {thread.packets.map((packet, i) => (
          <div
            key={packet.id}
            className={i < thread.packets.length - 1 ? "border-b border-border-subtle" : ""}
          >
            <PacketCard
              packet={packet}
              threadColor={color}
              isLatest={packet.id === latestPacketId}
              decisions={decisionMap.get(packet.id)}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
