# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project

Albatross is a general-purpose pipeline for turning continuous data streams into structured, queryable intelligence. The reference implementation is a P25 trunked radio dispatch intelligence system.

The pipeline has five stages: Data Stream → Packets → Preprocessing → TRM → Analysis.

The **Thread Routing Module (TRM)** is the intelligence layer. It takes processed text packets and makes two independent routing decisions per packet: **thread** (which conversation?) and **event** (which real-world occurrence?). It is domain-agnostic — domain-specific signals live in packet metadata.

Read `docs/albatross.md` first for the big picture. See `docs/albatross.md` for the full phase history.

## Current Phase

**Phase 3 — Database & Inter-Module Data Pipeline** is complete. See `docs/albatross_phase_3.md` for the plan and `docs/db-datapipeline.md` for implementation specs.

Phases 1 (TRM core), 2 (Web UI + API), and 3 (DB + data pipeline) are complete. The `db/` package has 5 ORM models, Alembic migrations, async session factory, a reset script, and `persist_routing_result()` for atomic TRM writes. The `contracts/` package has 4 boundary types with `to_orm()` mapping to ORM models. Mock capture (`capture/mock/run.py`) and preprocessing (`preprocessing/mock/run.py`) scripts simulate the full pipeline. `src/main_live.py` is the DB-driven TRM entry point — polls for processed rows and persists routing results. The `/live` page hydrates from the database on load via three REST endpoints (`/api/live/threads`, `/events`, `/transmissions`) and polls every 3 seconds for updates.

The existing scenario tooling (`data/`, `api/`, `src/`, `web/`) is **not being replaced** — it continues to work as-is for development and tuning. Phase 3 adds new modules alongside it.

## Running

```bash
# Activate the venv
source src/.venv/bin/activate

# Run the pipeline directly (requires ANTHROPIC_API_KEY in .env)
python -m src.main

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
# Run the full mock pipeline (capture + preprocessing + TRM against DB)
alembic upgrade head              # ensure schema exists
python db/reset.py                # clear all tables
python preprocessing/mock/run.py & # start preprocessing (polls for captured rows)
python capture/mock/run.py &      # start capture (writes packets to DB every 10s)
python src/main_live.py           # start TRM (polls for processed rows, routes + persists)
```

The CLI entry point is `src/main.py`. The API entry point is `api/main.py` (FastAPI). Both require the venv activated and `.env` with `ANTHROPIC_API_KEY` for live runs. The frontend dev server runs on `localhost:3000` and talks to the API on `localhost:8000`.

## Architecture

### Contracts (`contracts/`)

Shared Pydantic types for cross-module boundaries. All modules import boundary types from `contracts/`, not from each other.

- **`contracts/models.py`** — `TransmissionPacket` (capture output, with `to_orm()` method), `ProcessedPacket` (TRM input, domain-agnostic), `ReadyPacket` (alias for `ProcessedPacket`), `RoutingRecord` (TRM output, plain string decision fields, with `to_orm()` method).

### Mock Pipeline (`capture/`, `preprocessing/`)

Simulates the full Capture → Preprocessing flow against the database using `packets_radio.json` as source data.

- **`capture/mock/run.py`** — Reads augmented packets, constructs `TransmissionPacket`, calls `to_orm()`, writes to DB with `status = 'captured'` and `text = null`. 10s interval between packets.
- **`preprocessing/mock/run.py`** — Polls for `captured` rows, flips to `processing`, waits 10s (simulated ASR), writes text from source dataset + ASR metadata, flips to `processed`. Exits when no captured/processing rows remain.
- **`db/reset.py`** — Truncates all data tables in FK-safe order for re-runs.

### TRM Pipeline (`src/`)

The pipeline has three stages wired together with asyncio:

