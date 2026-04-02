# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project

Albatross is a general-purpose pipeline for turning continuous data streams into structured, queryable intelligence. The reference implementation is a P25 trunked radio dispatch intelligence system.

The pipeline has five stages: Data Stream → Packets → Preprocessing → TRM → Analysis.

The **Thread Routing Module (TRM)** is the intelligence layer. It takes processed text packets and makes two independent routing decisions per packet: **thread** (which conversation?) and **event** (which real-world occurrence?). It is domain-agnostic — domain-specific signals live in packet metadata.

Read `docs/albatross.md` first for the big picture. See `docs/albatross.md` for the full phase history.

## Current State

All core systems are built: TRM core, Web UI + API, database + data pipeline, and UI restructure. Real data integration (capture, ASR, radio hardware) is not built — it requires physical radio hardware.

The `db/` package has 5 ORM models, Alembic migrations, async session factory, a reset script, and `persist_routing_result()` for atomic TRM writes. The `contracts/` package has 4 boundary types with `to_orm()` mapping to ORM models. Mock capture (`capture/mock/run.py`) and preprocessing (`preprocessing/mock/run.py`) scripts simulate the full pipeline. `trm/main_live.py` is the DB-driven TRM entry point — polls for processed rows and persists routing results. The `/live` page hydrates from the database on load via three REST endpoints (`/api/live/threads`, `/events`, `/transmissions`) and polls every 3 seconds for updates.

The existing scenario tooling (`data/`, `api/`, `trm/`, `web/`) is **not being replaced** — it continues to work as-is for development and tuning.

## Running

```bash
# Activate the venv
source trm/.venv/bin/activate

# Run the pipeline directly (requires ANTHROPIC_API_KEY in .env)
python -m trm.main

# Run the API server
uvicorn api.main:app --reload

# Run tests (no API key needed — LLM calls are mocked)
python -m pytest tests/ -v

# Run database migrations
alembic upgrade head
```

```bash
# Run the Next.js frontend
cd web && npm run dev
```

```bash
# Launch both API + frontend together
./dev.sh
```

```bash
# Launch the full mock pipeline + API + frontend in one command
./live.sh
```

```bash
# Run the full mock pipeline manually (capture + preprocessing + TRM against DB)
alembic upgrade head              # ensure schema exists
python db/reset.py                # clear all tables
python preprocessing/mock/run.py & # start preprocessing (polls for captured rows)
python capture/mock/run.py &      # start capture (writes packets to DB every 10s)
python trm/main_live.py           # start TRM (polls for processed rows, routes + persists)
```

The CLI entry point is `trm/main.py`. The API entry point is `api/main.py` (FastAPI). Both require the venv activated and `.env` with `ANTHROPIC_API_KEY` for live runs. The frontend dev server runs on `localhost:3000` and talks to the API on `localhost:8000`.

## Architecture

### Contracts (`contracts/`)

Shared Pydantic types for cross-module boundaries. All modules import boundary types from `contracts/`, not from each other.

- **`contracts/models.py`** — `TransmissionPacket` (capture output, with `to_orm()` method), `ProcessedPacket` (TRM input, domain-agnostic), `ReadyPacket` (alias for `ProcessedPacket`), `RoutingRecord` (TRM output, plain string decision fields, with `to_orm()` method).

### Mock Pipeline (`capture/`, `preprocessing/`)

Simulates the full Capture → Preprocessing flow against the database using `packets_radio.json` as source data.

- **`capture/mock/run.py`** — Reads augmented packets, constructs `TransmissionPacket`, calls `to_orm()`, writes to DB with `status = 'captured'` and `text = null`. 10s interval between packets.
- **`preprocessing/mock/run.py`** — Polls for `captured` rows, flips to `processing`, waits 10s (simulated ASR), writes text from source dataset + ASR metadata, flips to `processed`. Exits when no captured/processing rows remain.
- **`db/reset.py`** — Truncates all data tables in FK-safe order for re-runs.

### TRM Pipeline (`trm/`)

The pipeline has three stages wired together with asyncio:

1. **PacketLoader** (`trm/pipeline/loader.py`) — reads `packets.json`, respects inter-packet timestamp gaps divided by `speed_factor`, pushes `ReadyPacket`s to the queue, sends `None` sentinel when done.
2. **PacketQueue** (`trm/pipeline/queue.py`) — thin `asyncio.Queue` wrapper.
3. **TRMRouter** (`trm/pipeline/router.py`) — the core. On each packet it serializes the full `TRMContext` (all active threads, events, buffered packets, and the incoming packet) as JSON, sends it to Claude Sonnet with a system prompt, parses the JSON response into a `RoutingRecord`, and updates internal state via `_apply()`.

