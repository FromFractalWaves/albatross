# TRM Outline

*Current state of the Thread Routing Module — architecture, structure, and what's next.*

---

## What's Built

### TRM Pipeline (`src/`)

- Async packet pipeline — `PacketLoader` reads `packets.json` and pushes `ReadyPacket` objects into an `asyncio.Queue` with timestamp-based replay and configurable `speed_factor`
- `TRMRouter` — LLM-backed router that processes one `ReadyPacket` at a time, maintains full session context, and emits a `RoutingRecord` per packet
- Four Tier 1 scenarios — `scenario_01` through `scenario_04` — built

### API (`api/`)

- FastAPI backend with CORS configured for the Next.js dev server (`localhost:3000`)
- `GET /api/scenarios` — lists scenarios grouped by tier, scanned from the filesystem
- `GET /api/scenarios/{tier}/{scenario}` — returns packets, expected output, and README
- `POST /api/runs` — starts an async run against a scenario, returns `run_id`
- `ws://localhost:8000/ws/runs/{run_id}` — streams `run_started`, `packet_routed`, `run_complete` (or `run_error`) messages
- `RunManager` orchestrates runs as background asyncio tasks. Runs are in-memory (no persistence). Clients connecting mid-run receive the full message backlog.

### Frontend (`web/`)

- Next.js (TypeScript, App Router) with Tailwind CSS v4, custom design tokens, JetBrains Mono font
- TypeScript types mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`, plus WebSocket message types (`RunStartedMessage`, `PacketRoutedMessage`, `RunCompleteMessage`, `RunErrorMessage`)
- `useRunSocket` hook — opens a WebSocket, parses messages via `useReducer`, tracks `context`, `routingRecords`, `latestPacketId`, `incomingPacket`, `status`, `error`, and `scenario`
- Utility libraries: `threadColors.ts` (rotating color palette), `packetDecisions.ts` (joins routing records to packets), `utils.ts` (cn helper)
- Dashboard components: `Badge`, `DecisionBadge`, `SectionHeader`, `PacketCard`, `ThreadLane`, `EventCard`, `TimelineRow`, `BufferZone`, `IncomingBanner`, `TopBar`, `ContextInspector`
- Home page (`page.tsx`) — launches a run and redirects to `/run/{runId}`
- Live run page (`run/[runId]/page.tsx`) — visual dashboard with three tabs: LIVE (thread lanes with color-coded packets), EVENTS (event cards with thread links), TIMELINE (chronological packet list). Incoming packet banner with pulsing LLM indicator, buffer zone for deferred packets, decision badges, top bar with status/stats, collapsible context inspector

### Tests (`tests/`)

- 16 tests total, all mocked (no API key needed)
- Scenario endpoint tests (9): list, sort order, detail content, structure, 404 handling
- Run/WebSocket tests (7): run creation, validation, full WebSocket integration (verifies message ordering, backlog delivery, end-to-end flow with mocked LLM)

---

## File Structure

```
thread-routing-module/
├── api/
│   ├── main.py               # FastAPI app, CORS, RunManager setup
│   ├── routes/
│   │   ├── scenarios.py      # GET /api/scenarios, GET /api/scenarios/{tier}/{scenario}
│   │   └── runs.py           # POST /api/runs, WebSocket /ws/runs/{run_id}
│   └── services/
│       └── runner.py         # RunManager — wraps TRM pipeline, manages run state
├── data/
│   └── tier_one/
│       ├── scenario_01_simple_two_party/
│       ├── scenario_02_interleaved/
│       ├── scenario_03_event_opens_mid_thread/
│       └── scenario_04_three_way_split/
├── docs/
│   ├── albatross.md
│   ├── trm_spec.md
│   ├── runtime_loop.md
│   ├── webui-api.md
│   ├── ui_spec.md
│   ├── ui_mockup.jsx
│   └── trm_outline.md
├── tests/
│   ├── conftest.py           # Shared fixtures (async test client)
│   ├── test_scenarios.py     # Scenario endpoint tests (9)
│   └── test_runs.py          # Run + WebSocket tests (7)
├── dev.sh                        # Launch API + frontend together
├── web/
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css       # Design tokens (Tailwind v4 @theme), base styles
│   │   │   ├── layout.tsx        # Root layout, JetBrains Mono font
│   │   │   ├── page.tsx          # Run launcher — redirects to /run/{runId}
│   │   │   └── run/
│   │   │       └── [runId]/
│   │   │           └── page.tsx  # Live run dashboard
│   │   ├── components/
│   │   │   ├── Badge.tsx         # Reusable badge (default/solid/outline)
│   │   │   ├── BufferZone.tsx    # Amber-themed section for buffered packets
│   │   │   ├── ContextInspector.tsx # Collapsible raw JSON inspector
│   │   │   ├── DecisionBadge.tsx # Routing decision badge (new/existing/none/buffer/unknown)
│   │   │   ├── EventCard.tsx     # Event card with status, label, thread link badges
│   │   │   ├── IncomingBanner.tsx # Incoming packet banner with pulsing indicator
│   │   │   ├── PacketCard.tsx    # Packet row with speaker, text, decision badges
│   │   │   ├── SectionHeader.tsx # Section header with optional count
│   │   │   ├── ThreadLane.tsx    # Thread column with color-coded packet list
│   │   │   ├── TimelineRow.tsx   # Compact horizontal row for timeline view
│   │   │   └── TopBar.tsx        # Sticky top bar with status and stats
│   │   ├── hooks/
│   │   │   └── useRunSocket.ts   # WebSocket hook with useReducer
│   │   ├── lib/
│   │   │   ├── utils.ts          # cn() helper (clsx + tailwind-merge)
│   │   │   ├── threadColors.ts   # Thread color palette mapping
│   │   │   └── packetDecisions.ts # Routing record lookup by packet ID
│   │   └── types/
│   │       ├── trm.ts            # ReadyPacket, Thread, Event, RoutingRecord, TRMContext
│   │       └── websocket.ts      # RunStarted, PacketRouted, RunComplete, RunError messages
│   └── ...
└── src/
    ├── main.py
    ├── models/
    │   ├── packets.py        # ProcessedPacket, ReadyPacket
    │   └── router.py         # Thread, Event, RoutingRecord, TRMContext, decision enums
    └── pipeline/
        ├── loader.py         # PacketLoader
        ├── queue.py          # PacketQueue
        └── router.py         # TRMRouter, system prompt
