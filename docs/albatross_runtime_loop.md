# Albatross Runtime — Radio Pipeline

*How a radio transmission moves from RF capture through to structured intelligence.*

---

## Overview

This document traces the full lifecycle of a single radio transmission through the Albatross pipeline — from RF capture to queryable intelligence in a database. It covers the four pipeline stages, the data model at each stage, the database schema, and the handoff mechanisms between stages.

The reference implementation is a P25 Phase 1 trunked radio dispatch intelligence system. The capture layer is specific to P25/OP25. Everything from the `ProcessedPacket` boundary onward is domain-agnostic.

For the TRM's internal per-packet decision loop, see `trm_runtime_loop.md`. This document covers the pipeline around it.

---

## The UUID Spine

Every transmission gets a UUID at capture. That UUID follows it through every stage of the pipeline:

```
Capture (UUID assigned)
    → Preprocessing (same UUID, text added)
        → TRM (same UUID, routing decisions added)
            → Analysis (same UUID, queryable)
```

The UUID is the primary key. You can always trace from a routing decision, a thread, or an event back to the original audio file. Nothing in the pipeline creates a new identity for a transmission — it grows a richer record under the same UUID.

---

## The Four Stages

### Stage 1 — Capture

**What happens:** P25 radio transmissions are received, decoded, and packaged into `TransmissionPacket` objects.

**This is not simple.** The capture layer is a multi-component system:

1. **GNU Radio flowgraph** (`flowgraph.py`) — runs gr-op25 blocks directly (not the stock OP25 app layer). One fixed control lane at the P25 control channel frequency drives the metadata queue. N pooled voice lanes (configurable via `VOICE_LANE_CAP`, default 8) are dynamically allocated on channel grants and returned on call end or inactivity.

2. **ZMQ bridge** (`zmq_bridge.py`) — sits between the flowgraph and the backend. Subscribes to per-lane PCM streams and the metadata queue. Correlates lane PCM with TGID metadata from the control channel using `LaneState` cross-indexing. Forwards tagged PCM (multipart: JSON header + raw int16) and control messages over ZMQ.

3. **Capture backend** (`capture_backend.py`) — receives tagged PCM and control messages from the bridge. Maintains per-TGID call buffers via `BufferManager`. On call end or inactivity timeout: writes a WAV file, builds a `TransmissionPacket`, and emits it.

**Output:** A `TransmissionPacket` with:

```
TransmissionPacket {
    id:                UUID (assigned here, permanent)
    timestamp:         ISO8601 (call start time)
    talkgroup_id:      int (P25 TGID)
    source_unit:       int | null (source radio ID, if available)
    frequency:         float (Hz)
    duration:          float (seconds)
    encryption_status: bool
    audio_path:        string (path to WAV file)
}
```

**What gets stored:**
- WAV file on disk: `out/wav/{timestamp}_{tgid}_{src}_{uuid}.wav`
- Database record: all `TransmissionPacket` fields, `status = 'captured'`

See `phase_1a_capture_pipeline.md` and the Phase 1A session handoff doc for the full capture architecture, block signatures, and open questions.

---

### Stage 2 — Preprocessing (ASR)

**What happens:** The audio is transcribed into text using multi-pass ASR.

The `TransmissionPacket` audio is run through Whisper (and potentially alternative ASR models). The output is a `ProcessedTransmissionPacket` — the same record, now with text.

ASR may take significant time. A 10-second transmission might take several seconds to transcribe, especially with multi-pass. This is the pipeline bottleneck.

**Output:** A `ProcessedTransmissionPacket` with:

```
ProcessedTransmissionPacket extends TransmissionPacket {
    text:              string (transcribed content)
    asr_model:         string (which model produced this transcription)
    asr_confidence:    float | null (if available)
    asr_passes:        int (how many passes were run)
}
```

This is the radio-specific instantiation of the Albatross `ProcessedPacket`. The TRM sees it as:

```
ProcessedPacket {
    id:        UUID (same as capture)
    timestamp: ISO8601
    text:      "transcribed content"
    metadata:  { talkgroup_id, source_unit, frequency, ... }
}
```

