import { Badge } from "./Badge";
import { ThemeToggle } from "./ThemeToggle";

type RunStatus = "idle" | "connecting" | "running" | "complete" | "error";

interface TopBarProps {
  scenarioName: string | null;
  status: RunStatus;
  packetsRouted: number;
  totalPackets: number | null;
  buffersRemaining: number;
  speedFactor?: number | null;
  hideBuffers?: boolean;
}

const STATUS_CONFIG: Record<RunStatus, { label: string; color: string }> = {
  idle:       { label: "idle",       color: "#555568" },
  connecting: { label: "connecting", color: "#a855f7" },
  running:    { label: "running",    color: "#22c55e" },
  complete:   { label: "complete",   color: "#3b82f6" },
  error:      { label: "error",      color: "#ef4444" },
};

function StatGroup({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-text-muted font-mono uppercase tracking-[0.06em]">
        {label}
      </span>
      <span className="text-[13px] text-text-primary font-mono font-semibold">{value}</span>
    </div>
  );
}

function Divider() {
  return <div className="w-px h-4 bg-border" />;
}

export function TopBar({
  scenarioName,
  status,
  packetsRouted,
  totalPackets,
  buffersRemaining,
  speedFactor,
  hideBuffers,
}: TopBarProps) {
  const statusConfig = STATUS_CONFIG[status];
  const packetDisplay = totalPackets !== null
    ? `${packetsRouted}/${totalPackets}`
    : `${packetsRouted}`;

  return (
    <div className="sticky top-0 z-50 flex items-center justify-between px-5 py-3 border-b border-border bg-surface">
      <div className="flex items-center gap-3.5">
        <span className="text-sm font-bold text-text-primary tracking-tight">Albatross</span>
        <Divider />
        {scenarioName && (
          <span className="text-xs text-text-muted">{scenarioName}</span>
        )}
        <Badge color={statusConfig.color}>● {statusConfig.label}</Badge>
      </div>
      <div className="flex items-center gap-3">
        <StatGroup label="packets" value={packetDisplay} />
        {!hideBuffers && (
          <>
            <Divider />
            <StatGroup label="buffers" value={String(buffersRemaining)} />
          </>
        )}
        {speedFactor != null && (
          <>
            <Divider />
            <StatGroup label="speed" value={`${speedFactor}×`} />
          </>
        )}
        <Divider />
        <ThemeToggle />
      </div>
    </div>
  );
}
