# Albatross — Phase 3: Database & Inter-Module Data Pipeline

*The persistent backbone and the plumbing between pipeline stages.*

---

## Mental Model

Albatross is a staged pipeline:

```
Capture → Preprocessing → TRM → Analysis
```

Each stage enriches the same record and hands off to the next. Phase 3 introduces the shared database that makes this real — every stage reads from and writes to one place, and the UI reads from that same place on load.

```
capture/mock ──▶ DB ──▶ preprocessing/mock ──▶ DB ──▶ TRM ──▶ DB ──▶ UI
```

Without Phase 3, the system works but nothing persists. Refresh the page and state is gone. Phase 3 is what makes it a real pipeline instead of a demo.

**Invariant:** A transmission's UUID is assigned at capture and never changed or replaced. Every stage enriches the same record under the same UUID. This is the backbone of the entire system — it means you can always trace a routing decision, a thread, or an event back to the original transmission.

---

## Context

See `docs/albatross.md` for the full Albatross phase history and document naming notes.

---

## What Phase 3 Is

Phase 2 left the system in a state where everything works but nothing persists. Runs are in-memory. If you refresh the page, state is gone. The WebSocket is the only source of truth while a run is active. There is no database. There is no inter-module signaling. The web UI is connected to the TRM but not to a persistent store.

Phase 3 builds the foundation that makes the system real:

- A shared database that every pipeline stage writes to and reads from
- A defined contracts layer so modules agree on data shapes at their boundaries
- A mock pipeline that simulates the full Capture → Preprocessing → TRM → Analysis flow without requiring radio hardware
- A UI that hydrates from the database on load, so a page refresh loses nothing
- The groundwork for live mode — the UI architecture that will power real radio data

Scenarios remain what they are — a dev and tuning tool that runs against flat files. They do not need to touch the database. That simplicity is worth keeping.

---

## Repo Structure

### Current State

```
albatross/
├── api/                     # FastAPI backend
├── src/                     # TRM pipeline (PacketLoader, TRMRouter, models)
├── web/                     # Next.js frontend
├── data/                    # Scenario datasets (flat files)
├── docs/
└── tests/
```

### Target State (end of Phase 3)

```
albatross/
├── contracts/               # Shared — base packet types, ProcessedPacket, RoutingRecord
│   └── models.py
├── db/                      # Shared — schema, ORM models, migrations, session
│   ├── models.py
│   ├── session.py
│   └── migrations/
├── capture/
│   └── mock/                # Mock capture — emits fake TransmissionPackets on a timer
│       └── src/
├── preprocessing/
│   └── mock/                # Mock ASR — sleeps N seconds, passes packet through
│       └── src/
├── api/                     # FastAPI backend (extended with DB-read endpoints)
├── src/                     # TRM pipeline (extended with persistence layer)
├── web/                     # Next.js frontend (extended with DB hydration on load)
├── data/                    # Scenario datasets (unchanged)
├── docs/
└── tests/
```

The `contracts/` layer is the key structural decision. Every module imports from contracts, not from each other. If a new preprocessing implementation is added later — real ASR, a different model, a non-audio domain — it just has to produce a valid `ProcessedPacket`. The TRM does not care what produced it.

---

## The Approach

Rather than building the full radio capture pipeline (which requires hardware), Phase 3 uses an augmented scenario dataset to drive the mock pipeline.

**The plan:**

1. Take an existing Tier 1 scenario dataset
2. Augment each packet with realistic radio metadata — `talkgroup_id`, `source_unit`, `frequency`, `duration`, `encryption_status`, `audio_path` (fake path)
3. Build a mock capture module that reads this augmented dataset and writes records to the database with `status = 'captured'`, as if they had just arrived from a real radio
4. Build a mock preprocessing module that picks up `captured` records, waits a configurable delay (simulating ASR transcription time), then writes the text back and flips status to `processed`
5. Wire the existing TRM to pick up `processed` records from the database, route them, and write results back — `status = 'routed'`, routing records, thread and event updates
6. Update the web UI to hydrate from the database on load, and receive live updates via WebSocket as new packets are routed

When this is working end to end, a page refresh shows the current state. The architecture is production-shaped. Building live mode on top of it is a matter of swapping the mock capture module for the real one.

---

## Build Order

Detailed implementation specs for each step live in `docs/db-datapipeline.md` as they are written. This section defines the steps and their completion criteria.

### Step 1 — Database schema + ORM setup

Stand up the database. Define all models. Verify migrations work. Nothing else runs until this exists.

The schema is already designed in `docs/albatross_runtime_loop.md`. The tables are:
- `transmissions` — one row per packet, grows through the pipeline
- `threads` — one row per thread, LLM-maintained label
- `events` — one row per event
- `thread_events` — join table
- `routing_records` — audit log of every TRM decision

Engine: SQLite for local dev, PostgreSQL for production. The ORM should abstract this. ORM decision (SQLAlchemy, Tortoise, raw asyncpg) to be made at implementation time.

**Done when:** Schema exists, migrations run cleanly, models are importable from `db/`.

---

### Step 2 — Contracts layer ✓

Define the shared types in `contracts/` that all modules import. These are the boundary contracts — the shapes that must be honored at each stage handoff.

