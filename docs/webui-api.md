# Web UI & API Plan

*Architecture and phased build plan for the TRM's web interface and FastAPI backend.*

---

## The Core Separation

The TRM runtime and the scenario tooling are two different concerns. The UI needs to support both, but they should not be tangled together.

**The TRM runtime** processes a stream of packets — one at a time, statefully, with the LLM making routing decisions. The runtime doesn't know or care where the packets come from. Its job is: receive packet, update context, emit routing record. The runtime view in the UI is useful regardless of the packet source.

**Scenario tooling** is one way to feed the runtime. It replays a known set of packets, collects the output, and compares it against expected results. This is not test scaffolding — it's a permanent part of the TRM workflow. Any new domain deployment will use scenarios to tune the system prompt. But it's a layer on top of the runtime, not baked into it.

**In production,** packets arrive from a live source — a radio receiver, a message queue, an API ingest. The runtime view is the same. The scenario comparison layer just isn't present.

This separation should be reflected in the API, the frontend, and the file structure.

---

## Architecture Overview

### API (FastAPI)

The API is the bridge between the TRM pipeline and the frontend. It exposes the runtime over WebSocket for live observation and provides REST endpoints for scenario management and run control.

#### REST Endpoints — Scenarios

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/scenarios` | List available scenarios (scans `data/` directory) |
| `GET` | `/api/scenarios/{tier}/{scenario}` | Get scenario detail — packets, expected output, README |

Scenarios are read from the filesystem. No database needed for this — the `data/` directory is the source of truth. The API just indexes what's there.

#### REST Endpoints — Runs

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/runs` | Start a new run (body specifies packet source — scenario, or eventually a live feed) |
| `GET` | `/api/runs` | List past runs (once persistence exists) |
| `GET` | `/api/runs/{run_id}` | Get completed run results |

A run is a single execution of the TRM runtime against a packet source. Starting a run returns a `run_id` that the frontend uses to connect via WebSocket.

#### WebSocket Protocol

| Path | Description |
|------|-------------|
| `ws://localhost:8000/ws/runs/{run_id}` | Live stream of TRM state during a run |

After starting a run via `POST /api/runs`, the frontend opens a WebSocket connection. The backend pushes a message after every packet is routed:

```json
{
  "type": "packet_routed",
  "packet_id": "pkt_005",
  "routing_record": {
    "packet_id": "pkt_005",
    "thread_decision": "existing",
    "thread_id": "thread_A",
    "event_decision": "new",
    "event_id": "event_A"
  },
  "context": {
    "active_threads": [...],
    "active_events": [...],
    "packets_to_resolve": [...],
    "buffers_remaining": 5
  }
}
```

Message types:

| Type | When |
|------|------|
| `run_started` | Run begins — includes scenario metadata if applicable |
| `packet_routed` | After each packet — includes routing record + full updated context |
| `run_complete` | All packets processed — includes final summary |
| `run_error` | Something broke |

The frontend renders state from these messages. It never polls — everything is pushed.

### Frontend (Next.js + TypeScript)

#### Pages

**`/` — Scenario Hub.** Lists all scenarios grouped by tier, fetched from `GET /api/scenarios`. Tabs for SCENARIOS (active), LIVE (disabled), HISTORY (disabled). Links to individual scenario detail pages.

**`/run/{run_id}` — Live Run View.** The main screen. During a run: incoming packet highlighted, active threads as columns/lanes with packets stacking, active events with thread links, routing decision badge, buffered packets in a holding area, buffer counter.

**`/scenarios/{tier}/{scenario}` — Scenario Detail.** Shows README, packet list, expected output (collapsible), run configuration (speed factor, buffer count). "Run This Scenario" button launches a run via `POST /api/runs` and redirects to the live view.

#### Key UI Components

**Thread Lane** — vertical column per thread, packets stacking in arrival order, color-coded, label updating as the LLM revises it.

**Event Card** — event label, status, connected thread lanes with visual links.

**Routing Decision Badge** — per-packet indicator for thread and event decisions. Green/red when comparing against expected.

**Context Inspector** — collapsible panel with raw JSON, for debugging.

### File Structure

