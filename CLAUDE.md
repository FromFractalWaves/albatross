# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project

Albatross is a general-purpose pipeline for turning continuous data streams into structured, queryable intelligence. The reference implementation is a P25 trunked radio dispatch intelligence system.

The pipeline has five stages: Data Stream → Packets → Preprocessing → TRM → Analysis.

The **Thread Routing Module (TRM)** is the intelligence layer. It takes processed text packets and makes two independent routing decisions per packet: **thread** (which conversation?) and **event** (which real-world occurrence?). It is domain-agnostic — domain-specific signals live in packet metadata.

Read `docs/albatross.md` first for the big picture. See `docs/albatross.md` for the full phase history.

## Current State

All core systems are built: TRM core, Web UI + API, database + data pipeline, UI restructure, and real capture pipeline. The capture layer (`capture/trunked_radio/`) has all three processes: flowgraph (GNU Radio + OP25, requires hardware), bridge, and backend. ASR/transcription is not built.

The `db/` package has 5 ORM models, Alembic migrations, async session factory, a reset script, and `persist_routing_result()` for atomic TRM writes. The `contracts/` package has boundary types with `to_orm()` mapping to ORM models, plus WebSocket message types in `contracts/ws.py` (including `PipelineStageDefinition` for pipeline observability). The mock pipeline runs as an in-process async pipeline inside the API via `LivePipelineManager` (`api/services/live_pipeline.py`), which inherits from `BasePipelineManager` (`api/services/base_pipeline.py`). It pushes stage-level messages (`packet_captured`, `packet_preprocessed`, `packet_routed`) over WebSocket at `/ws/live/mock`. `PipelineStarted` carries `stages` (list of stage definitions) instead of `total_packets`. The `/live` page hydrates from the database on load via three REST endpoints (`/api/live/threads`, `/events`, `/transmissions`) using TanStack Query, then receives real-time updates via WebSocket — no polling. A `PipelineStages` component shows per-stage packet counts that increment in real time.

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

The mock pipeline is started from the UI: open `/live/mock` and click "Start Mock Pipeline", which calls `POST /api/mock/start`. The pipeline runs in-process inside the API — no separate scripts needed. The standalone scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) still exist for manual/standalone usage but are not called by the API.

The CLI entry point is `trm/main.py`. The API entry point is `api/main.py` (FastAPI). Both require the venv activated and `.env` with `ANTHROPIC_API_KEY` for live runs. The frontend dev server runs on `localhost:3000` and talks to the API on `localhost:8000`.

```bash
# Run the real capture pipeline (requires GNU Radio + OP25 + RTL-SDR)
# Three separate terminals:
source trm/.venv/bin/activate && python -m capture.trunked_radio.backend     # Process 3 — backend (venv)
source trm/.venv/bin/activate && python -m capture.trunked_radio.bridge      # Process 2 — bridge (venv)
export OP25_APPS_DIR=/path/to/op25/op25/gr-op25_repeater/apps
python3 -m capture.trunked_radio.flowgraph   # Process 1 — flowgraph (system python3, needs GNU Radio)
```

## Architecture

### Contracts (`contracts/`)

Shared Pydantic types for cross-module boundaries. All modules import boundary types from `contracts/`, not from each other.

- **`contracts/models.py`** — `TransmissionPacket` (capture output, with `to_orm()` method), `ProcessedPacket` (TRM input, domain-agnostic), `ReadyPacket` (alias for `ProcessedPacket`), `RoutingRecord` (TRM output, plain string decision fields, with `to_orm()` method).
- **`contracts/ws.py`** — Pydantic models for live pipeline WebSocket messages: `PipelineStageDefinition`, `PipelineStarted` (carries `stages` list, not `total_packets`), `PacketCaptured`, `PacketPreprocessed`, `PacketRouted`, `PipelineComplete`, `PipelineError`.

### Capture Pipeline (`capture/trunked_radio/`)

Real P25 trunked radio capture — three cooperating OS processes connected by ZMQ. See `docs/sources/trunked_radio/` for full architecture docs.

Shared modules:
- **`config.py`** — All constants: ZMQ ports (5557 metadata, 5560-5567 PCM lanes, 5580 tagged PCM, 5581 control, 5590 packet push), SDR params (855.9625 MHz center, 3.2 Msps, gains), lane manager timing (2s sweep, 5s stale age), `OP25_APPS_DIR` env var, timeouts, WAV dir.
- **`models.py`** — Internal `@dataclass` types: `MetadataEvent`, `LaneAssignment`, `ActiveCall`, `CompletedCall`. Hot-path models — not Pydantic.
- **`tsbk.py`** — Standalone P25 TSBK parser (`TSBKParser`). Decodes grants, grant updates, identifier updates using 96-bit integer extraction matching OP25's `tk_p25.py` convention. Resolves channel IDs to frequencies via freq table. `process_qmsg()` handles OP25 `msg_queue` wire format (packed type field, bytes payload). GPL v3.

