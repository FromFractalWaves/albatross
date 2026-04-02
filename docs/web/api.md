# Web UI & API Architecture

*Architecture reference for the TRM's web interface and FastAPI backend.*

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
| `POST` | `/api/runs` | Start a new run (body specifies packet source — scenario tier and name) |

A run is a single execution of the TRM runtime against a packet source. Starting a run returns a `run_id` that the frontend uses to connect via WebSocket. Runs are in-memory only — no persistence or listing endpoint.

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

The `packet_routed` message includes `incoming_packet` as a top-level sibling field (popped from the context snapshot). The frontend never polls — everything is pushed.

#### REST Endpoints — Mock Pipeline

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/mock/start` | Reset DB and start in-process mock pipeline |
| `POST` | `/api/mock/stop` | Cancel running mock pipeline |
| `GET` | `/api/mock/status` | Check if mock pipeline is running — returns `{"status": "running" \| "stopped"}` |

The start endpoint resets all DB tables, then starts the pipeline as an in-process asyncio task via `LivePipelineManager`. The pipeline runs three concurrent stages (capture, preprocessing, routing) connected by async queues, writing to the DB at each stage and broadcasting progress over WebSocket.

#### WebSocket — Live Pipeline

| Path | Description |
|------|-------------|
| `ws://localhost:8000/ws/live/mock` | Live stream of pipeline stage messages |

After starting the pipeline via `POST /api/mock/start`, the frontend opens a WebSocket connection. The backend pushes stage-level messages:

| Type | When |
|------|------|
| `pipeline_started` | Pipeline begins — includes `total_packets` |
| `packet_captured` | Packet written to DB — includes `packet_id`, `timestamp`, `metadata` |
| `packet_preprocessed` | ASR complete — includes `packet_id`, `text` |
| `packet_routed` | TRM routing complete — includes `routing_record`, `context`, `incoming_packet` |
| `pipeline_complete` | All packets processed — includes `routing_records` |
| `pipeline_error` | Something broke — includes `error` |

Clients connecting mid-pipeline receive the full message backlog. The `packet_routed` message has the same shape as the scenario WebSocket's `packet_routed`.

> For the full mock pipeline reference — stages, status progression, timing, API response shapes, and frontend integration — see `docs/pipeline/mock_pipeline.md`.

### Frontend (Next.js + TypeScript)

#### Pages

**`/` — Homepage Hub.** Minimal landing page with two cards linking to `/trm` (TRM Tools) and `/sources` (Live Data). No data fetching.

**`/trm` — TRM Tools Hub.** Card linking to `/trm/scenarios`. Hub layout matching the homepage card style.

**`/trm/scenarios` — Scenario Browser.** Lists all scenarios grouped by tier, fetched from `GET /api/scenarios`. Tabs for SCENARIOS (active), LIVE, HISTORY. Links to individual scenario detail pages at `/trm/scenarios/{tier}/{scenario}`.

**`/trm/scenarios/{tier}/{scenario}` — Scenario Detail.** Shows README, packet list, expected output (collapsible), run configuration (speed factor, buffer count). "Run This Scenario" button launches a run and redirects to the live view. Back-link points to `/trm/scenarios`.

**`/sources` — Source Selection Hub.** Card for Mock Pipeline linking to `/live/mock`. Static "available" status indicator.

**`/run/{run_id}` — Live Run View.** The main screen. During a run: incoming packet highlighted, active threads as columns/lanes with packets stacking, active events with thread links, routing decision badge, buffered packets in a holding area, buffer counter.

**`/live/[source]` — Live Pipeline.** WebSocket-driven dashboard, dynamic by source. Mock pipeline controls (Start/Stop buttons, status indicator) shown when source is "mock". Same components as the run page. Hydrates from REST via TanStack Query on load, then receives real-time updates via WebSocket at `/ws/live/mock`.

#### Key UI Components

**Thread Lane** — vertical column per thread, packets stacking in arrival order, color-coded, label updating as the LLM revises it.

**Event Card** — event label, status, connected thread lanes with visual links.

**Routing Decision Badge** — per-packet indicator for thread and event decisions. Green/red when comparing against expected.

**Context Inspector** — collapsible panel with raw JSON, for debugging.

### File Structure

```
api/                        # FastAPI backend
├── main.py                 # App setup, CORS, lifespan
├── routes/
│   ├── scenarios.py        # Scenario listing and detail endpoints
│   ├── runs.py             # Run control + WebSocket
│   ├── live.py             # DB-hydrated live endpoints
│   └── mock.py             # Mock pipeline start/stop/status + live WebSocket
└── services/
    ├── runner.py           # Wraps TRM pipeline — starts runs, manages state
    └── live_pipeline.py    # In-process mock pipeline with WebSocket broadcast

web/                        # Next.js frontend
└── src/
    ├── app/                # Next.js app router pages
    ├── components/         # React components
    ├── hooks/              # useRunSocket, useLiveData, useTheme
    ├── lib/                # Utilities, constants, color palette
    └── types/              # TypeScript types mirroring Pydantic models
```

The `api/` layer imports from `trm/` — it wraps the existing pipeline, it doesn't replace it.

---

## What's Not Here

This API covers scenarios, runs, live data, and mock pipeline control. For future directions (scorer, real live ingest, multi-run comparison, authentication), see `docs/vision.md`.