```
albatross/
├── api/                        # FastAPI backend
│   ├── main.py                 # App setup, CORS, lifespan
│   ├── routes/
│   │   ├── scenarios.py        # Scenario listing and detail endpoints
│   │   └── runs.py             # Run control + WebSocket
│   └── services/
│       └── runner.py           # Wraps TRM pipeline — starts runs, manages state
├── web/                        # Next.js frontend
│   ├── src/
│   │   ├── app/                # Next.js app router pages
│   │   ├── components/         # React components
│   │   ├── hooks/              # WebSocket hook, etc.
│   │   └── types/              # TypeScript types mirroring Pydantic models
│   └── ...
├── src/                        # Existing TRM pipeline (unchanged)
│   ├── models/
│   │   ├── packets.py
│   │   └── router.py
│   └── pipeline/
│       ├── loader.py
│       ├── queue.py
│       └── router.py
├── data/                       # Existing scenarios (unchanged)
└── docs/
    └── webui-api.md            # This document
```

The `api/` layer imports from `src/` — it wraps the existing pipeline, it doesn't replace it.

---

## What Changes in the Existing Code

Minimal. The `TRMRouter.route()` method already returns a `RoutingRecord` and updates `self.context` after each packet. The runner service just needs to:

1. Call `router.route(packet)` as it does now
2. After each call, serialize `router.context` and the `RoutingRecord`
3. Push that over the WebSocket

The main change: `src/main.py` currently orchestrates the whole run inline. That orchestration moves to `api/services/runner.py`. The pipeline components (`PacketLoader`, `PacketQueue`, `TRMRouter`) stay exactly as they are.

---

## What's Deferred (Not In Any Phase Below)

- **Database / persistence** — runs are in-memory for now. Adding a DB is a separate step once the UI is stable.
- **Scorer** — still needs to be built. When it is, it plugs into the run-complete flow and the review view.
- **Live ingest** — a non-scenario packet source. The API is designed for this (`POST /api/runs` body specifies the source), but the only source implemented initially is scenario replay.
- **Multi-run comparison** — comparing results across different runs of the same scenario. Useful but not yet.
- **Authentication** — local dev tool for now. No auth needed.

---

## Phased Build Plan

Each phase is self-contained. Build it, test it, verify it works, then move on. Each phase's output is the foundation for the next.

**When starting a new chat for a phase:** include this document plus the existing project docs (albatross.md, trm_spec.md, runtime_loop.md, trm_outline.md) and the relevant source files for full context. Reference the specific phase you're working on.

---

### Phase 1 — FastAPI Skeleton + Scenario Endpoints

**Goal:** Stand up the FastAPI project and prove it can read scenario data from the filesystem.

**What to build:**
- `api/main.py` — FastAPI app with CORS configured for the Next.js dev server (localhost:3000)
- `api/routes/scenarios.py` — two endpoints:
  - `GET /api/scenarios` — scan `data/` directory, return list of scenarios grouped by tier (each entry: tier, scenario name, path)
  - `GET /api/scenarios/{tier}/{scenario}` — return full scenario detail: packets.json contents, expected_output.json contents, README.md text
- Ensure `api/` can import from `src/` cleanly (may need path setup or a workspace config)

**What NOT to build:** No runs, no WebSocket, no frontend, no runner service.

**How to verify:**
- `uvicorn api.main:app --reload` starts cleanly
- `curl localhost:8000/api/scenarios` returns scenario list with scenario_02_interleaved present
- `curl localhost:8000/api/scenarios/tier_one/scenario_02_interleaved` returns packets, expected output, and README content
- Adding a new scenario folder to `data/` shows up in the list without code changes

**Depends on:** Nothing. First thing built.

**Produces:** A running API that serves scenario data. Foundation for everything else.

---

### Phase 2 — Runner Service + WebSocket

**Goal:** Wire the TRM pipeline to the API so a run can be triggered and its progress streamed over WebSocket.

**What to build:**
- `api/services/runner.py` — the adapter between the API and the existing TRM pipeline:
  - Accepts a scenario path, creates `PacketLoader`, `PacketQueue`, `TRMRouter`
  - Runs the pipeline asynchronously
  - After each packet is routed, serializes the `RoutingRecord` and `TRMContext` and pushes to a callback (the WebSocket broadcast)
  - Emits `run_started`, `packet_routed`, and `run_complete` messages
  - Manages a run registry (in-memory dict of `run_id` → run state)
- `api/routes/runs.py` — two things:
  - `POST /api/runs` — accepts `{ "source": "scenario", "tier": "tier_one", "scenario": "scenario_02_interleaved", "speed_factor": 20.0 }`, creates a run, returns `{ "run_id": "..." }`
  - `ws://localhost:8000/ws/runs/{run_id}` — WebSocket endpoint that streams messages for the given run

**What NOT to build:** No frontend. No run persistence. No review mode.

