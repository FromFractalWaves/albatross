import { useState } from "react";

// ─── Mock Data ───────────────────────────────────────────────
const mockThreads = [
  {
    thread_id: "thread_A",
    label: "Bob and Dylan — timesheet policy complaints",
    color: "#3b82f6",
    packets: [
      { id: "pkt_001", text: "Dylan! How's it going man?", speaker: "bob", time: "09:00:00", thread_decision: "new", event_decision: "none" },
      { id: "pkt_003", text: "Bob! Not bad, not bad. You?", speaker: "dylan", time: "09:00:14", thread_decision: "existing", event_decision: "none" },
      { id: "pkt_005", text: "Doing alright. Did you see the new timesheet policy they rolled out?", speaker: "bob", time: "09:00:38", thread_decision: "existing", event_decision: "new" },
      { id: "pkt_007", text: "Oh I saw it. You have to log in fifteen minute increments now? Are they serious?", speaker: "dylan", time: "09:01:04", thread_decision: "existing", event_decision: "existing" },
      { id: "pkt_009", text: "Dead serious. And Karen from HR has been going desk to desk checking.", speaker: "bob", time: "09:01:33", thread_decision: "existing", event_decision: "existing" },
    ],
    event_ids: ["event_A"],
  },
  {
    thread_id: "thread_B",
    label: "Sam and Jose — lemon desserts",
    color: "#f59e0b",
    packets: [
      { id: "pkt_002", text: "hey", speaker: "sam", time: "09:00:07", thread_decision: "new", event_decision: "none" },
      { id: "pkt_004", text: "hey", speaker: "jose", time: "09:00:19", thread_decision: "existing", event_decision: "none" },
      { id: "pkt_006", text: "made a lemon pie last night, turned out really good", speaker: "sam", time: "09:00:51", thread_decision: "existing", event_decision: "new" },
      { id: "pkt_008", text: "oh nice, what kind of crust?", speaker: "jose", time: "09:01:17", thread_decision: "existing", event_decision: "existing" },
      { id: "pkt_010", text: "butter crust, did it from scratch. thinking about a lemon blueberry pound cake next", speaker: "sam", time: "09:01:44", thread_decision: "existing", event_decision: "existing" },
    ],
    event_ids: ["event_B"],
  },
];

const mockEvents = [
  { event_id: "event_A", label: "New timesheet policy and HR enforcement", status: "open", thread_ids: ["thread_A"], color: "#3b82f6" },
  { event_id: "event_B", label: "Lemon pie and plans for lemon blueberry pound cake", status: "open", thread_ids: ["thread_B"], color: "#f59e0b" },
];

const incomingPacket = {
  id: "pkt_011",
  text: "Karen came by my desk twice yesterday. I just left the spreadsheet open and nodded at her.",
  speaker: "dylan",
  time: "09:02:01",
};

// ─── Design Tokens ──────────────────────────────────────────
const tokens = {
  bg: {
    base: "#0a0a0f",
    surface: "#111118",
    elevated: "#1a1a24",
    hover: "#22222e",
    border: "#2a2a38",
    borderSubtle: "#1e1e2a",
  },
  text: {
    primary: "#e4e4ed",
    secondary: "#8888a0",
    muted: "#555568",
    inverse: "#0a0a0f",
  },
  accent: {
    blue: "#3b82f6",
    amber: "#f59e0b",
    green: "#22c55e",
    red: "#ef4444",
    purple: "#a855f7",
    cyan: "#06b6d4",
  },
};

// ─── Utility Components ─────────────────────────────────────
function Badge({ children, color, variant = "default" }) {
  const styles = {
    default: {
      background: color ? `${color}18` : `${tokens.accent.blue}18`,
      color: color || tokens.accent.blue,
      border: `1px solid ${color ? `${color}30` : `${tokens.accent.blue}30`}`,
    },
    solid: {
      background: color || tokens.accent.blue,
      color: tokens.text.inverse,
      border: "none",
    },
    outline: {
      background: "transparent",
      color: color || tokens.text.secondary,
      border: `1px solid ${tokens.bg.border}`,
    },
  };

  return (
    <span
      style={{
        ...styles[variant],
        padding: "2px 8px",
        borderRadius: "4px",
        fontSize: "11px",
        fontWeight: 500,
        fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
        letterSpacing: "0.02em",
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        whiteSpace: "nowrap",
      }}
    >
      {children}
    </span>
  );
}