Two entry points: `trm/main.py` (scenario mode — reads from flat files, in-memory only) and `trm/main_live.py` (DB mode — polls for `processed` rows, routes, persists via `db/persist.py`). Scenario tooling is unaffected by the DB path.

### Models (`trm/models/`)

- **`packets.py`**: Re-exports `ProcessedPacket` and `ReadyPacket` from `contracts.models`.
- **`router.py`**: TRM-internal types — `ThreadDecision`/`EventDecision` enums, `Thread`, `Event`, `TRMContext`. Imports `RoutingRecord` from `contracts.models`. All Pydantic models — context is serialized with `model_dump(mode="json")`.

### Database (`db/`)

SQLAlchemy 2.0 async ORM with Alembic migrations. Dev engine is SQLite via `aiosqlite`. Prod engine will be PostgreSQL via `asyncpg`.

- **`db/base.py`** — `DeclarativeBase` subclass.
- **`db/models.py`** — 5 ORM models: `Transmission`, `Thread`, `Event`, `ThreadEvent`, `RoutingRecord`.
- **`db/session.py`** — Async engine from `DATABASE_URL` env var (default `sqlite+aiosqlite:///./albatross.db`), `AsyncSessionLocal` factory, `get_session` dependency.
- **`db/persist.py`** — `persist_routing_result()`: atomic per-packet persistence. Upserts thread/event/join, writes routing record, updates transmission to `routed`. Called by `trm/main_live.py` after each `router.route()` call.
- **`db/migrations/`** — Alembic migrations. `env.py` configured for async with `render_as_batch=True` for SQLite.

### API (`api/`)

FastAPI backend that wraps the TRM pipeline. The `api/` layer imports from `trm/` — it wraps the existing pipeline, it doesn't replace it.

- **`api/routes/scenarios.py`** — `GET /api/scenarios` (list), `GET /api/scenarios/{tier}/{scenario}` (detail). Reads directly from the `data/` directory.
- **`api/routes/runs.py`** — `POST /api/runs` (start a run), `ws://localhost:8000/ws/runs/{run_id}` (live stream).
- **`api/routes/live.py`** — `GET /api/live/threads` (open threads with packets), `GET /api/live/events` (open events with thread IDs), `GET /api/live/transmissions` (routed transmissions ordered by timestamp). All use `Depends(get_session)` for DB access.
- **`api/routes/mock.py`** — `POST /api/mock/start` (reset DB + launch pipeline subprocesses), `POST /api/mock/stop` (terminate subprocesses), `GET /api/mock/status` (check if running). Process handles stored in `app.state.mock_processes`.
- **`api/services/runner.py`** — `RunManager` orchestrates runs as background asyncio tasks, broadcasts `run_started`, `packet_routed`, `run_complete` messages over WebSocket. Runs are in-memory (no persistence yet). The `packet_routed` message includes `context` (with `incoming_packet` popped out) and `incoming_packet` as a sibling field. Clients connecting mid-run receive the full message backlog.

### Frontend (`web/`)

Next.js (TypeScript, App Router) frontend with a visual dashboard for watching the TRM route packets in real time. Uses Tailwind CSS v4 with custom design tokens and JetBrains Mono font.

