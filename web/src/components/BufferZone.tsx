import type { ReadyPacket } from "@/types/trm";

interface BufferZoneProps {
  packets: ReadyPacket[];
}

export function BufferZone({ packets }: BufferZoneProps) {
  if (packets.length === 0) return null;

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        background: "linear-gradient(135deg, #f59e0b10, #f59e0b08)",
        border: "1px solid #f59e0b25",
      }}
    >
      {/* Header */}
      <div className="px-3.5 py-2.5 flex items-center gap-2">
        <span className="shrink-0 bg-accent-amber text-white text-[9px] font-bold font-mono px-1.5 py-0.5 rounded tracking-[0.06em]">
          BUFFERED
        </span>
        <span className="text-[11px] font-mono font-semibold text-text-secondary uppercase tracking-[0.08em]">
          Packets to Resolve
        </span>
        <span className="text-[10px] text-text-muted bg-elevated px-1.5 py-px rounded font-mono">
          {packets.length}
        </span>
      </div>

      {/* Buffered Packets */}
      <div>
        {packets.map((packet, i) => {
          const speaker = (packet.metadata?.speaker as string) ?? "unknown";
          const time = packet.timestamp.includes("T")
            ? packet.timestamp.split("T")[1]?.slice(0, 8)
            : packet.timestamp;

          return (
            <div
              key={packet.id}
              className={`px-3 py-2.5 border-l-2 ${i < packets.length - 1 ? "border-b border-border-subtle" : ""}`}
              style={{ borderLeftColor: "#f59e0b" }}
            >
              <div className="flex items-center gap-1.5 mb-1">
                <span className="text-[10px] font-mono text-text-muted">{packet.id}</span>
                <span className="text-[11px] font-semibold text-accent-amber">{speaker}</span>
                <span className="text-[10px] font-mono text-text-muted">{time}</span>
              </div>
              <p className="text-[13px] text-text-primary leading-[1.45] m-0">{packet.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
