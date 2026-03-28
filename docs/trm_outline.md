# TRM Outline

*Current state of the Thread Routing Module — architecture, structure, and what's next.*

---

## What's Built

- Async packet pipeline — `PacketLoader` reads `packets.json` and pushes `ReadyPacket` objects into an `asyncio.Queue` with timestamp-based replay and configurable `speed_factor`
- `TRMRouter` — LLM-backed router that processes one `ReadyPacket` at a time, maintains full session context, and emits a `RoutingRecord` per packet
- Four Tier 1 scenarios — `scenario_01` through `scenario_04` — built
- FastAPI backend (`api/`) with scenario listing/detail endpoints and run management
- Runner service — wraps the TRM pipeline, streams `run_started`, `packet_routed`, `run_complete` messages over WebSocket
- Test suite (`tests/`) — 16 tests covering scenario endpoints and run/WebSocket flow (mocked LLM)

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
│   └── planning/
│       └── trm_outline.md
├── tests/
│   ├── conftest.py           # Shared fixtures (async test client)
│   ├── test_scenarios.py     # Phase 1 endpoint tests
│   └── test_runs.py          # Phase 2 endpoint + WebSocket tests (mocked LLM)
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

1. Build the frontend — Next.js scaffold, WebSocket connection, live run view (webui-api Phases 3–4)
2. Scenario browser + run controls (Phase 5)
3. Review mode + expected vs actual comparison (Phase 6)
4. Build the Scorer — compare `RoutingRecord` list against `expected_output.json`, compute per-metric and composite scores
5. Run all four scenarios through the scorer and iterate on the system prompt until passing