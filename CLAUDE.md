# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

The Thread Routing Module (TRM) is part of the Albatross pipeline — a pattern for turning continuous data streams into structured intelligence. The TRM takes processed text packets and makes two independent routing decisions per packet: **thread** (which conversation?) and **event** (which real-world occurrence?). It is domain-agnostic; domain-specific signals live in packet metadata.

Read `docs/albatross.md` first for the big picture, then `docs/trm_spec.md` for the TRM specification.

## Running

```bash
# Activate the venv
source src/.venv/bin/activate

# Run the pipeline (requires ANTHROPIC_API_KEY in .env)
python -m src.main
```

The entry point is `src/main.py`. It loads a scenario's `packets.json`, queues packets with timestamp-aware replay (default 20x speed), and routes them through the LLM-backed router.

## Architecture

The pipeline has three stages wired together with asyncio:

1. **PacketLoader** (`src/pipeline/loader.py`) — reads `packets.json`, respects inter-packet timestamp gaps divided by `speed_factor`, pushes `ReadyPacket`s to the queue, sends `None` sentinel when done.
2. **PacketQueue** (`src/pipeline/queue.py`) — thin `asyncio.Queue` wrapper.
3. **TRMRouter** (`src/pipeline/router.py`) — the core. On each packet it serializes the full `TRMContext` (all active threads, events, buffered packets, and the incoming packet) as JSON, sends it to Claude Sonnet with a system prompt, parses the JSON response into a `RoutingRecord`, and updates internal state via `_apply()`.

### Models (`src/models/`)

- **`packets.py`**: `ProcessedPacket` (id, timestamp, text, metadata dict) and `ReadyPacket` (alias).
- **`router.py`**: `ThreadDecision`/`EventDecision` enums, `Thread`, `Event`, `RoutingRecord`, `TRMContext`. All Pydantic models — context is serialized with `model_dump(mode="json")`.

### Key design decisions

- **Stateful LLM**: Full session context is sent every turn. The LLM maintains and updates state, not a stateless classifier.
- **Two independent decision layers**: Thread and event routing are orthogonal. A thread can have no event; an event can span multiple threads.
- **Buffering**: Limited buffer slots (default 5) let the LLM defer ambiguous packets. Buffer exhaustion falls back to UNKNOWN.

## Test data

Scenarios live under `data/tier_one/`, `data/tier_two/`, etc. Each scenario folder contains:
- `packets.json` — input packets
- `expected_output.json` — golden truth (threads, events, routing records)
- `README.md` — scenario description

Currently only `data/tier_one/scenario_02_interleaved/` exists.

## Docs

- `docs/albatross.md` — the Albatross pipeline pattern
- `docs/trm_spec.md` — TRM spec: packet types, routing decisions, golden dataset tiers, scoring metrics
- `docs/runtime_loop.md` — per-packet execution loop, context schema, buffering, open problems
- `docs/trm_outline.md` — current state and next steps
- `docs/webui-api.md` — 6-phase plan for web UI and API
