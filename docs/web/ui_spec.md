# TRM Dashboard — UI Design Spec

*Visual design reference for the TRM web interface. Based on the interactive mockup built during planning.*

---

## Design Direction

Data-dense dashboard with dark/light theme toggle. Think Grafana/Datadog — designed for watching structured state evolve in real time. Prioritizes information density and clarity over decoration. Default theme is dark; users can toggle to light via a sun/moon button in the top bar. Preference persists in `localStorage`.

**Stack:** Next.js + TypeScript, Tailwind CSS v4.

---

## Design Tokens

All colors, backgrounds, and borders use a consistent token system. These should map to CSS variables or Tailwind config in implementation.

### Backgrounds

| Token | Value | Usage |
|-------|-------|-------|
| `bg.base` | `#0a0a0f` | Page background, deepest layer |
| `bg.surface` | `#111118` | Cards, panels, elevated containers |
| `bg.elevated` | `#1a1a24` | Hover states, active tabs, secondary containers |
| `bg.hover` | `#22222e` | Interactive hover states |
| `bg.border` | `#2a2a38` | Primary borders |
| `bg.borderSubtle` | `#1e1e2a` | Dividers within cards, row separators |

### Text

| Token | Value | Usage |
|-------|-------|-------|
| `text.primary` | `#e4e4ed` | Main content, packet text, labels |
| `text.secondary` | `#8888a0` | Section headers, descriptions, thread labels |
| `text.muted` | `#555568` | Timestamps, packet IDs, counters |
| `text.inverse` | `#0a0a0f` | Text on solid-color backgrounds |

### Accent Colors

| Token | Value | Usage |
|-------|-------|-------|
| `accent.blue` | `#3b82f6` | Thread A color, default accent, `existing` decisions |
| `accent.amber` | `#f59e0b` | Thread B color, `buffer` decisions |
| `accent.green` | `#22c55e` | `new` decisions, open status, correct matches |
| `accent.red` | `#ef4444` | `unknown` decisions, errors, mismatches |
| `accent.purple` | `#a855f7` | Incoming packet highlight, routing state |
| `accent.cyan` | `#06b6d4` | Secondary accent, subtle highlights |

Additional thread colors should be assigned from a palette as threads are created. Blue and amber are just the first two. A reasonable sequence: blue, amber, green, purple, cyan, red — cycling if more are needed.

### Typography

- **Body/UI text:** System font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif`)
- **Monospace (IDs, timestamps, code, badges, counters):** `'JetBrains Mono', 'SF Mono', 'Fira Code', monospace`
- **Section headers:** 11px, monospace, uppercase, `letter-spacing: 0.08em`, `text.secondary` color
- **Packet text:** 13px, system font, `text.primary`, `line-height: 1.45`
- **Badges:** 11px, monospace, `font-weight: 500`, `letter-spacing: 0.02em`

---

## Layout Structure

The dashboard is a single-page view with a fixed top bar and a scrollable content area below.

```
┌─────────────────────────────────────────────────────────────┐
│ TOP BAR                                                      │
│ [Albatross] | scenario_name | ● running  packets 10/12 | ☀ │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│ ┌─ INCOMING PACKET BANNER ────────────────────────────────┐ │
│ │ [ROUTING] pkt_011  dylan  09:02:01                      │ │
│ │ "Karen came by my desk twice yesterday..."    ● waiting │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                               │
│ [LIVE]  [EVENTS]  [TIMELINE]                    ← tab bar   │
│                                                               │
│ ┌─── Thread Lane ────┐  ┌─── Thread Lane ────┐              │
│ │ ● thread_A  [open] │  │ ● thread_B  [open] │              │
│ │ Bob and Dylan —     │  │ Sam and Jose —      │              │
│ │ timesheet policy    │  │ lemon desserts      │              │
│ │                     │  │                     │              │
│ │ pkt_001 bob         │  │ pkt_002 sam         │              │
│ │ "Dylan! How's..."   │  │ "hey"               │              │
│ │ [thr:new] [evt:none]│  │ [thr:new] [evt:none]│              │
│ │─────────────────────│  │─────────────────────│              │
│ │ pkt_003 dylan       │  │ pkt_004 jose        │              │
│ │ "Bob! Not bad..."   │  │ "hey"               │              │
│ │ ...                 │  │ ...                  │              │
│ └─────────────────────┘  └─────────────────────┘              │
│                                                               │
│ ┌─ CONTEXT INSPECTOR ─────────────────────── ▼ collapse ──┐ │
│ │ { "active_threads": [...], "active_events": [...] }      │ │
│ └──────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Components

