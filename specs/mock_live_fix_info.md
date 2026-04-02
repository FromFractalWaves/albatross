# Mock Live Pipeline — End-to-End Reference

How the mock pipeline, API, and live UI work together.

---

## 1. Overview

The mock live pipeline simulates a full radio dispatch data flow: **Capture → Preprocessing → TRM Routing → DB → Live UI**. Three Python scripts run as subprocesses, each writing to a shared SQLite database. The frontend polls REST endpoints to hydrate state from that database.

```
packets_radio.json
        │
        ▼
┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
│ capture/     │     │ preprocessing/   │     │ trm/         │
│ mock/run.py  │────▶│ mock/run.py      │────▶│ main_live.py │
│              │     │                  │     │              │
│ status:      │     │ status:          │     │ status:      │
│  "captured"  │     │  "processing"    │     │  "routing"   │
│              │     │  "processed"     │     │  "routed"    │
└──────────────┘     └──────────────────┘     └──────────────┘
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │ SQLite DB    │
                                              │ (5 tables)   │
                                              └──────┬───────┘
                                                     │
                                    ┌────────────────┼────────────────┐
                                    ▼                ▼                ▼
                             GET /threads     GET /events     GET /transmissions
                                    │                │                │
                                    └────────────────┼────────────────┘
                                                     ▼
                                              ┌──────────────┐
                                              │ Live Page    │
                                              │ (3s polling) │
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
| `captured` | `capture/mock/run.py` | Row inserted, `text` is null |
| `processing` | `preprocessing/mock/run.py` | Preprocessing claimed it, prevents double-pickup |
| `processed` | `preprocessing/mock/run.py` | ASR done, `text` + ASR metadata written |
| `routing` | `trm/main_live.py` | TRM claimed it, prevents double-pickup |
| `routed` | `db/persist.py` (called by TRM) | Routing complete, thread/event/record persisted |

---

## 3. Stage 1 — Capture (`capture/mock/run.py`)

**Source data**: `data/tier_one/scenario_02_interleaved/packets_radio.json`

**What it does**:
1. Loads all packets from JSON at startup.
2. For each packet, builds a `TransmissionPacket` (contracts model) from the JSON fields: `id`, `timestamp`, plus metadata fields (`talkgroup_id`, `source_unit`, `frequency`, `duration`, `encryption_status`, `audio_path`).
3. Calls `tp.to_orm()` which returns a `Transmission` ORM object with `status="captured"` and `text=None`.
4. Writes the ORM object to the DB.
5. Sleeps **10 seconds** before the next packet (except after the last one).

**Timing**: ~10s per packet. For 20 packets, capture takes ~190s.

**Key detail**: `to_orm()` parses the ISO8601 timestamp string into a `datetime` via `fromisoformat()`, replacing `Z` with `+00:00`.

---

## 4. Stage 2 — Preprocessing (`preprocessing/mock/run.py`)

**What it does**:
1. At startup, builds a `text_lookup` dict mapping `packet_id → text` from the same JSON file.
2. Polls every **2 seconds** for one row with `status="captured"` (LIMIT 1).
3. If found:
   - Immediately sets `status="processing"` and commits (prevents double-pickup).
   - Sleeps **10 seconds** (simulated ASR).
   - Re-fetches the row by `packet_id`.
   - Writes: `text` (from lookup), `asr_model="mock"`, `asr_confidence=1.0`, `asr_passes=1`.
   - Sets `status="processed"`.
4. If no `captured` rows found:
   - Checks for any `processing` rows (in-flight work). If found, resets idle counter and continues.
   - If no in-flight work either, increments idle counter.
   - After **3 consecutive idle cycles**, exits.

**Timing**: 2s poll + 10s ASR delay per packet. Runs concurrently with capture.

---

## 5. Stage 3 — TRM Routing (`trm/main_live.py`)

**What it does**:
1. Creates a `TRMRouter(buffers=5)`.
2. Polls every **2 seconds** for one row with `status="processed"` (ordered by timestamp, LIMIT 1).
3. If found:
   - Sets `status="routing"` and commits (prevents double-pickup).
   - Builds a `ReadyPacket` from the transmission fields: `id`, `timestamp` (as string), `text`, `metadata` dict with `talkgroup_id`, `source_unit`, `frequency`, `duration`.
   - Calls `await router.route(ready_packet)` — sends full TRMContext to Claude, gets back a `RoutingRecord`.
   - Calls `await persist_routing_result(session, packet_id, record, router.context)`.
4. If no `processed` rows, increments idle counter. After **10 consecutive idle cycles** (~20s), exits.

**Routing**: The `route()` call sends the entire `TRMContext` (all active threads, events, buffer, and the incoming packet) as JSON to Claude Sonnet. The response is parsed into a `RoutingRecord` with `thread_decision`, `thread_id`, `event_decision`, `event_id`.

---

## 6. Atomic Persistence (`db/persist.py`)

`persist_routing_result(session, packet_id, record, context)` writes everything in one transaction, in FK-safe order:

1. **Upsert Thread** — if decision is `new` or `existing` and `thread_id` is set. Looks up thread from `context.active_threads`, creates `ORMThread(id, label, status)`, uses `session.merge()` for upsert.
2. **Upsert Event** — same pattern from `context.active_events`, with `opened_at` field.
3. **Upsert ThreadEvent join** — if both `thread_id` and `event_id` exist, inserts join row if not already present.
4. **Write RoutingRecord** — `session.add(record.to_orm())`, auto-increment PK.
5. **Update Transmission** — sets `thread_id`, `event_id`, `thread_decision`, `event_decision`, and `status="routed"`.

All within `async with session.begin()`.

---

## 7. Database Schema

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

## 8. API Layer

### Mock Pipeline Control (`api/routes/mock.py`)

Registered at `/api/mock`.

| Endpoint | Behavior |
|----------|----------|
| `POST /api/mock/start` | Stops existing processes, calls `reset_db()` (truncates all tables), launches 3 subprocesses (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) via `asyncio.create_subprocess_exec()`. Stores handles in `app.state.mock_processes`. Returns `{"status": "started"}`. |
| `POST /api/mock/stop` | Terminates all processes (5s grace, then kill). Clears process list. Returns `{"status": "stopped"}`. |
| `GET /api/mock/status` | Returns `{"status": "running"}` if any process has `returncode is None`, else `{"status": "stopped"}`. |

### Live Data Endpoints (`api/routes/live.py`)

Registered at `/api/live`.

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

**`GET /api/live/events`** — All events with `status="open"`. Includes linked thread IDs. Response shape per event:
```json
{
  "event_id": "evt_001",
  "label": "Traffic stop on Main St",
  "opened_at": "pkt_003",
  "thread_ids": ["thr_001", "thr_002"],
  "status": "open"
}
```

**`GET /api/live/transmissions`** — All transmissions with `status="routed"`, ordered by timestamp. Includes decision fields and metadata. Response shape per transmission:
```json
{
  "id": "pkt_001",
  "timestamp": "2024-01-15T09:00:00+00:00",
  "text": "Dylan! How's it going man?",
  "status": "routed",
  "thread_id": "thr_001",
  "event_id": null,
  "thread_decision": "new",
  "event_decision": "none",
  "metadata": {
    "talkgroup_id": 1001,
    "source_unit": 4021,
    "frequency": 851.0125,
    "duration": 2.1,
    "encryption_status": false
  }
}
```

---

## 9. Frontend — Live Page

### Page (`web/src/app/live/[source]/page.tsx`)

Dynamic route where `source` is e.g. `"mock"`. Three tabs: **LIVE**, **EVENTS**, **TIMELINE**.

**Mock pipeline controls** (shown only when `source === "mock"`):
- Polls `GET /api/mock/status` every 3000ms.
- Start button → `POST /api/mock/start` (resets DB + launches scripts).
- Stop button → `POST /api/mock/stop`.
- Green pulsing dot when running.

**Tab content**:
- **LIVE**: `ThreadLane` per active thread. Each lane shows thread label, colored header, and `PacketCard` children with decision badges.
- **EVENTS**: `EventCard` per active event. Shows event label, `opened_at` timestamp, linked thread badges (colored).
- **TIMELINE**: All packets from all threads, flattened and sorted by packet ID. `TimelineRow` per packet.

**Computed state**:
- `threadColorMap`: Maps `thread_id` → hex color (6-color rotating palette from `threadColors.ts`).
- `decisionMap`: Maps `packet_id` → `{thread_decision, event_decision, thread_id, event_id}` (from `packetDecisions.ts`).
- Latest packet highlighted with colored left border.

### Hook (`web/src/hooks/useLiveData.ts`)

**Polling interval**: 3000ms.

**Per poll cycle**:
1. Fetches all 3 endpoints in parallel via `Promise.all()`.
2. Reconstructs `TRMContext`:
   ```typescript
   {
     active_threads: threads,       // from /api/live/threads
     active_events: events,         // from /api/live/events
     packets_to_resolve: [],        // always empty (no buffer visibility)
     buffers_remaining: 5,          // hardcoded
   }
   ```
3. Builds `RoutingRecord[]` from transmissions that have `thread_decision` set.
4. Sets `latestPacketId` from last transmission.

**Status values**: `"loading"` → `"empty"` (no data) or `"ready"` (has data). `"error"` on fetch failure (retries next poll).

**Note**: Network errors don't crash — they're silently ignored, and the next poll retries. Uses `activeRef` to prevent state updates after unmount.

---

## 10. Timing Summary

| Component | Interval | Exit Condition |
|-----------|----------|----------------|
| Capture script | 10s between packets | All packets emitted |
| Preprocessing poll | 2s | 3 consecutive idle cycles |
| Preprocessing ASR delay | 10s per packet | — |
| TRM poll | 2s | 10 consecutive idle cycles (~20s) |
| Frontend live data poll | 3s | Page unmount |
| Frontend mock status poll | 3s | Page unmount |

**End-to-end latency per packet**: ~10s capture gap + ~10s ASR + TRM routing time (LLM call, ~2-5s). Frontend sees it on next poll (up to 3s). Total: ~25s from capture to UI visibility.

**Full dataset runtime**: ~4 minutes for 20 packets (dominated by capture interval + ASR delay).

---

## 11. Source Data

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

## 12. Test Coverage

49 tests total, all passing. Key test files for this pipeline:

| File | Tests | Covers |
|------|-------|--------|
| `tests/test_mock_pipeline.py` | 3 | Capture→DB, preprocessing status transitions, DB reset |
| `tests/test_trm_persistence.py` | 5 | `persist_routing_result()` atomic writes, FK ordering, partial decisions |
| `tests/test_live_api.py` | 7 | All 3 live endpoints — filtering by status, response shapes, ordering |
| `tests/test_mock_api.py` | 6 | Mock start/stop/status, process management, restart behavior |
| `tests/test_db.py` | 7 | ORM model CRUD, table creation, FK relationships |
| `tests/test_contracts.py` | 5 | Boundary types, `to_orm()` methods, type aliases |
