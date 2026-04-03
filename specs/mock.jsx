/**
 * Pipeline Observability — UI Mockup
 *
 * Shows Option B: compact pipeline strip between top bar and pipeline controls.
 * Renders three states: stopped, mid-run, complete.
 *
 * Mock data uses the existing mock pipeline stages:
 *   Capture → Preprocessing → TRM Routing
 *
 * To view: paste into the interactive mockup at docs/web/ui_mockup.jsx,
 * or open in any React sandbox with Tailwind available.
 */

// ─── Design Tokens (mirrors tokens in ui_mockup.jsx) ────────
const tokens = {
  bg: {
    base: "#0a0a0f",
    surface: "#111118",
    elevated: "#1a1a24",
    border: "#2a2a38",
    borderSubtle: "#1e1e2a",
  },
  text: {
    primary: "#e4e4ed",
    secondary: "#8888a0",
    muted: "#555568",
  },
  accent: {
    blue: "#3b82f6",
    amber: "#f59e0b",
    green: "#22c55e",
    red: "#ef4444",
    purple: "#a855f7",
  },
};

// ─── Mock pipeline stage definitions ────────────────────────
// This is the shape that comes from pipeline_started.stages
// and from GET /api/mock/status { stages: [...] }
const MOCK_STAGES = [
  { id: "capture",       label: "Capture",       message_type: "packet_captured" },
  { id: "preprocessing", label: "Preprocessing",  message_type: "packet_preprocessed" },
  { id: "routing",       label: "TRM Routing",    message_type: "packet_routed" },
];

// ─── Three demo states ───────────────────────────────────────
const STATES = {
  stopped: {
    label: "Stopped",
    pipelineStatus: "stopped",
    total: 12,
    counts: { capture: 0, preprocessing: 0, routing: 0 },
  },
  running: {
    label: "Mid-run",
    pipelineStatus: "running",
    total: 12,
    counts: { capture: 12, preprocessing: 7, routing: 5 },
  },
  complete: {
    label: "Complete",
    pipelineStatus: "stopped",
    total: 12,
    counts: { capture: 12, preprocessing: 12, routing: 12 },
  },
};

// ─── Stage state derivation ──────────────────────────────────
// Given counts and pipeline status, derive per-stage visual state.
// Logic the PipelineStages component will use:
//   done   — count === total
//   active — count < total AND pipeline is running AND prior stage has packets
//   idle   — everything else
function deriveStageState(stageId, counts, total, pipelineStatus, stages) {
  const count = counts[stageId] ?? 0;
  if (total > 0 && count >= total) return "done";
  if (pipelineStatus === "running") {
    const idx = stages.findIndex((s) => s.id === stageId);
    // first stage is always active when running (unless done)
    if (idx === 0) return "active";
    // subsequent stages are active if the previous stage has started
    const prevId = stages[idx - 1]?.id;
    if (prevId && (counts[prevId] ?? 0) > 0) return "active";
  }
  return "idle";
}

// ─── PipelineStrip component ─────────────────────────────────
// This is the component to build: web/src/components/PipelineStages.tsx
// Receives: stages (from API), counts (from useLiveData), total, pipelineStatus
// Renders nothing if stages is empty — safe to drop in unconditionally.
function PipelineStrip({ stages, counts, total, pipelineStatus }) {
  if (!stages || stages.length === 0) return null;

  const dotStyle = (state) => ({
    width: 6,
    height: 6,
    borderRadius: "50%",
    flexShrink: 0,
    background:
      state === "done"
        ? tokens.accent.green
        : state === "active"
        ? tokens.accent.purple
        : "#3a3a50",
    animation: state === "active" ? "pulse-dot 1.4s ease-in-out infinite" : "none",
  });

  const stageStyle = (state) => ({
    display: "flex",
    alignItems: "center",
    gap: 5,
    padding: "3px 8px",
    borderRadius: 4,
    fontSize: 11,
    fontFamily: "'JetBrains Mono', monospace",
    background:
      state === "done"
        ? "rgba(34,197,94,0.10)"
        : state === "active"
        ? "rgba(168,85,247,0.12)"
        : "rgba(85,85,104,0.10)",
    color:
      state === "done"
        ? tokens.accent.green
        : state === "active"
        ? "#c084fc"
        : tokens.text.muted,
  });

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 6,
        padding: "7px 16px",
        background: tokens.bg.surface,
        borderBottom: `1px solid ${tokens.bg.border}`,
      }}
    >
      <span
        style={{
          fontSize: 10,
          color: tokens.text.muted,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          marginRight: 4,
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        Pipeline
      </span>

      {stages.map((stage, idx) => {
        const state = deriveStageState(
          stage.id, counts, total, pipelineStatus, stages
        );
        const count = counts[stage.id] ?? 0;

        return (
          <React.Fragment key={stage.id}>
            {idx > 0 && (
              <span style={{ color: tokens.bg.border, fontSize: 12 }}>›</span>
            )}
            <div style={stageStyle(state)}>
              <div style={dotStyle(state)} />
              <span>{stage.label}</span>
              {total > 0 && (
                <span style={{ fontSize: 10, opacity: 0.65 }}>
                  {count}/{total}
                </span>
              )}
            </div>
          </React.Fragment>
        );
      })}

      <style>{`
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
      `}</style>
    </div>
  );
}

