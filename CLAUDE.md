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
- **`api/services/runner.py`** — `RunManager` orchestrates runs as background asyncio tasks, broadcasts `run_started`, `packet_routed`, `run_complete` messages over WebSocket. Runs are in-memory (no persistence yet).

### Frontend (`web/`)

Next.js (TypeScript, App Router) frontend that connects to the API over WebSocket for live run observation.

- **`web/src/types/trm.ts`** — TypeScript interfaces mirroring the Pydantic models: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`.
- **`web/src/types/websocket.ts`** — Discriminated union for WebSocket messages: `RunStarted`, `PacketRouted`, `RunComplete`, `RunError`.
- **`web/src/hooks/useRunSocket.ts`** — Custom hook that opens a WebSocket to a run, parses messages, and maintains state via `useReducer`. Returns `{ status, context, routingRecords, error, scenario }`.
- **`web/src/app/page.tsx`** — Minimal page: starts a run via `POST /api/runs`, connects via WebSocket, renders raw TRM context JSON updating in real time.

### Tests (`tests/`)

Run with `python -m pytest tests/ -v`. LLM calls are mocked so no API key is needed. Tests cover scenario endpoints (10 tests) and run/WebSocket flow (7 tests).

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
- `docs/runtime_loop.md` — per-packet execution loop, context schema, buffering, open problems
- `docs/trm_outline.md` — current state and next steps
- `docs/webui-api.md` — 6-phase plan for web UI and API