**What gets stored:**
- Database record updated: text, ASR metadata fields, `status = 'processed'`

The original audio and capture metadata are untouched. The record grows.

---

### Stage 3 — TRM Routing

**What happens:** The processed packet enters the TRM queue and is routed.

The TRM pulls the `ProcessedTransmissionPacket` as a `ReadyPacket`. The existing runtime loop executes: full session context serialized to JSON, sent to the LLM, routing decision parsed, state updated. See `trm_runtime_loop.md` for the internal loop.

The TRM does not know this is a radio packet. It sees `id`, `timestamp`, `text`, and `metadata`. The metadata carries talkgroup_id, source_unit, etc. — but the TRM treats these as opaque routing signals weighted by configuration, not as radio-specific concepts.

**Output:** A `RoutingRecord` with:

```
RoutingRecord {
    packet_id:        UUID (same as capture)
    thread_decision:  new | existing | buffer | unknown
    thread_id:        string | null
    event_decision:   new | existing | none | unknown
    event_id:         string | null
}
```

Plus thread and event state updates.

**What gets stored:**
- Database record updated: thread_id, event_id, thread_decision, event_decision, `status = 'routed'`
- Thread table: thread created or updated (packet appended, label updated)
- Event table: event created or updated (thread linked)

---

### Stage 4 — Analysis

**What happens:** Downstream consumers read from the database.

This stage is everything after the TRM. It is fully domain-agnostic — it reads threads, events, and packets from the database. It does not know about radio, ASR, or talkgroups.

Consumers include:
- **Web UI** — live thread/event dashboard (the existing Next.js frontend, reading from the DB instead of in-memory state)
- **Reports** — incident summaries, shift reports, daily digests
- **Alerts** — pattern-based notifications (e.g. "new event on TGID X", "thread exceeded N packets")
- **Search** — full-text search across packet text, filtered by thread/event/talkgroup/time

None of these are built yet. The web UI exists but currently reads from the in-memory WebSocket stream. Migrating it to read from the database is a future step.

---

## Database Schema

The database is the persistent backbone of the pipeline. Every stage writes to it. Later stages read from it.

### Transmissions Table

One row per transmission. This is the core record that grows through the pipeline stages.

```
transmissions
├── id                  UUID        PRIMARY KEY (assigned at capture)
├── timestamp           TIMESTAMP   NOT NULL
├── status              ENUM        'captured' | 'processing' | 'processed' | 'routing' | 'routed' | 'error'
│
│   ── Capture fields (Stage 1) ──
├── talkgroup_id        INT         NOT NULL
├── source_unit         INT         NULL (not always available)
├── frequency           FLOAT       NOT NULL
├── duration            FLOAT       NOT NULL (seconds)
├── encryption_status   BOOL        NOT NULL
├── audio_path          TEXT        NOT NULL (path to WAV file)
│
│   ── Preprocessing fields (Stage 2) ──
├── text                TEXT        NULL (populated after ASR)
├── asr_model           TEXT        NULL
├── asr_confidence      FLOAT       NULL
├── asr_passes          INT         NULL
│
│   ── TRM fields (Stage 3) ──
├── thread_id           TEXT        NULL → FK threads.id
├── event_id            TEXT        NULL → FK events.id
├── thread_decision     ENUM        NULL ('new' | 'existing' | 'buffer' | 'unknown')
├── event_decision      ENUM        NULL ('new' | 'existing' | 'none' | 'unknown')
│
│   ── Metadata ──
├── created_at          TIMESTAMP   DEFAULT NOW()
└── updated_at          TIMESTAMP   DEFAULT NOW(), ON UPDATE
```

The `status` field tracks where the transmission is in the pipeline. This enables:
- ASR picking up `captured` records
- TRM picking up `processed` records
- Monitoring for stuck records (`processing` for too long = ASR failure)

### Threads Table

