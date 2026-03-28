import { Badge } from "./Badge";

const DECISION_CONFIG: Record<string, { icon: string; color: string }> = {
  new:      { icon: "+", color: "#22c55e" },
  existing: { icon: "→", color: "#3b82f6" },
  none:     { icon: "–", color: "#555568" },
  buffer:   { icon: "◷", color: "#f59e0b" },
  unknown:  { icon: "?", color: "#ef4444" },
};

interface DecisionBadgeProps {
  decision: string;
  type: "thr" | "evt";
}

export function DecisionBadge({ decision, type }: DecisionBadgeProps) {
  const config = DECISION_CONFIG[decision] || DECISION_CONFIG.unknown;
  return (
    <Badge color={config.color}>
      <span className="text-[10px]">{config.icon}</span>
      {type}:{decision}
    </Badge>
  );
}
