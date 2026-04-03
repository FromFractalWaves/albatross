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
    stages: [
      { id: "capture",       label: "Capture",       message_type: "packet_captured",     count: 0 },
      { id: "preprocessing", label: "Preprocessing",  message_type: "packet_preprocessed", count: 0 },
      { id: "routing",       label: "TRM Routing",    message_type: "packet_routed",        count: 0 },
    ],
  },
  running: {
    label: "Mid-run",
    pipelineStatus: "running",
    stages: [
      { id: "capture",       label: "Capture",       message_type: "packet_captured",     count: 12 },
      { id: "preprocessing", label: "Preprocessing",  message_type: "packet_preprocessed", count: 7 },
      { id: "routing",       label: "TRM Routing",    message_type: "packet_routed",        count: 5 },
    ],
  },
  complete: {
    label: "Complete",
    pipelineStatus: "stopped",
    stages: [
      { id: "capture",       label: "Capture",       message_type: "packet_captured",     count: 12 },
      { id: "preprocessing", label: "Preprocessing",  message_type: "packet_preprocessed", count: 12 },
      { id: "routing",       label: "TRM Routing",    message_type: "packet_routed",        count: 12 },
    ],
  },
};

// ─── Stage colors ────────────────────────────────────────────
// Each stage gets a fixed color by index. Order matches pipeline order.
const STAGE_COLORS = [
  tokens.accent.blue,   // capture
  tokens.accent.amber,  // preprocessing
  tokens.accent.purple, // routing
  tokens.accent.cyan,   // future stages
];

// ─── PipelineStrip component ─────────────────────────────────
// This is the component to build: web/src/components/PipelineStages.tsx
// Receives: stages (from useLiveData) — each with id, label, message_type, count
// Renders nothing if stages is empty — safe to drop in unconditionally.
// No total, no progress bar. Counts increment from zero indefinitely.
function PipelineStrip({ stages }) {
  if (!stages || stages.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 3,
        padding: "7px 16px",
        background: "#060610",
        borderBottom: `1px solid ${tokens.bg.border}`,
      }}
    >
      {stages.map((stage, idx) => {
        const color = STAGE_COLORS[idx] ?? tokens.text.muted;
        const isZero = stage.count === 0;

        return (
          <div
            key={stage.id}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 10,
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
            }}
          >
            <span style={{ width: 110, flexShrink: 0, color }}>
              [{stage.id}]
            </span>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: isZero ? "#3a3a55" : color,
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
  const { pipelineStatus, stages } = state;
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
      <PipelineStrip stages={stages} />

      <PipelineControls pipelineStatus={pipelineStatus} />
      <TabBar />
      <ContentStub counts={{ routing: stages.find(s => s.id === "routing")?.count ?? 0 }} />
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