**How to verify:**
- Start the API
- `POST /api/runs` with scenario_02_interleaved, get back a run_id
- Connect to `ws://localhost:8000/ws/runs/{run_id}` (use browser console, websocat, or a tiny test HTML page)
- See `run_started` message arrive
- See 12 `packet_routed` messages arrive one by one, each with the full context object
- See `run_complete` message at the end
- Context object grows correctly — threads accumulate packets, events open at the right time

**Depends on:** Phase 1 (API is running, scenario data is accessible).

**Produces:** A fully functional backend. The TRM runs, streams state over WebSocket. Everything the frontend needs is available.

---

### Phase 3 — Next.js Scaffold + Raw WebSocket View

**Goal:** Get the frontend project running, connected to the backend, and rendering raw TRM state as it arrives. Ugly but functional — proves the full end-to-end pipeline.

**What to build:**
- `web/` — Next.js project with TypeScript, app router
- `web/src/types/` — TypeScript types mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`, WebSocket message types (`RunStarted`, `PacketRouted`, `RunComplete`, `RunError`)
- `web/src/hooks/useRunSocket.ts` — custom hook that:
  - Accepts a `run_id`
  - Opens a WebSocket connection to `ws://localhost:8000/ws/runs/{run_id}`
  - Parses incoming messages and maintains current state (latest context, list of routing records so far, run status)
  - Returns `{ context, routingRecords, status, error }`
- `web/src/app/page.tsx` — minimal page: a button that calls `POST /api/runs` to start a run, then uses `useRunSocket` to connect and dumps the raw context JSON to the screen, updating live as packets are routed

**What NOT to build:** No styled UI. No thread lanes or event cards. No scenario browser. Just raw JSON rendering that updates in real time.

**How to verify:**
- `npm run dev` in `web/` starts the Next.js dev server
- Open `localhost:3000`, click the button
- See the TRM context JSON appear and update live — threads growing, events opening, packets being assigned
- All 12 packets process, run completes
- No WebSocket errors in console, no stale state

**Depends on:** Phase 2 (backend streams run state over WebSocket).

**Produces:** Full end-to-end pipeline proven: API → TRM → WebSocket → Browser. The data flows. Now it just needs to look good.

---

### Phase 4 — Dashboard Foundation + Live View

**Goal:** Replace the raw JSON dump with a real visual dashboard for watching the TRM work. This is the core deliverable — after this phase, you can watch a run build threads visually in real time.

**Design reference:** `docs/ui_spec.md` is the canonical design spec. `docs/ui_mockup.jsx` is the interactive mockup — use it as a component reference but follow the spec for final styling decisions.

**Setup (before building components):**

1. **Install shadcn/ui + Tailwind CSS.** `npx shadcn@latest init` pulls in Tailwind as a dependency. Configure the Tailwind theme with the design tokens from `docs/ui_spec.md` (backgrounds, text, accents) as CSS variables.
2. **Load JetBrains Mono** (weights 400, 500, 600, 700) via Google Fonts or self-hosted.
3. ~~**Include `incoming_packet` in the WebSocket broadcast.**~~ **Done.** The runner pops `incoming_packet` from the context snapshot and sends it as a top-level sibling field in the `packet_routed` message. The TypeScript `PacketRoutedMessage` type and `useRunSocket` hook already handle this.
4. ~~**Extend `useRunSocket` to track the latest routed packet.**~~ **Done.** The hook's reducer state includes `latestPacketId: string | null` and `incomingPacket: ReadyPacket | null`, both set on each `packet_routed` action and cleared on `run_complete`.

**What to build:**

Base components (bottom-up):
- `web/src/components/Badge.tsx` — reusable badge with `default`, `solid`, and `outline` variants, color-tinted backgrounds
- `web/src/components/DecisionBadge.tsx` — `[icon] type:decision` format, color-coded per decision type (see ui_spec)
- `web/src/components/SectionHeader.tsx` — 11px monospace uppercase header with optional count badge

Dashboard components:
- `web/src/components/TopBar.tsx` — fixed top bar: TRM wordmark, scenario name, status badge, packet/buffer/speed counters
- `web/src/components/IncomingBanner.tsx` — purple/cyan gradient banner showing the packet currently being routed, pulsing "awaiting LLM" indicator
- `web/src/components/PacketCard.tsx` — packet row: ID, speaker, timestamp, text, decision badges. Latest packet gets left border highlight + background tint
- `web/src/components/ThreadLane.tsx` — vertical column per thread: colored dot + header, packet list using `PacketCard`. Flex layout, min-width 340px, wraps on narrow screens
- `web/src/components/ContextInspector.tsx` — collapsible panel: header row with chevron toggle, expandable `<pre>` block with raw TRMContext JSON