### Top Bar

Fixed at the top. Displays run metadata at a glance.

**Left side:**
- "Albatross" wordmark — 14px, bold, `text.primary`
- Vertical divider
- Scenario name — 12px, `text.muted`
- Status badge — "● running" (green), "● complete" (blue), "● error" (red)

**Right side — stat counters, each separated by vertical dividers:**
- `PACKETS` — e.g. "10/12" (processed / total)
- `BUFFERS` — remaining buffer count
- `SPEED` — replay speed factor, e.g. "20×"

All counter labels are 10px uppercase monospace in `text.muted`. Values are 13px monospace bold in `text.primary`.

### Incoming Packet Banner

Highlighted banner at the top of the content area showing the packet currently being routed by the LLM.

- Background: subtle gradient using `accent.purple` and `accent.cyan` at very low opacity (~8-10%)
- Border: `accent.purple` at ~25% opacity
- Left side: solid purple "ROUTING" badge (9px, uppercase, monospace, bold)
- Center: packet ID, speaker name, timestamp, then packet text below
- Right side: pulsing dot + "awaiting LLM" text in `accent.purple`

The pulsing dot animates with a simple opacity keyframe (1.0 → 0.3 → 1.0, 1.5s ease-in-out infinite).

When the packet is routed, this banner updates to show the next incoming packet, or disappears when the run is complete.

### Tab Bar

Three tabs below the incoming packet banner: **LIVE**, **EVENTS**, **TIMELINE**.

- 11px monospace uppercase text
- Active tab: `bg.elevated` background, `text.primary` color
- Inactive tab: transparent background, `text.muted` color
- Tabs are pill-shaped (border-radius: 5px), no borders
- Switch views without navigation — same page, different content rendering

### Thread Lane (LIVE tab)

One vertical column per active thread. Lanes sit side by side, flexing to fill available width (min-width ~340px, wrapping on narrow screens).

**Header:**
- Colored dot (8px circle) matching the thread's assigned color, with a subtle glow (`box-shadow: 0 0 8px {color}40`)
- Thread ID — 11px monospace, bold, in the thread's color
- Status badge — "open" in outline style
- Thread label — 12px, `text.secondary`, wraps if long
- Packet count — top-right corner, e.g. "5 pkts" in `text.muted` on `bg.elevated` background

**Packet list:**
Each packet is a row within the lane, separated by `bg.borderSubtle` dividers.

Packet row layout:
- Top line: packet ID (10px mono, `text.muted`), speaker name (11px bold, in thread color), timestamp (10px mono, `text.muted`)
- Packet text below: 13px, `text.primary`
- Decision badges below text: `[thr:decision]` and `[evt:decision]` side by side

The most recent packet in each lane gets a left border highlight (2px solid in thread color) and a very subtle background tint of the thread color (~3% opacity). This draws the eye to what just happened.

### Event Card (EVENTS tab)

Cards displayed in a vertical stack, max-width ~600px.

- Colored dot (6px) matching the event's primary thread color
- Event ID — 11px monospace bold in the event color
- Status badge — "open" with green tint
- Event label — 12px, `text.secondary`
- Thread links below — outline badges showing each linked thread_id in the event's color

### Timeline View (TIMELINE tab)

A flat chronological list of all packets across all threads, sorted by packet ID / timestamp.

