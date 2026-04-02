# Mock Pipeline — End-to-End Reference

*How the mock pipeline, API, and live UI work together.*

---

## 1. Overview

The mock live pipeline simulates a full radio dispatch data flow: **Capture → Preprocessing → TRM Routing → DB + WebSocket → Live UI**. The pipeline runs in-process inside the API as three concurrent async stages connected by `PacketQueue`s. The frontend receives real-time updates via WebSocket and hydrates from the database on page load.

```
packets_radio.json
        │
        ▼
┌──────────────────────────────────────────────────────┐
│ LivePipelineManager (api/services/live_pipeline.py)  │
│                                                      │
│  Capture Stage ──▶ Preprocessing ──▶ Routing Stage   │
│  (PacketQueue)     (PacketQueue)     (TRMRouter)     │
│                                                      │
│  DB writes at each stage:                            │
│  "captured" → "processing" → "processed" → "routed"  │
│                                                      │
│  WebSocket broadcast at each stage:                  │
│  packet_captured → packet_preprocessed →             │
│  packet_routed                                       │
└──────────────────────────────────────────────────────┘
        │                                  │
        ▼                                  ▼
┌──────────────┐                  ┌────────────────┐
│ SQLite DB    │                  │ ws://localhost  │
│ (5 tables)   │                  │ :8000/ws/live/  │
│              │                  │ mock            │
└──────┬───────┘                  └───────┬────────┘
       │                                  │
       ▼                                  ▼
 REST hydration                   Real-time push
 (page load/refresh)              (TanStack Query
                                   cache updates)
       │                                  │
       └──────────────┬───────────────────┘
                      ▼
               ┌──────────────┐
               │ Live Page    │
               │ (WebSocket)  │
               └──────────────┘
```

---

## 2. Transmission Status Progression

A single transmission row moves through these statuses:

```
captured → processing → processed → routing → routed
```

| Status | Set by | Meaning |
|--------|--------|---------|
| `captured` | Capture stage | Row inserted, `text` is null |
| `processing` | Preprocessing stage | Preprocessing claimed it |
| `processed` | Preprocessing stage | ASR done, `text` + ASR metadata written |
| `routing` | Routing stage | TRM claimed it |
| `routed` | `db/persist.py` (called by routing stage) | Routing complete, thread/event/record persisted |

---

## 3. Pipeline Manager (`api/services/live_pipeline.py`)

`LivePipelineManager` orchestrates the pipeline as a single asyncio task with three concurrent stages. It is a singleton stored on `app.state.live_pipeline_manager`.

**Lifecycle**:
1. `POST /api/mock/start` → `manager.start(session_factory)` → resets DB, spawns pipeline task
2. Pipeline runs three stages via `asyncio.gather()`, broadcasting WebSocket messages at each step
3. `POST /api/mock/stop` → `manager.stop()` → cancels the task

**WebSocket messages** (broadcast in order):

| Message Type | When | Payload |
|-------------|------|---------|
| `pipeline_started` | Pipeline begins | `total_packets` |
| `packet_captured` | Packet written to DB | `packet_id`, `timestamp`, `metadata` |
| `packet_preprocessed` | ASR complete | `packet_id`, `text` |
| `packet_routed` | TRM routing complete | `packet_id`, `routing_record`, `context`, `incoming_packet` |
| `pipeline_complete` | All packets done | `total_packets`, `routing_records` |
| `pipeline_error` | Error occurred | `error` |

Late-joining WebSocket clients receive the full message backlog on connect.

---

## 4. Stage 1 — Capture

**Source data**: `data/tier_one/scenario_02_interleaved/packets_radio.json`

**What it does**:
1. Loads all packets from JSON at startup.
2. For each packet, builds a `TransmissionPacket` (contracts model) from the JSON fields: `id`, `timestamp`, plus metadata fields (`talkgroup_id`, `source_unit`, `frequency`, `duration`, `encryption_status`, `audio_path`).
3. Calls `tp.to_orm()` which returns a `Transmission` ORM object with `status="captured"` and `text=None`.
4. Writes the ORM object to the DB.
5. Broadcasts `packet_captured` message.
6. Puts packet data on the capture queue for the preprocessing stage.
7. Sleeps **10 seconds** before the next packet (except after the last one).
8. Sends `None` sentinel on the queue when done.

---

## 5. Stage 2 — Preprocessing