```

---

## Key Decisions

**Async queue with sentinel** — `PacketLoader` pushes a `None` sentinel when the stream is exhausted. The router consumer checks for it and exits cleanly. This boundary is always honored even when preprocessing is trivial.

**Speed factor replay** — the loader uses actual timestamp deltas between packets and divides by `speed_factor` to replay at accelerated speed. Default is `20.0x`. Set to `1.0` for real-time replay.

**LLM as context manager** — the router passes full session state to the LLM on every turn: all active threads with their packets, all active events, buffered packets, and buffers remaining. The LLM holds and updates state rather than being used as a stateless classifier.

**Thread and event decisions are independent** — made separately on every packet. A thread can exist with no event. A packet can join an existing thread while simultaneously opening a new event.

**Pydantic models throughout** — `ProcessedPacket`, `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext` are all Pydantic models. Clean serialization to/from JSON at the API boundary.

**`incoming_packet` sent as sibling field** — the runner pops `incoming_packet` from the context snapshot and sends it as a top-level field in the `packet_routed` WebSocket message. This keeps the context object clean (no stale incoming_packet after routing) while giving the frontend the current packet. The TypeScript types and `useRunSocket` hook already account for this.

**Message backlog on connect** — when a WebSocket client connects to a run already in progress, the runner sends all previously broadcast messages before streaming new ones. This means late-joining clients get full history without re-running.

---

## Tier 1 Scenarios

| Scenario | Status |
|----------|--------|
| `scenario_01_simple_two_party` | Written |
| `scenario_02_interleaved` | Written, router running against it |
| `scenario_03_event_opens_mid_thread` | Written |
| `scenario_04_three_way_split` | Written |

---

## What's Next

1. Scenario browser + run controls (webui-api Phase 6)
3. Review mode + expected vs actual comparison (Phase 7)
4. Build the Scorer — compare `RoutingRecord` list against `expected_output.json`, compute per-metric and composite scores
5. Run all four scenarios through the scorer and iterate on the system prompt until passing