```
threads
├── id                  TEXT        PRIMARY KEY (e.g. 'thread_A', or UUID in production)
├── label               TEXT        NOT NULL (LLM-maintained summary)
├── status              TEXT        'open' | 'closed'
├── created_at          TIMESTAMP   DEFAULT NOW()
└── updated_at          TIMESTAMP   DEFAULT NOW(), ON UPDATE
```

Packet-to-thread assignment is in the `transmissions` table (`thread_id` FK). Thread-to-event links are in a join table.

### Events Table

```
events
├── id                  TEXT        PRIMARY KEY
├── label               TEXT        NOT NULL (LLM-maintained summary)
├── status              TEXT        'open' | 'closed'
├── opened_at           UUID        FK transmissions.id (packet that opened this event)
├── created_at          TIMESTAMP   DEFAULT NOW()
└── updated_at          TIMESTAMP   DEFAULT NOW(), ON UPDATE
```

### Thread-Event Join Table

Many-to-many relationship.

```
thread_events
├── thread_id           TEXT        FK threads.id
├── event_id            TEXT        FK events.id
└── PRIMARY KEY (thread_id, event_id)
```

### Routing Records Table

One row per routing decision. This is the audit log — every decision the TRM ever made.

```
routing_records
├── id                  SERIAL      PRIMARY KEY
├── packet_id           UUID        FK transmissions.id
├── thread_decision     ENUM        NOT NULL
├── thread_id           TEXT        NULL → FK threads.id
├── event_decision      ENUM        NOT NULL
├── event_id            TEXT        NULL → FK events.id
├── created_at          TIMESTAMP   DEFAULT NOW()
```

This is separate from the denormalized fields on `transmissions` because the transmission record shows the *current* state (which thread is this in?) while the routing record is the *historical* decision (what did the TRM decide at the time?). If thread correction is ever added, the transmission record changes but the routing record is immutable.

---

## Stage-to-Stage Handoff

### The Problem

The stages run at very different speeds:
- **Capture** is real-time — transmissions arrive as they happen
- **ASR** is the bottleneck — transcription takes real time, potentially longer than the audio
- **TRM** is fast per-packet but sequential — processes one packet at a time with an LLM call each

A simple ZMQ push chain would create backpressure. The TRM can't consume packets as fast as capture produces them if ASR is still working.

### The Likely Architecture

**Database as the persistent backbone. Lightweight signals between stages for "go process this" notifications.**

```
Capture
  ├── writes TransmissionPacket to DB (status = 'captured')
  └── signals ASR: "UUID X is ready"
              │
ASR           ▼
  ├── reads audio_path from DB
  ├── runs transcription
  ├── updates DB with text + ASR metadata (status = 'processed')
  └── signals TRM: "UUID X is ready for routing"
              │
TRM           ▼
  ├── reads ProcessedPacket from DB
  ├── routes it (LLM call)
  └── writes RoutingRecord + thread/event updates to DB (status = 'routed')
              │
Analysis      ▼
  └── reads from DB (threads, events, packets)
```

The signal mechanism between stages is an open design decision. Options:

| Mechanism | Pros | Cons |
|-----------|------|------|
| ZMQ push (UUID only) | Fast, already used in capture layer, no polling | One more thing to manage, needs restart handling |
| Database polling | Simple, no extra infra, inherently restartable | Latency from poll interval, DB load |
| Database LISTEN/NOTIFY (Postgres) | Real-time, no polling, DB-native | Postgres-specific, adds coupling |
| Message queue (Redis, RabbitMQ) | Robust, built for this | Another dependency to run |

For v1, ZMQ push with the UUID is the simplest path — the capture layer already uses ZMQ throughout. If the TRM or ASR crashes Restarts can pick up unprocessed records from the DB by status.

**This decision is deferred until Stage 2 (ASR) is being built.** The database schema and status field model work regardless of which signaling mechanism is chosen.

---

## How Scenario Tooling Connects

The existing scenario runner and WebUI bypass Stages 1 and 2 entirely. A scenario's `packets.json` is already preprocessed text — it enters at Stage 3 directly.

```
Scenario runner:
  packets.json → PacketLoader → PacketQueue → TRM → in-memory state → WebSocket → UI

Production:
  RF → Capture → DB → ASR → DB → TRM → DB → UI reads from DB
```