- **`web/src/types/trm.ts`** — TypeScript interfaces mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`.
- **`web/src/types/websocket.ts`** — Discriminated union for WebSocket messages: `RunStarted`, `PacketRouted`, `RunComplete`, `RunError`.
- **`web/src/hooks/useRunSocket.ts`** — Custom hook that opens a WebSocket to a run, parses messages, and maintains state via `useReducer`. Returns `{ status, context, routingRecords, latestPacketId, incomingPacket, error, scenario }`.
- **`web/src/hooks/useLiveData.ts`** — Custom hook for the live page. Fetches `/api/live/threads`, `/events`, `/transmissions` on mount, reconstructs `TRMContext`, polls every 3s. Returns `{ status, context, routingRecords, latestPacketId, error }`.
- **`web/src/hooks/useTheme.ts`** — Dark/light theme toggle hook. Reads/writes `localStorage`, toggles `dark`/`light` class on `<html>`. SSR-safe.
- **`web/src/lib/`** — `utils.ts` (cn helper), `threadColors.ts` (rotating color palette for threads), `packetDecisions.ts` (joins routing records to packets by ID), `api.ts` (API_BASE and WS_BASE constants).
- **`web/src/components/`** — Dashboard components: `Badge`, `DecisionBadge`, `SectionHeader`, `PacketCard`, `ThreadLane`, `EventCard`, `TimelineRow`, `BufferZone`, `IncomingBanner`, `TopBar`, `ContextInspector`, `HubTopBar`, `TabBar`, `ThemeToggle`.
- **`web/src/app/page.tsx`** — Homepage hub: two cards linking to `/trm` (TRM Tools) and `/sources` (Live Data).
- **`web/src/app/trm/page.tsx`** — TRM Tools hub: card linking to `/trm/scenarios`.
- **`web/src/app/trm/scenarios/page.tsx`** — Scenario browser: lists tiers and scenarios, links to detail pages.
- **`web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`** — Scenario detail: README, packet list, expected output, run config, launches run. Back-link to `/trm/scenarios`.
- **`web/src/app/sources/page.tsx`** — Source selection hub: card for Mock Pipeline linking to `/live/mock`.
- **`web/src/app/run/[runId]/page.tsx`** — Live run dashboard: LIVE (thread lanes), EVENTS (event cards), TIMELINE (chronological list). Incoming packet banner, buffer zone, decision badges, context inspector.
- **`web/src/app/live/[source]/page.tsx`** — DB-hydrated live dashboard, dynamic by source. Mock pipeline controls shown when source is "mock". Same components as run page, minus IncomingBanner/BufferZone (transient state). Polls DB every 3s for updates.

### Tests (`tests/`)

Run with `python -m pytest tests/ -v`. LLM calls are mocked so no API key is needed. 49 tests total: contracts layer (5 tests), mock pipeline (3 tests), scenario endpoints (9 tests), run/WebSocket flow (7 tests), database models (7 tests), TRM persistence (5 tests), live API endpoints (7 tests), and mock pipeline API (6 tests).

### Key Design Decisions

- **Stateful LLM**: Full session context is sent every turn. The LLM maintains and updates state, not a stateless classifier.
- **Two independent decision layers**: Thread and event routing are orthogonal. A thread can have no event; an event can span multiple threads.
- **Buffering**: Limited buffer slots (default 5) let the LLM defer ambiguous packets. Buffer exhaustion falls back to UNKNOWN.
- **DB as single source of truth**: All pipeline stages write to the shared database. WebSocket is the live edge only — the DB is the ground truth. Page hydration reads from DB, not from in-memory state.
- **Scenario tooling stays separate**: Scenarios run against flat files and in-memory state. They do not touch the database. This path is permanent — it exists for development and prompt tuning regardless of what production does.

## Test Data

Scenarios live under `data/tier_one/`, `data/tier_two/`, etc. Each scenario folder contains:
- `packets.json` — input packets
- `expected_output.json` — golden truth (threads, events, routing records)
- `README.md` — scenario description

Four Tier 1 scenarios exist: `scenario_01_simple_two_party`, `scenario_02_interleaved`, `scenario_03_event_opens_mid_thread`, `scenario_04_three_way_split`.

The augmented dataset for the mock pipeline lives at `data/tier_one/scenario_02_interleaved/packets_radio.json` — same packets with radio metadata added. See `docs/pipeline/database.md` for details.

## Docs

| Document | Description |
|----------|-------------|
| `docs/albatross.md` | Start here — the Albatross pattern, pipeline stages, phase history |
| `docs/pipeline/architecture.md` | Full radio pipeline architecture — DB schema, stage handoffs, production TRM requirements |
| `docs/pipeline/database.md` | Database & data pipeline — ORM models, contracts layer, mock pipeline, persistence |
| `docs/pipeline/mock_pipeline.md` | Mock pipeline end-to-end — stages, status progression, API, frontend, timing |
| `docs/trm/spec.md` | TRM spec — packet types, routing decisions, golden dataset tiers, scoring |
| `docs/trm/runtime_loop.md` | TRM runtime loop — context schema, per-packet decision cycle, buffering |
| `docs/trm/scenarios.md` | Scenarios system — data layer, API, service layer, web UI, end-to-end flow |
| `docs/web/api.md` | Web UI & API architecture — REST endpoints, WebSocket protocol, frontend pages |
| `docs/web/ui_spec.md` | Visual design spec — design tokens, components, layout |
| `docs/web/ui_mockup.jsx` | Interactive React mockup — component reference |
| `docs/vision.md` | What Albatross should become — design intent, not a roadmap |