**What it does**:
1. At startup, a `text_lookup` dict mapping `packet_id → text` is built from the same JSON file.
2. Consumes packets from the capture queue (no polling — direct queue consumption).
3. For each packet:
   - Sets `status="processing"` in DB.
   - Sleeps **3 seconds** (simulated ASR).
   - Writes: `text` (from lookup), `asr_model="mock"`, `asr_confidence=1.0`, `asr_passes=1`.
   - Sets `status="processed"`.
   - Broadcasts `packet_preprocessed` message.
   - Builds a `ReadyPacket` and puts it on the routing queue.
4. Forwards `None` sentinel when capture is done.

---

## 6. Stage 3 — TRM Routing

**What it does**:
1. Creates a `TRMRouter(buffers=5)`.
2. Consumes `ReadyPacket`s from the routing queue.
3. For each packet:
   - Sets `status="routing"` in DB.
   - Calls `await router.route(ready_packet)` — sends full TRMContext to Claude, gets back a `RoutingRecord`.
   - Calls `await persist_routing_result(session, packet_id, record, router.context)`.
   - Broadcasts `packet_routed` message with routing record and full context snapshot.
4. After all packets: pipeline broadcasts `pipeline_complete`.

---

## 7. Atomic Persistence (`db/persist.py`)

`persist_routing_result(session, packet_id, record, context)` writes everything in one transaction, in FK-safe order:

1. **Upsert Thread** — if decision is `new` or `existing` and `thread_id` is set. Looks up thread from `context.active_threads`, creates `ORMThread(id, label, status)`, uses `session.merge()` for upsert.
2. **Upsert Event** — same pattern from `context.active_events`, with `opened_at` field.
3. **Upsert ThreadEvent join** — if both `thread_id` and `event_id` exist, inserts join row if not already present.
4. **Write RoutingRecord** — `session.add(record.to_orm())`, auto-increment PK.
5. **Update Transmission** — sets `thread_id`, `event_id`, `thread_decision`, `event_decision`, and `status="routed"`.

All within `async with session.begin()`.

---

## 8. Database Schema

**5 tables** managed by SQLAlchemy 2.0 async ORM (`db/models.py`), migrated via Alembic.

| Table | PK | Key Columns |
|-------|----|-------------|
| `transmissions` | `id` (str) | `timestamp`, `status`, `talkgroup_id`, `source_unit`, `frequency`, `duration`, `encryption_status`, `audio_path`, `text`, `asr_*`, `thread_id` (FK), `event_id` (FK), `thread_decision`, `event_decision` |
| `threads` | `id` (str) | `label`, `status` (default "open") |
| `events` | `id` (str) | `label`, `status` (default "open"), `opened_at` (FK→transmissions.id) |
| `thread_events` | `(thread_id, event_id)` | Many-to-many join |
| `routing_records` | `id` (int, auto) | `packet_id` (FK), `thread_decision`, `thread_id` (FK), `event_decision`, `event_id` (FK) |

Engine: `sqlite+aiosqlite:///./albatross.db` (default). Session: `AsyncSessionLocal` from `db/session.py`. Dependency: `get_session()` yields sessions for FastAPI.

---

## 9. API Layer

### Mock Pipeline Control (`api/routes/mock.py`)

| Endpoint | Behavior |
|----------|----------|
| `POST /api/mock/start` | Calls `manager.start(AsyncSessionLocal)` — stops any existing pipeline, resets DB, starts new in-process pipeline task. Returns `{"status": "started"}`. |
| `POST /api/mock/stop` | Calls `manager.stop()` — cancels the pipeline task. Returns `{"status": "stopped"}`. |
| `GET /api/mock/status` | Returns `{"status": "running"}` if pipeline task is active, else `{"status": "stopped"}`. |
| `ws://localhost:8000/ws/live/mock` | WebSocket endpoint. Accepts connection, sends backlog, then streams live pipeline messages. |

### Live Data Endpoints (`api/routes/live.py`)

Registered at `/api/live`. These serve as the **hydration layer** — the frontend fetches them on page load or refresh, then WebSocket messages keep the state current.

**`GET /api/live/threads`** — All threads with `status="open"`. For each thread, fetches routed transmissions (joined by `thread_id`, ordered by timestamp) and event IDs (via `thread_events` join). Response shape per thread:
```json
{
  "thread_id": "thr_001",
  "label": "Bob and Dylan catching up",
  "packets": [
    {"id": "pkt_001", "timestamp": "2024-01-15T09:00:00Z", "text": "...", "metadata": {...}}
  ],
  "event_ids": ["evt_001"],
  "status": "open"
}
```

**`GET /api/live/events`** — All events with `status="open"`. Includes linked thread IDs.