1. **PacketLoader** (`src/pipeline/loader.py`) — reads `packets.json`, respects inter-packet timestamp gaps divided by `speed_factor`, pushes `ReadyPacket`s to the queue, sends `None` sentinel when done.
2. **PacketQueue** (`src/pipeline/queue.py`) — thin `asyncio.Queue` wrapper.
3. **TRMRouter** (`src/pipeline/router.py`) — the core. On each packet it serializes the full `TRMContext` (all active threads, events, buffered packets, and the incoming packet) as JSON, sends it to Claude Sonnet with a system prompt, parses the JSON response into a `RoutingRecord`, and updates internal state via `_apply()`.

Two entry points: `src/main.py` (scenario mode — reads from flat files, in-memory only) and `src/main_live.py` (DB mode — polls for `processed` rows, routes, persists via `db/persist.py`). Scenario tooling is unaffected by the DB path.

### Models (`src/models/`)

- **`packets.py`**: Re-exports `ProcessedPacket` and `ReadyPacket` from `contracts.models`.
- **`router.py`**: TRM-internal types — `ThreadDecision`/`EventDecision` enums, `Thread`, `Event`, `TRMContext`. Imports `RoutingRecord` from `contracts.models`. All Pydantic models — context is serialized with `model_dump(mode="json")`.

### Database (`db/`)

SQLAlchemy 2.0 async ORM with Alembic migrations. Dev engine is SQLite via `aiosqlite`. Prod engine will be PostgreSQL via `asyncpg`.

- **`db/base.py`** — `DeclarativeBase` subclass.
- **`db/models.py`** — 5 ORM models: `Transmission`, `Thread`, `Event`, `ThreadEvent`, `RoutingRecord`.
- **`db/session.py`** — Async engine from `DATABASE_URL` env var (default `sqlite+aiosqlite:///./albatross.db`), `AsyncSessionLocal` factory, `get_session` dependency.
- **`db/persist.py`** — `persist_routing_result()`: atomic per-packet persistence. Upserts thread/event/join, writes routing record, updates transmission to `routed`. Called by `src/main_live.py` after each `router.route()` call.
- **`db/migrations/`** — Alembic migrations. `env.py` configured for async with `render_as_batch=True` for SQLite.

### API (`api/`)

FastAPI backend that wraps the TRM pipeline. The `api/` layer imports from `src/` — it wraps the existing pipeline, it doesn't replace it.

- **`api/routes/scenarios.py`** — `GET /api/scenarios` (list), `GET /api/scenarios/{tier}/{scenario}` (detail). Reads directly from the `data/` directory.
- **`api/routes/runs.py`** — `POST /api/runs` (start a run), `ws://localhost:8000/ws/runs/{run_id}` (live stream).
- **`api/routes/live.py`** — `GET /api/live/threads` (open threads with packets), `GET /api/live/events` (open events with thread IDs), `GET /api/live/transmissions` (routed transmissions ordered by timestamp). All use `Depends(get_session)` for DB access.
- **`api/services/runner.py`** — `RunManager` orchestrates runs as background asyncio tasks, broadcasts `run_started`, `packet_routed`, `run_complete` messages over WebSocket. Runs are in-memory (no persistence yet). The `packet_routed` message includes `context` (with `incoming_packet` popped out) and `incoming_packet` as a sibling field. Clients connecting mid-run receive the full message backlog.

### Frontend (`web/`)

Next.js (TypeScript, App Router) frontend with a visual dashboard for watching the TRM route packets in real time. Uses Tailwind CSS v4 with custom design tokens and JetBrains Mono font.