Process 1 — Flowgraph (requires GNU Radio + gr-osmosdr + gr-op25 + RTL-SDR):
- **`lane_manager.py`** — Thread-safe lane allocation. `on_grant(tgid, freq, srcaddr)` assigns/retunes/preempts voice lanes. `sweep_stale(max_age)` releases idle lanes. Pure logic, no GNU Radio dependency.
- **`metadata_poller.py`** — Daemon thread bridging `gr.msg_queue` → TSBK parser → lane manager → ZMQ PUSH on :5557. Drains msg_queue, annotates grants with `lane_id`, sweeps stale lanes every ~2s. Logs 10s status summaries with message/TSBK/decoded counts.
- **`flowgraph.py`** — `P25Flowgraph(gr.top_block)`. SDR source → control lane (`p25_demod_cb` → `p25_frame_assembler` → msg_queue) + 3 voice lanes (`p25_demod_cb` → `p25_frame_assembler` → ZMQ push sinks on :5560-5562). Both control and voice use `p25_demod_cb` which has efficient two-stage decimation (BPF decim=32 → mixer → LPF decim=4 → arb_resampler). Entry point: `python3 -m capture.trunked_radio.flowgraph`.

Process 2 — Bridge:
- **`bridge.py`** — `LaneState` (thread-safe lane→tgid mapping), `MetadataSubscriber` (pulls JSON from :5557, updates LaneState, translates `srcaddr` → `source_unit`, forwards to :5581), `PCMLaneSubscriber` ×8 (pulls PCM from :5560-5567, tags with tgid, pushes multipart to :5580). Entry point: `python -m capture.trunked_radio.bridge`.

Process 3 — Backend:
- **`buffer_manager.py`** — `BufferManager` call state machine. Tracks active calls by tgid, accumulates PCM chunks, handles grant/lane reassignment, source unit change splitting, sweep timeouts, drain.
- **`wav_writer.py`** — `WavWriter` writes mono int16 8000 Hz WAV files from `CompletedCall` audio.
- **`packet_builder.py`** — `build_packet()` maps `CompletedCall` + WAV path to `TransmissionPacket` (from `contracts.models`).
- **`packet_sink.py`** — `PacketSink` protocol with three implementations: `ZmqPacketSink` (PUSH to :5590), `StdoutPacketSink`, `JsonlPacketSink`.
- **`backend.py`** — `CaptureBackend` async event loop. ZMQ poll on PCM + control sockets, periodic sweep, `_finalize_calls` writes WAV + DB + sink. Entry point: `python -m capture.trunked_radio.backend`.

### Mock Pipeline (`capture/mock/`, `preprocessing/`, `api/services/live_pipeline.py`)

The primary mock pipeline runs in-process inside the API via `LivePipelineManager`. Three async stages connected by `PacketQueue`s: capture (reads `packets_radio.json`, writes to DB, emits to queue), preprocessing (simulates ASR, writes to DB, emits to queue), and routing (calls `TRMRouter`, persists via `persist_routing_result`, broadcasts over WebSocket). Started via `POST /api/mock/start`, streams progress to `/ws/live/mock`.

Standalone scripts still exist for manual usage:
- **`capture/mock/run.py`** — Reads augmented packets, writes to DB with `status = 'captured'`. 10s interval.
- **`preprocessing/mock/run.py`** — Polls for `captured` rows, simulates ASR, writes text + flips to `processed`.
- **`trm/main_live.py`** — Polls for `processed` rows, routes, persists.
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
- **`api/routes/mock.py`** — `POST /api/mock/start` (reset DB + start in-process pipeline), `POST /api/mock/stop` (cancel pipeline), `GET /api/mock/status` (check if running), `ws://localhost:8000/ws/live/mock` (live pipeline WebSocket). Uses `LivePipelineManager` from `app.state`.
- **`api/services/runner.py`** — `RunManager` orchestrates scenario runs as background asyncio tasks, broadcasts `run_started`, `packet_routed`, `run_complete` messages over WebSocket. Runs are in-memory (no persistence yet). The `packet_routed` message includes `context` (with `incoming_packet` popped out) and `incoming_packet` as a sibling field. Clients connecting mid-run receive the full message backlog.
- **`api/services/base_pipeline.py`** — `BasePipelineManager` abstract base class for pipeline managers. Provides lifecycle (start/stop), WebSocket subscriber fanout, message backlog, and stage metadata. Subclasses implement `pipeline_stages` (property) and `_run_pipeline` (async method). See `docs/pipeline/new_pipelines.md` for how to add new pipelines.
- **`api/services/live_pipeline.py`** — `LivePipelineManager` (inherits `BasePipelineManager`) orchestrates the mock pipeline as a single asyncio task with three concurrent stages (capture, preprocessing, routing). Declares its stages via `pipeline_stages` property. Broadcasts stage-level messages (`pipeline_started`, `packet_captured`, `packet_preprocessed`, `packet_routed`, `pipeline_complete`) over WebSocket. Late-joining clients receive the full message backlog.

### Frontend (`web/`)