function DecisionBadge({ decision, type }) {
  const config = {
    new: { color: tokens.accent.green, icon: "+" },
    existing: { color: tokens.accent.blue, icon: "→" },
    none: { color: tokens.text.muted, icon: "–" },
    buffer: { color: tokens.accent.amber, icon: "◷" },
    unknown: { color: tokens.accent.red, icon: "?" },
  };
  const c = config[decision] || config.unknown;
  return (
    <Badge color={c.color}>
      <span style={{ fontSize: "10px" }}>{c.icon}</span>
      {type}:{decision}
    </Badge>
  );
}

function SectionHeader({ title, count, action }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "10px 14px",
        borderBottom: `1px solid ${tokens.bg.borderSubtle}`,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: tokens.text.secondary,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {title}
        </span>
        {count !== undefined && (
          <span
            style={{
              fontSize: "10px",
              color: tokens.text.muted,
              background: tokens.bg.elevated,
              padding: "1px 6px",
              borderRadius: "3px",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {count}
          </span>
        )}
      </div>
      {action}
    </div>
  );
}

// ─── Packet Card ────────────────────────────────────────────
function PacketCard({ packet, threadColor, isLatest }) {
  return (
    <div
      style={{
        padding: "10px 12px",
        background: isLatest ? `${threadColor}08` : "transparent",
        borderLeft: `2px solid ${isLatest ? threadColor : "transparent"}`,
        transition: "all 0.2s ease",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "5px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "10px",
              fontFamily: "'JetBrains Mono', monospace",
              color: tokens.text.muted,
            }}
          >
            {packet.id}
          </span>
          <span
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: threadColor,
            }}
          >
            {packet.speaker}
          </span>
          <span
            style={{
              fontSize: "10px",
              color: tokens.text.muted,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {packet.time}
          </span>
        </div>
      </div>
      <p
        style={{
          fontSize: "13px",
          color: tokens.text.primary,
          lineHeight: 1.45,
          margin: "0 0 6px 0",
        }}
      >
        {packet.text}
      </p>
      <div style={{ display: "flex", gap: "5px" }}>
        <DecisionBadge decision={packet.thread_decision} type="thr" />
        <DecisionBadge decision={packet.event_decision} type="evt" />
      </div>
    </div>
  );
}

// ─── Thread Lane ────────────────────────────────────────────
function ThreadLane({ thread }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: "340px",
        background: tokens.bg.surface,
        borderRadius: "8px",
        border: `1px solid ${tokens.bg.border}`,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Thread header */}
      <div
        style={{
          padding: "12px 14px",
          borderBottom: `1px solid ${tokens.bg.borderSubtle}`,
          display: "flex",
          alignItems: "flex-start",
          gap: "10px",
        }}
      >
        <div
          style={{
            width: "8px",
            height: "8px",
            borderRadius: "50%",
            background: thread.color,
            marginTop: "4px",
            flexShrink: 0,
            boxShadow: `0 0 8px ${thread.color}40`,
          }}
        />
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "3px" }}>
            <span
              style={{
                fontSize: "11px",
                fontFamily: "'JetBrains Mono', monospace",
                color: thread.color,
                fontWeight: 600,
              }}
            >
              {thread.thread_id}
            </span>
            <Badge variant="outline">open</Badge>
          </div>
          <span
            style={{
              fontSize: "12px",
              color: tokens.text.secondary,
              lineHeight: 1.4,
            }}
          >
            {thread.label}
          </span>
        </div>
        <span
          style={{
            fontSize: "10px",
            fontFamily: "'JetBrains Mono', monospace",
            color: tokens.text.muted,
            background: tokens.bg.elevated,
            padding: "2px 6px",
            borderRadius: "3px",
          }}
        >
          {thread.packets.length} pkts
        </span>
      </div>

      {/* Packets */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {thread.packets.map((p, i) => (
          <div
            key={p.id}
            style={{
              borderBottom:
                i < thread.packets.length - 1
                  ? `1px solid ${tokens.bg.borderSubtle}`
                  : "none",
            }}
          >
            <PacketCard
              packet={p}
              threadColor={thread.color}
              isLatest={i === thread.packets.length - 1}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Event Card ─────────────────────────────────────────────
function EventCard({ event }) {
  return (
    <div
      style={{
        padding: "10px 12px",
        background: tokens.bg.surface,
        borderRadius: "6px",
        border: `1px solid ${tokens.bg.border}`,
        display: "flex",
        alignItems: "flex-start",
        gap: "10px",
      }}
    >
      <div
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          background: event.color,
          marginTop: "5px",
          flexShrink: 0,
        }}
      />
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px", marginBottom: "4px" }}>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "'JetBrains Mono', monospace",
              color: event.color,
              fontWeight: 600,
            }}
          >
            {event.event_id}
          </span>
          <Badge color={tokens.accent.green}>open</Badge>
        </div>
        <span style={{ fontSize: "12px", color: tokens.text.secondary, lineHeight: 1.4 }}>
          {event.label}
        </span>
        <div style={{ marginTop: "5px", display: "flex", gap: "4px" }}>
          {event.thread_ids.map((tid) => (
            <Badge key={tid} variant="outline" color={event.color}>
              {tid}
            </Badge>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Incoming Packet Banner ────────────────────────────────
function IncomingBanner({ packet }) {
  return (
    <div
      style={{
        background: `linear-gradient(135deg, ${tokens.accent.purple}10, ${tokens.accent.cyan}08)`,
        border: `1px solid ${tokens.accent.purple}25`,
        borderRadius: "8px",
        padding: "14px 16px",
        display: "flex",
        alignItems: "flex-start",
        gap: "12px",
      }}
    >
      <div
        style={{
          background: tokens.accent.purple,
          color: "#fff",
          fontSize: "9px",
          fontWeight: 700,
          fontFamily: "'JetBrains Mono', monospace",
          padding: "3px 7px",
          borderRadius: "4px",
          letterSpacing: "0.06em",
          flexShrink: 0,
          marginTop: "1px",
        }}
      >
        ROUTING
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px" }}>
          <span
            style={{
              fontSize: "11px",
              fontFamily: "'JetBrains Mono', monospace",
              color: tokens.accent.purple,
              fontWeight: 600,
            }}
          >
            {packet.id}
          </span>
          <span style={{ fontSize: "12px", fontWeight: 600, color: tokens.text.primary }}>
            {packet.speaker}
          </span>
          <span
            style={{
              fontSize: "10px",
              color: tokens.text.muted,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {packet.time}
          </span>
        </div>
        <p style={{ fontSize: "13px", color: tokens.text.primary, margin: 0, lineHeight: 1.45 }}>
          {packet.text}
        </p>
      </div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <div
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: tokens.accent.purple,
            animation: "pulse 1.5s ease-in-out infinite",
          }}
        />
        <span
          style={{
            fontSize: "10px",
            color: tokens.accent.purple,
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          awaiting LLM
        </span>
      </div>
    </div>
  );
}

// ─── Context Inspector ──────────────────────────────────────
function ContextInspector({ expanded, onToggle }) {
  const contextJson = {
    active_threads: mockThreads.map((t) => ({
      thread_id: t.thread_id,
      label: t.label,
      packet_count: t.packets.length,
      event_ids: t.event_ids,
      status: "open",
    })),
    active_events: mockEvents.map((e) => ({
      event_id: e.event_id,
      label: e.label,
      status: e.status,
    })),
    packets_to_resolve: [],
    buffers_remaining: 5,
    incoming_packet: incomingPacket,
  };

  return (
    <div
      style={{
        background: tokens.bg.surface,
        borderRadius: "8px",
        border: `1px solid ${tokens.bg.border}`,
        overflow: "hidden",
      }}
    >
      <div
        onClick={onToggle}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 14px",
          cursor: "pointer",
          userSelect: "none",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: tokens.text.secondary,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            Context Inspector
          </span>
          <Badge variant="outline">TRMContext</Badge>
        </div>
        <span
          style={{
            fontSize: "12px",
            color: tokens.text.muted,
            transform: expanded ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.2s ease",
          }}
        >
          ▼
        </span>
      </div>
      {expanded && (
        <div
          style={{
            padding: "0 14px 14px",
            borderTop: `1px solid ${tokens.bg.borderSubtle}`,
          }}
        >
          <pre
            style={{
              fontSize: "11px",
              fontFamily: "'JetBrains Mono', monospace",
              color: tokens.text.secondary,
              lineHeight: 1.6,
              margin: "12px 0 0 0",
              whiteSpace: "pre-wrap",
              overflow: "auto",
              maxHeight: "300px",
            }}
          >
            {JSON.stringify(contextJson, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

// ─── Top Bar ────────────────────────────────────────────────
function TopBar() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 20px",
        borderBottom: `1px solid ${tokens.bg.border}`,
        background: tokens.bg.surface,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
        <span
          style={{
            fontSize: "14px",
            fontWeight: 700,
            color: tokens.text.primary,
            letterSpacing: "-0.02em",
          }}
        >
          TRM
        </span>
        <div
          style={{
            width: "1px",
            height: "16px",
            background: tokens.bg.border,
          }}
        />
        <span style={{ fontSize: "12px", color: tokens.text.muted }}>
          scenario_02_interleaved
        </span>
        <Badge color={tokens.accent.green} variant="default">
          ● running
        </Badge>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "10px",
              color: tokens.text.muted,
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            packets
          </span>
          <span
            style={{
              fontSize: "13px",
              color: tokens.text.primary,
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
            }}
          >
            10/12
          </span>
        </div>
        <div
          style={{
            width: "1px",
            height: "16px",
            background: tokens.bg.border,
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "10px",
              color: tokens.text.muted,
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            buffers
          </span>
          <span
            style={{
              fontSize: "13px",
              color: tokens.text.primary,
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
            }}
          >
            5
          </span>
        </div>
        <div
          style={{
            width: "1px",
            height: "16px",
            background: tokens.bg.border,
          }}
        />
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "10px",
              color: tokens.text.muted,
              fontFamily: "'JetBrains Mono', monospace",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            speed
          </span>
          <span
            style={{
              fontSize: "13px",
              color: tokens.text.primary,
              fontFamily: "'JetBrains Mono', monospace",
              fontWeight: 600,
            }}
          >
            20×
          </span>
        </div>
      </div>
    </div>
  );
}

// ─── Main Dashboard ─────────────────────────────────────────
export default function TRMDashboard() {
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("live");

  return (
    <div
      style={{
        background: tokens.bg.base,
        minHeight: "100vh",
        color: tokens.text.primary,
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif",
      }}
    >
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: ${tokens.bg.base}; }
        ::-webkit-scrollbar-thumb { background: ${tokens.bg.border}; border-radius: 3px; }
      `}</style>

      <TopBar />

      <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: "14px" }}>
        {/* Incoming packet */}
        <IncomingBanner packet={incomingPacket} />

        {/* Tab bar */}
        <div style={{ display: "flex", gap: "2px" }}>
          {["live", "events", "timeline"].map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              style={{
                background: activeTab === tab ? tokens.bg.elevated : "transparent",
                color: activeTab === tab ? tokens.text.primary : tokens.text.muted,
                border: "none",
                padding: "7px 14px",
                fontSize: "11px",
                fontWeight: 600,
                fontFamily: "'JetBrains Mono', monospace",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                borderRadius: "5px",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Thread Lanes */}
        {activeTab === "live" && (
          <div style={{ display: "flex", gap: "14px", alignItems: "flex-start" }}>
            {mockThreads.map((thread) => (
              <ThreadLane key={thread.thread_id} thread={thread} />
            ))}
          </div>
        )}

        {/* Events view */}
        {activeTab === "events" && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "8px",
              maxWidth: "600px",
            }}
          >
            {mockEvents.map((event) => (
              <EventCard key={event.event_id} event={event} />
            ))}
          </div>
        )}

        {/* Timeline view */}
        {activeTab === "timeline" && (
          <div
            style={{
              background: tokens.bg.surface,
              borderRadius: "8px",
              border: `1px solid ${tokens.bg.border}`,
              overflow: "hidden",
            }}
          >
            <SectionHeader title="Packet Timeline" count={10} />
            <div style={{ padding: "4px 0" }}>
              {[...mockThreads[0].packets, ...mockThreads[1].packets]
                .sort((a, b) => a.id.localeCompare(b.id))
                .map((p, i) => {
                  const thread = mockThreads.find((t) =>
                    t.packets.some((tp) => tp.id === p.id)
                  );
                  return (
                    <div
                      key={p.id}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        padding: "8px 14px",
                        gap: "12px",
                        borderBottom:
                          i < 9 ? `1px solid ${tokens.bg.borderSubtle}` : "none",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "10px",
                          fontFamily: "'JetBrains Mono', monospace",
                          color: tokens.text.muted,
                          width: "52px",
                          flexShrink: 0,
                        }}
                      >
                        {p.id}
                      </span>
                      <div
                        style={{
                          width: "8px",
                          height: "8px",
                          borderRadius: "50%",
                          background: thread?.color,
                          flexShrink: 0,
                        }}
                      />
                      <span
                        style={{
                          fontSize: "11px",
                          fontFamily: "'JetBrains Mono', monospace",
                          color: thread?.color,
                          width: "50px",
                          flexShrink: 0,
                          fontWeight: 600,
                        }}
                      >
                        {p.speaker}
                      </span>
                      <span
                        style={{
                          fontSize: "12px",
                          color: tokens.text.primary,
                          flex: 1,
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {p.text}
                      </span>
                      <div
                        style={{
                          display: "flex",
                          gap: "4px",
                          flexShrink: 0,
                        }}
                      >
                        <DecisionBadge decision={p.thread_decision} type="thr" />
                        <DecisionBadge decision={p.event_decision} type="evt" />
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* Context Inspector */}
        <ContextInspector
          expanded={inspectorOpen}
          onToggle={() => setInspectorOpen(!inspectorOpen)}
        />
      </div>
    </div>
  );
}