- `TransmissionPacket` — base capture output
- `ProcessedPacket` — TRM input (domain-agnostic)
- `ReadyPacket` — alias for ProcessedPacket
- `RoutingRecord` — TRM output

**Done.** `contracts/models.py` exists with all four boundary types. All modules import from `contracts/`, not from each other. `src/models/packets.py` re-exports from contracts. `RoutingRecord` uses plain strings for decision fields (enums stay TRM-internal). 28 tests pass.

---

### Step 3 — Augment a Tier 1 scenario with radio metadata

Take `scenario_02_interleaved`. Add radio-style metadata to each packet:

```json
{
  "id": "uuid-here",
  "timestamp": "2024-01-15T14:23:01Z",
  "text": "Hey, did you get the memo about the new shift schedule?",
  "metadata": {
    "talkgroup_id": 1001,
    "source_unit": 4021,
    "frequency": 851.0125,
    "duration": 3.2,
    "encryption_status": false,
    "audio_path": "out/wav/mock_001.wav"
  }
}
```

This becomes the seed data for the mock pipeline. It looks like real radio data. The TRM treats the metadata as routing signals, same as it would in production.

**Done when:** Augmented `packets.json` exists. Text content is unchanged — only metadata is added.

---

### Step 4 — Mock capture module

A script in `capture/mock/` that reads the augmented packets and writes them to the database one at a time, with a configurable delay between packets, as if they were arriving from a live radio source.

Each packet written as a `transmissions` row with `status = 'captured'`. The text field is intentionally left null — capture doesn't know the text yet, that's preprocessing's job.

Signaling mechanism for Phase 3: database polling. Simple, no extra infrastructure, inherently restartable. ZMQ push is deferred until real capture is built.

**Done when:** Running the mock capture script populates the `transmissions` table with `status = 'captured'` rows, one by one, on a timer.

---

### Step 5 — Mock preprocessing module

A script in `preprocessing/mock/` that polls for `captured` records, simulates ASR processing time (configurable sleep, default 5–10 seconds), then writes the text back to the record and flips `status = 'processed'`.

The text already exists in the augmented dataset — mock preprocessing just copies it into the `text` field. Also writes mock ASR metadata (`asr_model = 'mock'`, `asr_confidence = 1.0`, `asr_passes = 1`).

**Done when:** Records that enter as `status = 'captured'` emerge as `status = 'processed'` with text populated, after a simulated delay.

---

### Step 6 — TRM persistence layer

Extend the existing TRM to write to the database after each routing decision. The in-memory state update logic in `_apply()` does not change — a persistence layer wraps it.

After each packet is routed:
- Write `RoutingRecord` to `routing_records` table
- Update `transmissions` row: `thread_id`, `event_id`, `thread_decision`, `event_decision`, `status = 'routed'`
- Create or update row in `threads`
- Create or update row in `events`
- Update `thread_events` join table

**Critical:** The DB write for each packet must be atomic. In-memory state and database state must not drift — if the DB write fails, the in-memory update should not be applied either. Consistency between the two is the invariant this step must preserve.

The TRM also needs a DB-driven entry point — polling for `processed` records rather than consuming from `PacketLoader`. Scenario tooling is unaffected; it continues to use `PacketLoader` and in-memory state. The DB-driven path is a separate entry point.

**Done when:** A packet that enters as `status = 'processed'` emerges as `status = 'routed'`, with routing records, thread, and event rows written to the database. In-memory and DB state match after every packet.

---

### Step 7 — UI hydration from database

Update the web UI and API so that on page load, current state is read from the database rather than requiring an active WebSocket session.

New API endpoints:
- `GET /api/live/threads` — all open threads with their packets
- `GET /api/live/events` — all open events with linked threads
- `GET /api/live/packets` — recent routing records

On page load: fetch current state from these endpoints, render the dashboard. Then open WebSocket for live updates as new packets are routed. New packets push over WebSocket and also exist in the DB — the two are always in sync.

**Done when:** Page refresh shows current state. A new browser tab opened mid-run shows the same state as the existing tab. The WebSocket is the live edge, the DB is the ground truth.

---

## What Done Looks Like

The integration test for Phase 3:

1. Start the database
2. Start mock capture — packets begin appearing in `transmissions` with `status = 'captured'`
3. Start mock preprocessing — after a delay, records flip to `status = 'processed'` with text
4. Start TRM (DB-driven mode) — records flip to `status = 'routed'`, threads and events appear
5. Open the web UI — current state renders correctly
6. Refresh the page — nothing is lost
7. Open a second browser tab — same state as the first

If all seven steps work, Phase 3 is done.

---

## What Phase 3 Does Not Include

- Real radio capture (hardware-dependent, Phase 4+)
- Real ASR / Whisper integration (Phase 4+)
- Scorer
- UI scenario builder
- Prompt versioning
- Multi-run comparison

---

## Future Items

Things decided, recorded, not happening now:

- **UI scenario builder** — build datasets packet by packet in the UI; thread/event annotations generate `expected_output.json` automatically
- **Live mode UI** — full live data source connection, stream visualization
- **Prompt versioning** — save and compare system prompt versions across runs
- **Multi-run comparison** — score comparison across prompt iterations or scenario runs