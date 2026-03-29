# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

The Thread Routing Module (TRM) is part of the Albatross pipeline — a pattern for turning continuous data streams into structured intelligence. The TRM takes processed text packets and makes two independent routing decisions per packet: **thread** (which conversation?) and **event** (which real-world occurrence?). It is domain-agnostic; domain-specific signals live in packet metadata.

Read `docs/albatross.md` first for the big picture, then `docs/trm_spec.md` for the TRM specification.

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
```

```bash
# Run the Next.js frontend
cd web && npm run dev
```

```bash
# Launch both API + frontend together
./dev.sh
```

The CLI entry point is `src/main.py`. The API entry point is `api/main.py` (FastAPI). Both require the venv activated and `.env` with `ANTHROPIC_API_KEY` for live runs. The frontend dev server runs on `localhost:3000` and talks to the API on `localhost:8000`.

## Architecture

### TRM Pipeline (`src/`)

The pipeline has three stages wired together with asyncio:

1. **PacketLoader** (`src/pipeline/loader.py`) — reads `packets.json`, respects inter-packet timestamp gaps divided by `speed_factor`, pushes `ReadyPacket`s to the queue, sends `None` sentinel when done.
2. **PacketQueue** (`src/pipeline/queue.py`) — thin `asyncio.Queue` wrapper.
3. **TRMRouter** (`src/pipeline/router.py`) — the core. On each packet it serializes the full `TRMContext` (all active threads, events, buffered packets, and the incoming packet) as JSON, sends it to Claude Sonnet with a system prompt, parses the JSON response into a `RoutingRecord`, and updates internal state via `_apply()`.

### Models (`src/models/`)

- **`packets.py`**: `ProcessedPacket` (id, timestamp, text, metadata dict) and `ReadyPacket` (alias).
- **`router.py`**: `ThreadDecision`/`EventDecision` enums, `Thread`, `Event`, `RoutingRecord`, `TRMContext`. All Pydantic models — context is serialized with `model_dump(mode="json")`.

### API (`api/`)

FastAPI backend that wraps the TRM pipeline. The `api/` layer imports from `src/` — it wraps the existing pipeline, it doesn't replace it.

- **`api/routes/scenarios.py`** — `GET /api/scenarios` (list), `GET /api/scenarios/{tier}/{scenario}` (detail). Reads directly from the `data/` directory.
- **`api/routes/runs.py`** — `POST /api/runs` (start a run), `ws://localhost:8000/ws/runs/{run_id}` (live stream).
- **`api/services/runner.py`** — `RunManager` orchestrates runs as background asyncio tasks, broadcasts `run_started`, `packet_routed`, `run_complete` messages over WebSocket. Runs are in-memory (no persistence yet). The `packet_routed` message includes `context` (with `incoming_packet` popped out) and `incoming_packet` as a sibling field. Clients connecting mid-run receive the full message backlog.

### Frontend (`web/`)

Next.js (TypeScript, App Router) frontend with a visual dashboard for watching the TRM route packets in real time. Uses Tailwind CSS v4 with custom design tokens, shadcn/ui `cn()` utility, and JetBrains Mono font.

- **`web/src/types/trm.ts`** — TypeScript interfaces mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`.
- **`web/src/types/websocket.ts`** — Discriminated union for WebSocket messages: `RunStarted`, `PacketRouted`, `RunComplete`, `RunError`.
- **`web/src/hooks/useRunSocket.ts`** — Custom hook that opens a WebSocket to a run, parses messages, and maintains state via `useReducer`. Returns `{ status, context, routingRecords, latestPacketId, incomingPacket, error, scenario }`.
- **`web/src/lib/`** — `utils.ts` (cn helper), `threadColors.ts` (rotating color palette for threads), `packetDecisions.ts` (joins routing records to packets by ID), `api.ts` (API_BASE and WS_BASE constants).
- **`web/src/components/`** — Dashboard components: `Badge`, `DecisionBadge`, `SectionHeader`, `PacketCard`, `ThreadLane`, `EventCard`, `TimelineRow`, `BufferZone`, `IncomingBanner`, `TopBar`, `ContextInspector`, `HubTopBar`, `TabBar`.
- **`web/src/types/scenarios.ts`** — TypeScript interfaces for scenario data: `ScenarioSummary`, `TierGroup`, `ScenarioDetail`, `ScenarioPacket`, `ExpectedOutput`.
- **`web/src/app/page.tsx`** — Scenario hub: fetches `GET /api/scenarios`, lists tiers and scenarios with tabs (SCENARIOS active, LIVE/HISTORY disabled), links to `/scenarios/{tier}/{scenario}`.
- **`web/src/app/scenarios/[tier]/[scenario]/page.tsx`** — Scenario detail: renders README, packet list, expected output (collapsible), run config (speed factor/buffer count), launches a run via `POST /api/runs` and redirects to `/run/{runId}`.
- **`web/src/app/run/[runId]/page.tsx`** — Live run dashboard with three tabs: LIVE (thread lanes with color-coded packets), EVENTS (event cards with thread links), TIMELINE (chronological packet list). Incoming packet banner, buffer zone, decision badges, top bar with stats, collapsible context inspector.

### Tests (`tests/`)

Run with `python -m pytest tests/ -v`. LLM calls are mocked so no API key is needed. 16 tests total: scenario endpoints (9 tests) and run/WebSocket flow (7 tests).

### Key design decisions

- **Stateful LLM**: Full session context is sent every turn. The LLM maintains and updates state, not a stateless classifier.
- **Two independent decision layers**: Thread and event routing are orthogonal. A thread can have no event; an event can span multiple threads.
- **Buffering**: Limited buffer slots (default 5) let the LLM defer ambiguous packets. Buffer exhaustion falls back to UNKNOWN.

## Test data

Scenarios live under `data/tier_one/`, `data/tier_two/`, etc. Each scenario folder contains:
- `packets.json` — input packets
- `expected_output.json` — golden truth (threads, events, routing records)
- `README.md` — scenario description

Four Tier 1 scenarios exist: `scenario_01_simple_two_party`, `scenario_02_interleaved`, `scenario_03_event_opens_mid_thread`, `scenario_04_three_way_split`.

## Docs

- `docs/albatross.md` — the Albatross pipeline pattern
- `docs/trm_spec.md` — TRM spec: packet types, routing decisions, golden dataset tiers, scoring metrics
- `docs/trm_runtime_loop.md` — per-packet execution loop, context schema, buffering, open problems
- `docs/albatross_runtime_loop.md` — Albatross-level runtime loop
- `docs/trm_outline.md` — current state and next steps
- `docs/webui-api.md` — 6-phase plan for web UI and API (all phases done)
- `docs/ui_spec.md` — visual design spec: design tokens, component specs, layout, interaction patterns
- `docs/ui_mockup.jsx` — interactive React mockup with inline styles and mock data, component reference for Phase 4+