- **`web/src/types/trm.ts`** — TypeScript interfaces mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`.
- **`web/src/types/websocket.ts`** — Discriminated union for WebSocket messages: `RunStarted`, `PacketRouted`, `RunComplete`, `RunError`.
- **`web/src/hooks/useRunSocket.ts`** — Custom hook that opens a WebSocket to a run, parses messages, and maintains state via `useReducer`. Returns `{ status, context, routingRecords, latestPacketId, incomingPacket, error, scenario }`.
- **`web/src/hooks/useLiveData.ts`** — Custom hook for the live page. Fetches `/api/live/threads`, `/events`, `/transmissions` on mount, reconstructs `TRMContext`, polls every 3s. Returns `{ status, context, routingRecords, latestPacketId, error }`.
- **`web/src/lib/`** — `utils.ts` (cn helper), `threadColors.ts` (rotating color palette for threads), `packetDecisions.ts` (joins routing records to packets by ID), `api.ts` (API_BASE and WS_BASE constants).
- **`web/src/components/`** — Dashboard components: `Badge`, `DecisionBadge`, `SectionHeader`, `PacketCard`, `ThreadLane`, `EventCard`, `TimelineRow`, `BufferZone`, `IncomingBanner`, `TopBar`, `ContextInspector`, `HubTopBar`, `TabBar`.
- **`web/src/app/page.tsx`** — Scenario hub: lists tiers and scenarios, links to detail pages.
- **`web/src/app/scenarios/[tier]/[scenario]/page.tsx`** — Scenario detail: README, packet list, expected output, run config, launches run.
- **`web/src/app/run/[runId]/page.tsx`** — Live run dashboard: LIVE (thread lanes), EVENTS (event cards), TIMELINE (chronological list). Incoming packet banner, buffer zone, decision badges, context inspector.
- **`web/src/app/live/page.tsx`** — DB-hydrated live dashboard. Same components as run page, minus IncomingBanner/BufferZone (transient state). Polls DB every 3s for updates.

### Tests (`tests/`)

Run with `python -m pytest tests/ -v`. LLM calls are mocked so no API key is needed. 43 tests total: contracts layer (5 tests), mock pipeline (3 tests), scenario endpoints (9 tests), run/WebSocket flow (7 tests), database models (7 tests), TRM persistence (5 tests), and live API endpoints (7 tests).

### Key Design Decisions

- **Stateful LLM**: Full session context is sent every turn. The LLM maintains and updates state, not a stateless classifier.
- **Two independent decision layers**: Thread and event routing are orthogonal. A thread can have no event; an event can span multiple threads.
- **Buffering**: Limited buffer slots (default 5) let the LLM defer ambiguous packets. Buffer exhaustion falls back to UNKNOWN.
- **DB as single source of truth** (Phase 3): All pipeline stages write to the shared database. WebSocket is the live edge only — the DB is the ground truth. Page hydration reads from DB, not from in-memory state.
- **Scenario tooling stays separate**: Scenarios run against flat files and in-memory state. They do not touch the database. This path is permanent — it exists for development and prompt tuning regardless of what production does.

## Test Data

Scenarios live under `data/tier_one/`, `data/tier_two/`, etc. Each scenario folder contains:
- `packets.json` — input packets
- `expected_output.json` — golden truth (threads, events, routing records)
- `README.md` — scenario description

Four Tier 1 scenarios exist: `scenario_01_simple_two_party`, `scenario_02_interleaved`, `scenario_03_event_opens_mid_thread`, `scenario_04_three_way_split`.

The augmented dataset for the Phase 3 mock pipeline lives at `data/tier_one/scenario_02_interleaved/packets_radio.json` — same packets with radio metadata added. See `docs/db-datapipeline.md` for details.

## Docs

| Document | Description |
|----------|-------------|
| `docs/albatross.md` | Start here — the Albatross pattern, pipeline stages, phase history |
| `docs/albatross_phase_3.md` | Phase 3 plan — DB, contracts layer, mock pipeline, UI hydration |
| `docs/db-datapipeline.md` | Phase 3 implementation specs — synthetic data, simulation parameters, reset |
| `docs/albatross_runtime_loop.md` | Full radio pipeline architecture and DB schema (primary Phase 3 reference) |
| `docs/trm_spec.md` | TRM spec — packet types, routing decisions, golden dataset tiers, scoring |
| `docs/trm_runtime_loop.md` | TRM runtime loop — context schema, per-packet decision cycle, buffering |
| `docs/trm_outline.md` | TRM current state and key design decisions |
| `docs/webui-api.md` | Web UI & API build plan — six sub-phases, all complete |
| `docs/ui_spec.md` | Visual design spec — design tokens, components, layout |
| `docs/ui_mockup.jsx` | Interactive React mockup — component reference |