The TRM doesn't know or care which path produced the packet. In both cases it receives a `ReadyPacket` with `id`, `timestamp`, `text`, and `metadata`.

The scenario tooling will continue to work as-is for prompt development and regression testing. When the database is integrated, scenario runs could optionally write their results to the DB too — but that's not required. The in-memory path serves its purpose for development.

---

## What the TRM Needs to Change for Production

The current TRM (`src/pipeline/router.py`) is designed for bounded scenario runs. For production:

### Session continuity

The TRM currently holds all state in memory via `TRMContext`. A scenario run starts with empty state and ends when packets are exhausted. In production, the TRM runs continuously. Questions to resolve:

- **Context window growth.** Every packet is appended to its thread, and the full context is sent to the LLM each turn. Over hours of radio traffic, this grows without bound. A context management strategy is needed — probably windowing (only send the N most recent packets per thread) or summarization (condense older packets into a thread summary).
- **Thread/event lifecycle.** Threads and events need to close. The current model has no close logic — everything stays open. Production needs inactivity timeouts, explicit close signals, or LLM-driven close decisions.
- **Restart recovery.** If the TRM crashes, it needs to rebuild `TRMContext` from the database — load open threads and events, load recent packets per thread, and resume routing.

### Database writes

The current TRM updates in-memory state and emits `RoutingRecord` objects. For production it also needs to:
- Write the `RoutingRecord` to the `routing_records` table
- Update the `transmissions` record with `thread_id`, `event_id`, and `status = 'routed'`
- Create or update rows in `threads` and `events`
- Update the `thread_events` join table

This can be added as a persistence layer that wraps or extends the existing `_apply()` method. The in-memory state update logic doesn't need to change.

### The WebSocket bridge

The existing WebSocket broadcast (`api/services/runner.py`) pushes context snapshots to the frontend during scenario runs. In production, the frontend could:
- Read historical state from the database on page load
- Subscribe to a WebSocket for live updates as new packets are routed
- Both — DB for history, WebSocket for real-time

This is an evolution of the existing architecture, not a replacement.

---

## Open Questions

- **Database engine.** PostgreSQL is the likely choice for production (LISTEN/NOTIFY, JSONB for metadata, mature). SQLite could work for local dev. Decision deferred until implementation.
- **ASR architecture.** Multi-pass ASR is specified but not built. The number of passes, model selection, and confidence thresholds are all TBD. The database schema accommodates whatever ASR produces.
- **Context window management.** How to keep the TRM context from growing without bound in production. Windowing vs. summarization vs. hybrid. Needs experimentation once the TRM is running against real radio traffic.
- **Thread/event close policy.** When does a thread close? When does an event close? Inactivity timeout? LLM decision? Both? Needs design against real traffic patterns.
- **ORM vs. raw SQL.** SQLAlchemy, Tortoise ORM, or raw queries with asyncpg/aiosqlite. Decision deferred.
- **Audio storage.** Currently local filesystem. Production may need object storage (S3, MinIO) for durability and access. The `audio_path` field in the schema is a string that can point to either.

---

## Build Order

This is not phased like the WebUI plan — the stages are too interdependent for strict phase gates. But the natural order is:

1. **Database schema + ORM setup** — stand up the database, define the models, verify migrations work
2. **TRM persistence layer** — extend `_apply()` to write to the DB alongside in-memory state. Verify with scenario runs.
3. **ASR pipeline** — build the preprocessing stage. Reads audio from DB, transcribes, writes text back. Signals TRM.
4. **Capture → DB integration** — modify the capture backend to write `TransmissionPacket` records to the DB instead of (or in addition to) JSONL.
5. **Live TRM** — TRM reads from DB instead of scenario files. Continuous operation, context management, restart recovery.
6. **Frontend DB integration** — web UI reads from DB for historical state, WebSocket for live updates.

Steps 1–2 can happen now with the existing codebase. Steps 3–4 require being in a radio environment (home, not Ohio). Step 5 is the integration point. Step 6 is polish.