**`GET /api/live/transmissions`** — All transmissions with `status="routed"`, ordered by timestamp. Includes decision fields and metadata.

---

## 10. Frontend — Live Page

### Page (`web/src/app/live/[source]/page.tsx`)

Dynamic route where `source` is e.g. `"mock"`. Three tabs: **LIVE**, **EVENTS**, **TIMELINE**.

**Mock pipeline controls** (shown only when `source === "mock"`):
- Polls `GET /api/mock/status` every 3000ms for status indicator.
- Start button → `POST /api/mock/start` (resets DB + starts pipeline).
- Stop button → `POST /api/mock/stop`.
- Green pulsing dot when running.

**Tab content**:
- **LIVE**: `ThreadLane` per active thread. Each lane shows thread label, colored header, and `PacketCard` children with decision badges.
- **EVENTS**: `EventCard` per active event. Shows event label, `opened_at` timestamp, linked thread badges (colored).
- **TIMELINE**: All packets from all threads, flattened and sorted by packet ID. `TimelineRow` per packet.

### Hook (`web/src/hooks/useLiveData.ts`)

Uses **TanStack Query** for data management and **WebSocket** for real-time push.

**Hydration** (on mount / page refresh):
- `useQuery` fetches `/api/live/threads`, `/events`, `/transmissions`.
- When WebSocket is connected, polling is disabled. Otherwise, fallback poll every 5s.

**WebSocket push** (real-time updates):
- Connects to `ws://localhost:8000/ws/live/mock`.
- On `packet_routed`: updates TanStack Query caches with context and routing record from the message.
- On `pipeline_complete`: invalidates all queries to re-fetch final state from DB.
- Auto-reconnects on disconnect with 2s backoff.

**Return shape**:
```typescript
{ status, context, routingRecords, latestPacketId, incomingPacket, error }
```

---

## 11. Timing Summary

| Component | Interval | Exit Condition |
|-----------|----------|----------------|
| Capture stage | 10s between packets | All packets emitted |
| Preprocessing ASR delay | 3s per packet | — |
| Routing | Immediate (queue-driven) | All packets routed |
| Frontend WebSocket | Real-time push | Page unmount |
| Frontend mock status poll | 3s | Page unmount |

**End-to-end latency per packet**: ~10s capture gap + ~3s ASR + TRM routing time (LLM call, ~2-5s). Frontend sees it immediately via WebSocket push. Total: ~15-18s from capture to UI visibility.

**Full dataset runtime**: ~2 minutes for 12 packets (dominated by capture interval + LLM routing time).

---

## 12. Source Data

**File**: `data/tier_one/scenario_02_interleaved/packets_radio.json`

Each entry:
```json
{
  "id": "pkt_001",
  "timestamp": "2024-01-15T09:00:00Z",
  "text": "Dylan! How's it going man?",
  "metadata": {
    "speaker": "bob",
    "talkgroup_id": 1001,
    "source_unit": 4021,
    "frequency": 851.0125,
    "duration": 2.1,
    "encryption_status": false,
    "audio_path": "out/wav/mock_pkt_001.wav"
  }
}
```

The `text` field is used by preprocessing (looked up by packet ID). The `speaker` field in metadata is not stored in the DB — it's only used by the TRM via the `ReadyPacket.metadata` dict.

---

## 13. Standalone Scripts

The original subprocess scripts still exist for manual/standalone usage outside the API:

- `capture/mock/run.py` — Writes packets to DB on 10s intervals.
- `preprocessing/mock/run.py` — Polls DB for captured rows, simulates ASR.
- `trm/main_live.py` — Polls DB for processed rows, routes + persists.

These are **not** called by the API — the in-process pipeline replaces them for the live UI workflow.

---

## 14. Test Coverage

55 tests total, all passing. Key test files for this pipeline:

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_live_pipeline.py` | 6 | Pipeline manager lifecycle, message collection/ordering, WebSocket backlog, multi-client |
| `tests/test_mock_api.py` | 6 | Mock start/stop/status via LivePipelineManager |
| `tests/test_mock_pipeline.py` | 3 | Capture→DB, preprocessing status transitions, DB reset |
| `tests/test_trm_persistence.py` | 5 | `persist_routing_result()` atomic writes, FK ordering, partial decisions |
| `tests/test_live_api.py` | 7 | All 3 live endpoints — filtering by status, response shapes, ordering |
| `tests/test_db.py` | 7 | ORM model CRUD, table creation, FK relationships |
| `tests/test_contracts.py` | 5 | Boundary types, `to_orm()` methods, type aliases |
