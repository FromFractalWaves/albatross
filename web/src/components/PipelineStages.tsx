import type { StageState } from "@/hooks/useLiveData";

const STAGE_COLORS = [
  "var(--color-accent-blue)",
  "var(--color-accent-amber)",
  "var(--color-accent-purple)",
];

const MUTED_COLOR = "var(--color-text-muted)";
const ZERO_COLOR = "#3a3a55";

interface PipelineStagesProps {
  stages: StageState[];
}

export function PipelineStages({ stages }: PipelineStagesProps) {
  if (stages.length === 0) return null;

  return (
    <div
      className="flex flex-col border-b border-border"
      style={{ gap: 3, padding: "7px 16px", background: "#060610" }}
    >
      {stages.map((stage, idx) => {
        const color = STAGE_COLORS[idx] ?? MUTED_COLOR;
        const isZero = stage.count === 0;

        return (
          <div
            key={stage.id}
            className="flex items-baseline font-mono"
            style={{ gap: 10, fontSize: 11 }}
          >
            <span className="shrink-0" style={{ width: 110, color }}>
              [{stage.id}]
            </span>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: isZero ? ZERO_COLOR : color,
              }}
            >
              {stage.count}
            </span>
          </div>
        );
      })}
    </div>
  );
}
