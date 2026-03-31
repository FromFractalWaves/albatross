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
- Utility libraries: `threadColors.ts` (rotating color palette), `packetDecisions.ts` (joins routing records to packets), `utils.ts` (cn helper), `api.ts` (API_BASE and WS_BASE constants)
- Scenario types: `types/scenarios.ts` (`ScenarioSummary`, `TierGroup`, `ScenarioDetail`, `ScenarioPacket`, `ExpectedOutput`)
- Dashboard components: `Badge`, `DecisionBadge`, `SectionHeader`, `PacketCard`, `ThreadLane`, `EventCard`, `TimelineRow`, `BufferZone`, `IncomingBanner`, `TopBar`, `ContextInspector`, `HubTopBar`, `TabBar`
- Scenario hub (`page.tsx`) — lists all scenarios grouped by tier, links to detail pages
- Scenario detail page (`scenarios/[tier]/[scenario]/page.tsx`) — renders README, packet list, expected output (collapsible), run config (speed factor, buffer count), launches run and redirects to `/run/{runId}`
- Live run page (`run/[runId]/page.tsx`) — visual dashboard with three tabs: LIVE (thread lanes with color-coded packets), EVENTS (event cards with thread links), TIMELINE (chronological packet list). Incoming packet banner with pulsing LLM indicator, buffer zone for deferred packets, decision badges, top bar with status/stats, collapsible context inspector

### Contracts (`contracts/`)

- Shared Pydantic types for cross-module boundaries — the single source of truth for types that cross pipeline stage boundaries
- `TransmissionPacket` — capture output, preprocessing input (radio-specific)
- `ProcessedPacket` — preprocessing output, TRM input (domain-agnostic)
- `ReadyPacket` — type alias for `ProcessedPacket` (naming convention for pipeline position)
- `RoutingRecord` — TRM output, one per routed packet (plain string decision fields)
- All modules import boundary types from `contracts/`, not from each other

### Database (`db/`)

- SQLAlchemy 2.0 async ORM with Alembic migrations
- 5 models: `Transmission` (grows through pipeline stages), `Thread`, `Event`, `ThreadEvent` (join table), `RoutingRecord` (audit log)
- Async session factory from `DATABASE_URL` env var, defaults to SQLite via `aiosqlite`
- Alembic configured for async with `render_as_batch=True` for SQLite compatibility

### Tests (`tests/`)

- 31 tests total, all mocked (no API key needed)
- Contracts tests (5): import validation, TransmissionPacket construction, ReadyPacket alias, RoutingRecord string decisions, datetime parsing
- Mock pipeline tests (3): capture writes, preprocessing updates, DB reset
- Scenario endpoint tests (9): list, sort order, detail content, structure, 404 handling
- Run/WebSocket tests (7): run creation, validation, full WebSocket integration (verifies message ordering, backlog delivery, end-to-end flow with mocked LLM)
- Database model tests (7): imports, table creation, CRUD for all 5 models

---

## File Structure

```
albatross/
├── contracts/
│   ├── __init__.py
│   └── models.py            # Boundary types: TransmissionPacket, ProcessedPacket, ReadyPacket, RoutingRecord
├── api/
│   ├── main.py               # FastAPI app, CORS, RunManager setup
│   ├── routes/
│   │   ├── scenarios.py      # GET /api/scenarios, GET /api/scenarios/{tier}/{scenario}
│   │   └── runs.py           # POST /api/runs, WebSocket /ws/runs/{run_id}
│   └── services/
│       └── runner.py         # RunManager — wraps TRM pipeline, manages run state
├── capture/
│   └── mock/
│       └── run.py            # Mock capture — reads packets_radio.json, writes to DB
├── preprocessing/
│   └── mock/
│       └── run.py            # Mock preprocessing — polls captured rows, simulates ASR
├── db/
│   ├── base.py               # DeclarativeBase
│   ├── models.py             # Transmission, Thread, Event, ThreadEvent, RoutingRecord
│   ├── session.py            # Async engine, session factory, get_session dependency
│   ├── reset.py              # Truncates all data tables in FK-safe order
│   └── migrations/
│       ├── env.py            # Async Alembic config
│       └── versions/         # Migration scripts
├── data/
│   └── tier_one/
│       ├── scenario_01_simple_two_party/
│       ├── scenario_02_interleaved/
│       ├── scenario_03_event_opens_mid_thread/
│       └── scenario_04_three_way_split/
├── docs/
│   ├── albatross.md
│   ├── trm_spec.md
│   ├── trm_runtime_loop.md
│   ├── albatross_runtime_loop.md
│   ├── webui-api.md
│   ├── ui_spec.md
│   ├── ui_mockup.jsx
│   └── trm_outline.md
├── tests/
│   ├── conftest.py           # Shared fixtures (async test client, DB engine/session)
│   ├── test_scenarios.py     # Scenario endpoint tests (9)
│   ├── test_runs.py          # Run + WebSocket tests (7)
│   └── test_db.py            # Database model tests (7)
├── dev.sh                        # Launch API + frontend together
├── web/
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css       # Design tokens (Tailwind v4 @theme), base styles
│   │   │   ├── layout.tsx        # Root layout, JetBrains Mono font
│   │   │   ├── page.tsx          # Scenario hub — lists tiers and scenarios
│   │   │   ├── scenarios/
│   │   │   │   └── [tier]/
│   │   │   │       └── [scenario]/
│   │   │   │           └── page.tsx  # Scenario detail — README, packets, run config
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
│   │   │   ├── TopBar.tsx        # Sticky top bar with status and stats
│   │   │   ├── HubTopBar.tsx    # Top bar for the scenario hub
│   │   │   └── TabBar.tsx       # Reusable tab bar component
│   │   ├── hooks/
│   │   │   └── useRunSocket.ts   # WebSocket hook with useReducer
│   │   ├── lib/
│   │   │   ├── utils.ts          # cn() helper (clsx + tailwind-merge)
│   │   │   ├── threadColors.ts   # Thread color palette mapping
│   │   │   ├── packetDecisions.ts # Routing record lookup by packet ID
│   │   │   └── api.ts            # API_BASE, WS_BASE constants
│   │   └── types/
│   │       ├── trm.ts            # ReadyPacket, Thread, Event, RoutingRecord, TRMContext
│   │       ├── websocket.ts      # RunStarted, PacketRouted, RunComplete, RunError messages
│   │       └── scenarios.ts      # ScenarioSummary, TierGroup, ScenarioDetail, etc.
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

Phase 3 is in progress. Sub-phases 3.1 (DB schema + ORM), 3.2 (contracts layer), and 3.2b (mock pipeline + DB reset) are complete. Remaining:

1. **Sub-phase 3.3** — TRM persistence layer + `main_live.py` DB-driven entry point
2. **Sub-phase 3.4** — UI hydration from database + live WebSocket updates

Future (post Phase 3): Scorer, prompt iteration, real ASR integration