Page:
- `web/src/app/run/[runId]/page.tsx` — the live run view. Wires `useRunSocket` to all components above. Three-tab interface: LIVE (thread lanes), EVENTS (event cards), TIMELINE (chronological packet list). Uses `hidden` class for tab switching to preserve scroll position.

**Build order:** Badge → DecisionBadge → SectionHeader → PacketCard → ThreadLane → IncomingBanner → TopBar → ContextInspector → run page (wire everything)

**Thread color assignment:** Threads get colors from a rotating palette as they're created: blue, amber, green, purple, cyan, red (cycling if more needed). Color assignment should be deterministic from thread creation order.

**What NOT to build:** No Events tab content. No Timeline tab content. No BufferZone (deferred until a scenario exercises it). No scenario browser. No playback controls. No comparison overlay.

**How to verify:**
- Start a run against scenario_02_interleaved, watch threads build up visually
- Thread A (Bob/Dylan/timesheets) in blue and Thread B (Sam/Jose/desserts) in amber are visually distinct
- Packets appear in the correct thread lanes as they're routed
- Incoming banner shows each packet before it's routed, with pulsing indicator
- Top bar shows running status, packet counter incrementing, buffer count, speed
- Decision badges show correct decisions (new/existing/none)
- Context inspector expands to show raw state matching the visual components
- Run completes cleanly — status changes, incoming banner hides

**Depends on:** Phase 3 (frontend connected to backend, WebSocket hook working).

**Produces:** A working visual dashboard for watching the TRM in real time. The LIVE tab is fully functional.

---

### Phase 5 — Events + Timeline Tabs

**Goal:** Complete the dashboard's three-tab interface. Add the Events and Timeline views, plus the BufferZone for scenarios that use buffering.

**What to build:**
- `web/src/components/EventCard.tsx` — event label, status badge, colored dot, thread link badges. Cards stacked vertically, max-width 600px
- Timeline view (inline in the run page or a dedicated component) — flat chronological list of all packets across all threads, sorted by packet ID. Each row: packet ID, thread color dot, speaker, truncated text, decision badges
- Wire the tab bar: LIVE, EVENTS, TIMELINE switch the main content area. State preserved across tab switches (scroll position, inspector collapse state)
- `web/src/components/BufferZone.tsx` — conditional section between incoming banner and tab bar, visible when `packets_to_resolve` is non-empty. Amber-styled packet cards, buffer count badge

**What NOT to build:** No scenario browser. No playback controls. No comparison overlay. No run history.

**How to verify:**
- EVENTS tab shows event cards with correct labels, status, and thread links
- Events appear at the right time (event_A opens at pkt_005, event_B at pkt_006)
- TIMELINE tab shows all packets in chronological order with correct thread colors
- Switching tabs preserves state — going to Timeline and back to Live doesn't lose scroll position
- BufferZone appears if a scenario uses buffering (may need a test scenario or manual verification)

**Depends on:** Phase 4 (dashboard foundation, base components, run page).

**Produces:** The complete dashboard from the mockup — all three tabs functional, full visual representation of TRM state.

---

### Phase 6 — Scenario Browser + Run Controls

**Goal:** Add the scenario management UI and run configuration so runs can be launched from the browser instead of hardcoded.

**What to build:**
- `web/src/app/scenarios/page.tsx` — list all scenarios grouped by tier, fetched from `GET /api/scenarios`
- `web/src/app/scenarios/[tier]/[scenario]/page.tsx` — scenario detail: README rendered as markdown, packet list, expected output preview, "Run This Scenario" button
- Run configuration before launch: speed factor control, buffer count
- Update the dashboard (`/`) to show scenario list and recent runs
- Navigation between pages

**What NOT to build:** No comparison overlay yet. No run history persistence. No playback/step-through.

**How to verify:**
- Scenario browser shows scenario_02_interleaved under tier_one
- Clicking into it shows the README, packets, expected output
- Clicking "Run" with a chosen speed factor launches the run and navigates to the live view
- Adding a new scenario folder to `data/` shows up in the browser

**Depends on:** Phase 5 (full dashboard exists to navigate to).

**Produces:** Complete workflow: browse scenarios → pick one → configure → run → watch live.

---

## Phase Checklist

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | FastAPI skeleton + scenario endpoints | **Done** |
| 2 | Runner service + WebSocket | **Done** |
| 3 | Next.js scaffold + raw WebSocket view | **Done** |
| 4 | Dashboard foundation + live view | **Done** |
| 5 | Events + timeline tabs | **Done** |
| 6 | Scenario browser + run controls | **Done** |
