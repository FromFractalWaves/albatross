# TRM Outline

*Current state of the Thread Routing Module — architecture, structure, and what's next.*

---

## What's Built

- Async packet pipeline — `PacketLoader` reads `packets.json` and pushes `ReadyPacket` objects into an `asyncio.Queue` with timestamp-based replay and configurable `speed_factor`
- `TRMRouter` — LLM-backed router that processes one `ReadyPacket` at a time, maintains full session context, and emits a `RoutingRecord` per packet
- One Tier 1 scenario — `scenario_02_interleaved` — built and running

---

## File Structure

```
thread-routing-module/
├── data/
│   └── tier_one/
│       └── scenario_02_interleaved/
│           ├── packets.json
│           ├── expected_output.json
│           └── README.md
├── docs/
│   ├── albatross.md
│   ├── trm_spec.md
│   ├── runtime_loop.md
│   └── planning/
│       └── trm_outline.md
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
| `scenario_01_simple_two_party` | Not yet written |
| `scenario_02_interleaved` | Written, router running against it |
| `scenario_03_event_opens_mid_thread` | Not yet written |

---

## What's Next

1. Build the Scorer — compare `RoutingRecord` list against `expected_output.json`, compute per-metric and composite scores
2. Build the UI — replace raw terminal output with something readable
3. Write `scenario_01` and `scenario_03`
4. Run all three scenarios through the scorer and iterate on the system prompt until passing