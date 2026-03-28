import type { ReadyPacket } from "@/types/trm";

interface IncomingBannerProps {
  packet: ReadyPacket;
}

export function IncomingBanner({ packet }: IncomingBannerProps) {
  const speaker = (packet.metadata?.speaker as string) ?? "unknown";
  const time = packet.timestamp.includes("T")
    ? packet.timestamp.split("T")[1]?.slice(0, 8)
    : packet.timestamp;

  return (
    <div
      className="rounded-lg px-4 py-3.5 flex items-start gap-3"
      style={{
        background: "linear-gradient(135deg, #a855f710, #06b6d408)",
        border: "1px solid #a855f725",
      }}
    >
      <span className="shrink-0 mt-0.5 bg-accent-purple text-white text-[9px] font-bold font-mono px-1.5 py-0.5 rounded tracking-[0.06em]">
        ROUTING
      </span>
      <div className="flex-1">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[11px] font-mono font-semibold text-accent-purple">{packet.id}</span>
          <span className="text-xs font-semibold text-text-primary">{speaker}</span>
          <span className="text-[10px] font-mono text-text-muted">{time}</span>
        </div>
        <p className="text-[13px] text-text-primary leading-[1.45] m-0">{packet.text}</p>
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <div className="w-1.5 h-1.5 rounded-full bg-accent-purple animate-pulse-dot" />
        <span className="text-[10px] font-mono text-accent-purple">awaiting LLM</span>
      </div>
    </div>
  );
}