Each row:
- Packet ID — 10px monospace, `text.muted`, fixed width (~52px)
- Thread color dot — 8px circle
- Speaker — 11px monospace bold, in thread color, fixed width (~50px)
- Packet text — 12px, `text.primary`, truncated with ellipsis (flex: 1)
- Decision badges — right-aligned, flex-shrink 0

Rows separated by `bg.borderSubtle` dividers. This view is most useful for seeing the interleaving pattern and checking that temporal ordering is correct.

### Decision Badges

Compact indicators showing routing decisions. Used on every packet in every view.

Format: `[icon] type:decision`

| Decision | Icon | Color |
|----------|------|-------|
| `new` | `+` | `accent.green` |
| `existing` | `→` | `accent.blue` |
| `none` | `–` | `text.muted` |
| `buffer` | `◷` | `accent.amber` |
| `unknown` | `?` | `accent.red` |

Badge styling:
- Background: decision color at ~10% opacity
- Border: decision color at ~20% opacity
- Text: decision color at full opacity
- 11px monospace, padding 2px 8px, border-radius 4px

Two badges per packet: one for thread decision (`thr:new`), one for event decision (`evt:none`).

**Phase 6 addition:** In comparison mode, badges get a green or red background override to indicate match/mismatch against expected output.

### Context Inspector

Collapsible panel at the bottom of the content area.

**Collapsed (default):** Single row with "CONTEXT INSPECTOR" label (section header style) + "TRMContext" outline badge + chevron (▼). Click to expand.

**Expanded:** Raw JSON of the current `TRMContext` object rendered in a `<pre>` block. 11px monospace, `text.secondary`, max-height 300px with scroll. Shows active_threads (summarized), active_events, packets_to_resolve, buffers_remaining, and incoming_packet.

The chevron rotates 180° when expanded (CSS transition, 0.2s ease).

### Buffer Zone (future)

Not visible in the mockup since scenario_02 doesn't use buffers, but when `packets_to_resolve` is non-empty:

- A dedicated section between the incoming banner and the tab bar
- Header: "BUFFERED PACKETS" with count badge
- Cards for each buffered packet, styled similarly to packet rows but with an amber left border and amber tint
- Buffer counter prominently displayed

---

## Interaction Patterns

### Live Run Flow

1. User starts a run (from scenario browser or dashboard)
2. Redirected to `/run/{runId}`
3. WebSocket connects, `run_started` message arrives
4. Top bar shows "● running", packet counter starts at 0/N
5. For each `packet_routed` message:
   - Incoming banner updates to show the NEXT packet (or hides if none left)
   - The just-routed packet appears in its assigned thread lane with decision badges
   - Event cards update if an event was created or linked
   - Packet counter increments
   - Context inspector updates if expanded
6. `run_complete` message arrives — status changes to "● complete", incoming banner hides

### Tab Switching

Tabs switch the main content area between Live, Events, and Timeline views. State is preserved across switches — switching to Timeline and back to Live doesn't lose scroll position or collapse state.

### Context Inspector Toggle

Click the header row to expand/collapse. State persists across tab switches. When expanded, JSON updates in real time during a live run.

---

## Responsive Behavior

- Thread lanes wrap on narrow screens (flex-wrap)
- Min-width per lane: ~340px
- On very narrow screens (mobile), lanes stack vertically
- Timeline view works well at any width since rows are horizontal
- Top bar stats can collapse into a dropdown or second row on mobile (low priority — this is primarily a desktop tool)

---

## Fonts to Load

- **JetBrains Mono** (weights: 400, 500, 600, 700) — via Google Fonts or self-hosted
- System font stack for body text (no loading needed)

---

## File Reference

The interactive mockup is at `docs/web/ui_mockup.jsx`. It uses inline styles and mock data for portability. The real implementation should use Tailwind classes and shadcn/ui components, with the design tokens mapped to Tailwind's config / CSS variables.