Next.js (TypeScript, App Router) frontend with a visual dashboard for watching the TRM route packets in real time. Uses Tailwind CSS v4 with custom design tokens and JetBrains Mono font.

- **`web/src/types/trm.ts`** — TypeScript interfaces mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`.
- **`web/src/types/websocket.ts`** — Discriminated unions for WebSocket messages: `WSMessage` (scenario runs: `RunStarted`, `PacketRouted`, `RunComplete`, `RunError`) and `LiveWSMessage` (live pipeline: `PipelineStarted`, `PacketCaptured`, `PacketPreprocessed`, `LivePacketRouted`, `PipelineComplete`, `PipelineError`).
- **`web/src/hooks/useRunSocket.ts`** — Custom hook that opens a WebSocket to a run, parses messages, and maintains state via `useReducer`. Returns `{ status, context, routingRecords, latestPacketId, incomingPacket, error, scenario }`.
- **`web/src/hooks/useLiveData.ts`** — Custom hook for the live page. Hydrates from REST via TanStack Query on mount, then receives real-time updates via WebSocket at `/ws/live/mock`. Tracks per-stage packet counts via `useState` (seeded from `pipeline_started`, incremented by stage messages). Returns `{ status, context, routingRecords, latestPacketId, incomingPacket, stages, error }`.
- **`web/src/hooks/useTheme.ts`** — Dark/light theme toggle hook. Reads/writes `localStorage`, toggles `dark`/`light` class on `<html>`. SSR-safe.
- **`web/src/lib/`** — `utils.ts` (cn helper), `threadColors.ts` (rotating color palette for threads), `packetDecisions.ts` (joins routing records to packets by ID), `api.ts` (API_BASE and WS_BASE constants).
- **`web/src/components/`** — Dashboard components: `Badge`, `DecisionBadge`, `SectionHeader`, `PacketCard`, `ThreadLane`, `EventCard`, `TimelineRow`, `BufferZone`, `IncomingBanner`, `TopBar`, `ContextInspector`, `HubTopBar`, `TabBar`, `ThemeToggle`, `PipelineStages`.
- **`web/src/app/page.tsx`** — Homepage hub: two cards linking to `/trm` (TRM Tools) and `/sources` (Live Data).
- **`web/src/app/trm/page.tsx`** — TRM Tools hub: card linking to `/trm/scenarios`.
- **`web/src/app/trm/scenarios/page.tsx`** — Scenario browser: lists tiers and scenarios, links to detail pages.
- **`web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`** — Scenario detail: README, packet list, expected output, run config, launches run. Back-link to `/trm/scenarios`.
- **`web/src/app/sources/page.tsx`** — Source selection hub: card for Mock Pipeline linking to `/live/mock`.
- **`web/src/app/run/[runId]/page.tsx`** — Live run dashboard: LIVE (thread lanes), EVENTS (event cards), TIMELINE (chronological list). Incoming packet banner, buffer zone, decision badges, context inspector.
- **`web/src/app/live/[source]/page.tsx`** — WebSocket-driven live dashboard, dynamic by source. Mock pipeline controls shown when source is "mock". Same components as run page. Hydrates from REST on load, then updates in real time via WebSocket push.

### Tests (`tests/`)

Run with `python -m pytest tests/ -v`. LLM calls are mocked so no API key is needed. 105 tests total: contracts layer (5 tests), mock pipeline (3 tests), scenario endpoints (9 tests), run/WebSocket flow (7 tests), database models (7 tests), TRM persistence (5 tests), live API endpoints (7 tests), mock pipeline API (6 tests), live pipeline/WebSocket (9 tests), TSBK parser (7 tests), buffer manager (13 tests), WAV writer (4 tests), packet builder (5 tests), capture backend (2 tests), bridge (8 tests), and lane manager (8 tests).

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
| `docs/pipeline/new_pipelines.md` | How to add a new pipeline — inherit BasePipelineManager, declare stages, add routes |
| `docs/trm/spec.md` | TRM spec — packet types, routing decisions, golden dataset tiers, scoring |
| `docs/trm/runtime_loop.md` | TRM runtime loop — context schema, per-packet decision cycle, buffering |
| `docs/trm/scenarios.md` | Scenarios system — data layer, API, service layer, web UI, end-to-end flow |
| `docs/web/api.md` | Web UI & API architecture — REST endpoints, WebSocket protocol, frontend pages |
| `docs/web/ui_spec.md` | Visual design spec — design tokens, components, layout |
| `docs/web/ui_mockup.jsx` | Interactive React mockup — component reference |
| `docs/sources/trunked_radio/architecture.md` | Capture pipeline — three-process architecture, ZMQ wiring, signal chain |
| `docs/sources/trunked_radio/hardware.md` | Hardware and software dependencies — GNU Radio, OP25, RTL-SDR, env vars |
| `docs/vision.md` | What Albatross should become — design intent, not a roadmap |
| `specs/radio_integration.md` | Live RF validation — test results, bugs fixed, CPU budget blocker, next steps |