// ─── Shared top bar stub ─────────────────────────────────────
function TopBar({ pipelineStatus }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 16px",
        background: tokens.bg.surface,
        borderBottom: `1px solid ${tokens.bg.border}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: tokens.text.primary,
            letterSpacing: "-0.02em",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          Albatross
        </span>
        <div style={{ width: 1, height: 14, background: tokens.bg.border }} />
        <span
          style={{
            fontSize: 11,
            color: tokens.text.muted,
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          live / mock
        </span>
        {pipelineStatus === "running" && (
          <span
            style={{
              fontSize: 10,
              padding: "2px 7px",
              borderRadius: 4,
              background: "rgba(34,197,94,0.12)",
              color: tokens.accent.green,
              border: "1px solid rgba(34,197,94,0.2)",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            ● running
          </span>
        )}
      </div>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <span
          style={{
            fontSize: 10,
            padding: "2px 7px",
            borderRadius: 4,
            background: "rgba(85,85,104,0.15)",
            color: tokens.text.secondary,
            border: "1px solid rgba(85,85,104,0.2)",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          7 / 12
        </span>
      </div>
    </div>
  );
}

// ─── Pipeline controls stub (existing) ──────────────────────
function PipelineControls({ pipelineStatus }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "10px 16px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background:
              pipelineStatus === "running" ? tokens.accent.green : "#3a3a50",
            display: "inline-block",
          }}
        />
        <span
          style={{
            fontSize: 11,
            color: tokens.text.muted,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          Pipeline {pipelineStatus}
        </span>
      </div>
      <button
        style={{
          padding: "3px 10px",
          fontSize: 11,
          fontFamily: "'JetBrains Mono', monospace",
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          borderRadius: 4,
          background: "rgba(34,197,94,0.15)",
          color: tokens.accent.green,
          border: "none",
          cursor: "default",
          opacity: pipelineStatus === "running" ? 0.4 : 1,
        }}
      >
        Start Mock Pipeline
      </button>
      <button
        style={{
          padding: "3px 10px",
          fontSize: 11,
          fontFamily: "'JetBrains Mono', monospace",
          fontWeight: 600,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          borderRadius: 4,
          background: "rgba(239,68,68,0.12)",
          color: tokens.accent.red,
          border: "none",
          cursor: "default",
          opacity: pipelineStatus === "stopped" ? 0.4 : 1,
        }}
      >
        Stop
      </button>
    </div>
  );
}

// ─── Tab bar stub ────────────────────────────────────────────
function TabBar() {
  return (
    <div
      style={{
        display: "flex",
        borderBottom: `1px solid ${tokens.bg.border}`,
        padding: "0 16px",
        background: tokens.bg.surface,
      }}
    >
      {["Live", "Events", "Timeline"].map((tab, i) => (
        <div
          key={tab}
          style={{
            fontSize: 11,
            padding: "8px 14px",
            color: i === 0 ? tokens.text.primary : tokens.text.muted,
            letterSpacing: "0.05em",
            textTransform: "uppercase",
            borderBottom: i === 0 ? `2px solid ${tokens.accent.blue}` : "2px solid transparent",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {tab}
        </div>
      ))}
    </div>
  );
}

// ─── Content stub ────────────────────────────────────────────
function ContentStub({ counts }) {
  const hasData = counts.routing > 0;
  return (
    <div style={{ padding: "12px 16px", display: "flex", gap: 8 }}>
      {hasData ? (
        <>
          {[
            { label: "thr_001 — bob & dylan", color: tokens.accent.blue },
            { label: "thr_002 — sam & jose",  color: tokens.accent.amber },
          ].map(({ label, color }) => (
            <div
              key={label}
              style={{
                flex: 1,
                background: tokens.bg.surface,
                border: `1px solid ${tokens.bg.border}`,
                borderRadius: 6,
                padding: "8px 10px",
                minHeight: 60,
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color,
                  marginBottom: 8,
                  paddingBottom: 6,
                  borderBottom: `1px solid ${tokens.bg.borderSubtle}`,
                  fontFamily: "'JetBrains Mono', monospace",
                }}
              >
                {label}
              </div>
              <div style={{ height: 18, background: tokens.bg.elevated, borderRadius: 3, marginBottom: 4, width: "90%" }} />
              <div style={{ height: 18, background: tokens.bg.elevated, borderRadius: 3, width: "70%" }} />
            </div>
          ))}
        </>
      ) : (
        <span
          style={{
            fontSize: 12,
            color: tokens.text.muted,
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          No data yet. Start the pipeline to begin.
        </span>
      )}
    </div>
  );
}

// ─── Full page mockup for one state ─────────────────────────
function PageMockup({ state }) {
  const { pipelineStatus, total, counts } = state;
  return (
    <div
      style={{
        background: tokens.bg.base,
        borderRadius: 10,
        border: `0.5px solid #2a2a38`,
        overflow: "hidden",
      }}
    >
      <TopBar pipelineStatus={pipelineStatus} />

      {/* NEW: PipelineStrip sits between top bar and pipeline controls */}
      <PipelineStrip
        stages={MOCK_STAGES}
        counts={counts}
        total={total}
        pipelineStatus={pipelineStatus}
      />

      <PipelineControls pipelineStatus={pipelineStatus} />
      <TabBar />
      <ContentStub counts={counts} />
    </div>
  );
}

// ─── Root ────────────────────────────────────────────────────
export default function PipelineObservabilityMockup() {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 32, padding: "4px 0 20px" }}>
      {Object.entries(STATES).map(([key, state]) => (
        <div key={key}>
          <div
            style={{
              fontSize: 10,
              fontWeight: 600,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: tokens.text.muted,
              fontFamily: "'JetBrains Mono', monospace",
              marginBottom: 8,
            }}
          >
            State: {state.label}
          </div>
          <PageMockup state={state} />
        </div>
      ))}
    </div>
  );
}