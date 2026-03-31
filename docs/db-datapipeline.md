# DB & Data Pipeline — Implementation Specs

*Detailed implementation specs for Albatross Phase 3. High-level plan lives in `docs/albatross_phase_3.md`.*

---

## Sub-phase 3.1 — Database Schema + ORM Setup ✓

### Stack

- **ORM:** SQLAlchemy 2.0 async (`sqlalchemy[asyncio]`)
- **Dev engine:** SQLite via `aiosqlite`
- **Prod engine:** PostgreSQL via `asyncpg`
- **Migrations:** Alembic
- **Config:** engine URL from environment variable `DATABASE_URL`, defaulting to `sqlite+aiosqlite:///./albatross.db` for local dev

### File Structure

```
db/
├── __init__.py
├── base.py          # DeclarativeBase, metadata
├── models.py        # All ORM models
├── session.py       # Engine setup, AsyncSession factory, get_session dependency
└── migrations/
    ├── env.py
    ├── script.py.mako
    └── versions/
```

### Models

All models use `mapped_column` and `Mapped` (SQLAlchemy 2.0 style). Timestamps use `func.now()` server defaults.

#### Transmission

```python
class Transmission(Base):
    __tablename__ = "transmissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # packet id, e.g. "pkt_001"
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    # 'captured' | 'processing' | 'processed' | 'routing' | 'routed' | 'error'

    # Capture fields
    talkgroup_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_unit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    encryption_status: Mapped[bool] = mapped_column(Boolean, nullable=False)
    audio_path: Mapped[str] = mapped_column(String, nullable=False)

    # Preprocessing fields
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asr_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    asr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asr_passes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # TRM fields
    thread_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("threads.id"), nullable=True)
    event_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("events.id"), nullable=True)
    thread_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### Thread

```python
class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "thread_A"
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    # 'open' | 'closed'

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### Event

```python
class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # e.g. "event_A"
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    # 'open' | 'closed'
    opened_at: Mapped[Optional[str]] = mapped_column(String, ForeignKey("transmissions.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```

#### ThreadEvent (join table)

```python
class ThreadEvent(Base):
    __tablename__ = "thread_events"

    thread_id: Mapped[str] = mapped_column(String, ForeignKey("threads.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(String, ForeignKey("events.id"), primary_key=True)
```

#### RoutingRecord

```python
class RoutingRecord(Base):
    __tablename__ = "routing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    packet_id: Mapped[str] = mapped_column(String, ForeignKey("transmissions.id"), nullable=False)
    thread_decision: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("threads.id"), nullable=True)
    event_decision: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("events.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

### Session Setup

```python
# db/session.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./albatross.db")

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

### Migrations

```bash
# Create initial migration
alembic revision --autogenerate -m "initial schema"

# Apply
alembic upgrade head
```

`albatross.db` is gitignored and gets recreated on `alembic upgrade head`. Any script that touches the database requires migrations to be applied first.

---

## Sub-phase 3.2 — Contracts Layer

### Purpose

A single source of truth for the Pydantic types that cross module boundaries. Every module imports boundary types from `contracts/`, not from each other.

### What Goes in Contracts vs What Stays in src/

This distinction matters. Not everything in `src/models/` is a boundary type.

**Moves to `contracts/`** — types that cross stage boundaries:
- `TransmissionPacket` — capture output, preprocessing input
- `ProcessedPacket` — preprocessing output, TRM input
- `ReadyPacket` — alias for `ProcessedPacket` once dequeued by TRM
- `RoutingRecord` — TRM output, DB/analysis input

**Stays in `src/models/`** — types that are TRM-internal only:
- `Thread` — in-memory context state, includes `packets: list[ReadyPacket]` and `event_ids`
- `Event` — in-memory context state
- `TRMContext` — the full session state sent to the LLM each turn
- `ThreadDecision` / `EventDecision` — enums used internally by the router

The rule: if a type is only ever used inside the TRM, it stays in `src/`. If it crosses a stage boundary, it lives in `contracts/`.

### File Structure

```
contracts/
├── __init__.py
└── models.py
```

### Models

```python
# contracts/models.py

from pydantic import BaseModel
from typing import Any, Optional

class TransmissionPacket(BaseModel):
    """Output of the capture stage. Input to preprocessing."""
    id: str
    timestamp: str
    talkgroup_id: int
    source_unit: Optional[int] = None
    frequency: float
    duration: float
    encryption_status: bool
    audio_path: str
    metadata: dict[str, Any] = {}

class ProcessedPacket(BaseModel):
    """Output of preprocessing. Input to the TRM. Domain-agnostic."""
    id: str
    timestamp: str
    text: str
    metadata: dict[str, Any] = {}

# ReadyPacket is a positional alias — a ProcessedPacket dequeued by the TRM
ReadyPacket = ProcessedPacket

class RoutingRecord(BaseModel):
    """Output of the TRM. One per packet."""
    packet_id: str
    thread_decision: str   # 'new' | 'existing' | 'buffer' | 'unknown'
    thread_id: Optional[str] = None
    event_decision: str    # 'new' | 'existing' | 'none' | 'unknown'
    event_id: Optional[str] = None
```

### Files That Need Import Updates

These files currently import packet or routing types from `src/models/` and need to be updated to import from `contracts/` instead:

- `src/pipeline/router.py` — imports `ReadyPacket`, `RoutingRecord`
- `api/services/runner.py` — imports `RoutingRecord`
- `tests/conftest.py` and test mocks — any mock that constructs `ReadyPacket` or `RoutingRecord` directly

Changes are mechanical — find/replace imports, verify tests still pass.

### Done When

- `contracts/models.py` exists and is importable
- `src/models/packets.py` reconciled — `ProcessedPacket` and `ReadyPacket` definitions match contracts
- No file imports boundary types from `src/models/` directly
- All 16 tests still pass

---

## Sub-phase 3.2b — Synthetic Live Data & Mock Pipeline

**Prerequisite:** `alembic upgrade head` must be run before starting any mock scripts. The database file is gitignored and will not exist in a fresh clone.

### Source Dataset

`data/tier_one/scenario_02_interleaved/packets_radio.json` ✓ — already created. 12 packets, two interleaved conversations, TGID 1001 (bob/dylan) and TGID 1002 (sam/jose).

### Simulation Parameters

| Parameter | Value |
|-----------|-------|
| Packet arrival interval | 10 seconds |
| Mock ASR delay | 10 seconds |
| Loop | No — run through dataset once and stop |

Total wall time: ~4 minutes from first capture to last routed packet.

### Pydantic ↔ ORM Mapping Convention

Both scripts map between Pydantic types (from `contracts/`) and ORM models (from `db/`). Establish this pattern now so 3.3 follows the same convention.

Use a `to_orm()` classmethod on each Pydantic model that returns the corresponding ORM instance:

```python
# In contracts/models.py
class TransmissionPacket(BaseModel):
    ...
    def to_orm(self) -> "db.models.Transmission":
        from db.models import Transmission
        return Transmission(
            id=self.id,
            timestamp=self.timestamp,
            talkgroup_id=self.talkgroup_id,
            source_unit=self.source_unit,
            frequency=self.frequency,
            duration=self.duration,
            encryption_status=self.encryption_status,
            audio_path=self.audio_path,
            status="captured",
            text=None,
        )
```

Same pattern applies to `RoutingRecord.to_orm()` in 3.3. Keeps mapping logic colocated with the type definition rather than scattered across scripts.

### Mock Capture Script

Location: `capture/mock/run.py`

**Behavior:**
1. Loads `packets_radio.json` into memory
2. For each packet in order:
   - Extracts capture fields — note that radio metadata fields (`talkgroup_id`, `source_unit`, `frequency`, `duration`, `encryption_status`, `audio_path`) are **nested under `metadata`** in the JSON and must be pulled out explicitly: `packet["metadata"]["talkgroup_id"]` etc.
   - Constructs a `TransmissionPacket` (Pydantic) from the extracted fields
   - Calls `transmission_packet.to_orm()` to get the ORM model
   - Writes to `transmissions` with `status = 'captured'`, `text = null`
   - Logs: `[CAPTURE] pkt_001 → captured (1/12)`
3. Waits 10 seconds
4. Moves to the next packet
5. Exits after the last packet

```bash
python capture/mock/run.py
```

**Logging format:**
```
[CAPTURE] 09:00:00 pkt_001 → captured (1/12)
[CAPTURE] 09:00:10 pkt_002 → captured (2/12)
...
[CAPTURE] done — 12 packets written
```

### Mock Preprocessing Script

Location: `preprocessing/mock/run.py`

**How it gets the text:** Capture writes rows with `text = null`. Preprocessing needs to fill it in, but it's only polling the DB — the text isn't there. On startup, preprocessing loads `packets_radio.json` and builds an `id → text` lookup dict. When it picks up a `captured` record, it looks up the text by packet id from that dict and writes it in.

```python
# On startup
with open("data/tier_one/scenario_02_interleaved/packets_radio.json") as f:
    packets = json.load(f)
text_lookup = {p["id"]: p["text"] for p in packets}
```

**Behavior:**
1. Loads `packets_radio.json` and builds `id → text` lookup
2. Polls `transmissions` for `status = 'captured'` rows every 2 seconds
3. Flips status to `'processing'` immediately on pickup (prevents double-pickup)
4. Logs: `[PREPROCESS] pkt_001 → processing...`
5. Waits 10 seconds (simulated ASR)
6. Looks up text from the dict, writes it to the `transmissions` row
7. Sets `asr_model = 'mock'`, `asr_confidence = 1.0`, `asr_passes = 1`
8. Flips status to `'processed'`
9. Logs: `[PREPROCESS] pkt_001 → processed (text: 26 chars)`
10. Continues polling until no `captured` or `processing` records remain, then exits

```bash
python preprocessing/mock/run.py
```

**Logging format:**
```
[PREPROCESS] 09:00:02 pkt_001 → processing...
[PREPROCESS] 09:00:12 pkt_001 → processed (text: 26 chars)
[PREPROCESS] 09:00:12 pkt_002 → processing...
...
[PREPROCESS] done — all packets processed
```

Both scripts run concurrently in separate terminals. Both import from `contracts/` for Pydantic types and from `db/` for ORM/session. Use Python `logging` module throughout — not bare `print`.

### DB Reset

Location: `db/reset.py`

Truncates all data tables in FK-safe order. Does not drop or recreate schema.

**Truncation order:**
1. `routing_records`
2. `thread_events`
3. `transmissions`
4. `threads`
5. `events`

```bash
python db/reset.py
```

---

## Sub-phase 3.3 — TRM Persistence Layer

### What Changes

The existing `TRMRouter._apply()` method updates in-memory state. A persistence layer wraps each call to also write to the database. The in-memory logic does not change.

A new DB-driven entry point is added alongside the existing scenario runner. Scenario tooling is completely unaffected.

### Enum → String Alignment

`_apply()` currently uses `ThreadDecision` and `EventDecision` enums for comparisons internally. The contracts `RoutingRecord` uses string literals (`'new'`, `'existing'`, etc.) — this was established in 3.2. The persistence layer works with the string-based `RoutingRecord` from contracts, so comparisons in `persist_routing_result()` use string literals throughout. No enum imports needed in the persistence layer.

### to_orm() Convention

`RoutingRecord` in `contracts/models.py` gets a `to_orm()` classmethod, same pattern as `TransmissionPacket.to_orm()` established in 3.2b. Lazy import, colocated with the type definition:

```python
class RoutingRecord(BaseModel):
    ...
    def to_orm(self, packet_id: str) -> "db.models.RoutingRecord":
        from db.models import RoutingRecord as ORMRoutingRecord
        return ORMRoutingRecord(
            packet_id=packet_id,
            thread_decision=self.thread_decision,
            thread_id=self.thread_id,
            event_decision=self.event_decision,
            event_id=self.event_id,
        )
```

### New Entry Point

`src/main_live.py` — polls for `processed` records from the DB, feeds them into `TRMRouter`, writes results back. Follows the same exit condition pattern as `preprocessing/mock/run.py` — idle cycle counter, exits when nothing remains.

```python
# Pseudocode
idle_cycles = 0
MAX_IDLE = 15  # exit after ~30 seconds of nothing — gives margin for slow pipeline start

while True:
    async with AsyncSessionLocal() as session:
        packet = await fetch_next_processed(session)

    if not packet:
        idle_cycles += 1
        if idle_cycles >= MAX_IDLE:
            logger.info("[TRM] no more packets — exiting")
            break
        await asyncio.sleep(2)
        continue

    idle_cycles = 0
    async with AsyncSessionLocal() as session:
        await update_status(session, packet.id, 'routing')

    ready_packet = ReadyPacket(
        id=packet.id,
        timestamp=str(packet.timestamp),
        text=packet.text,
        metadata={"talkgroup_id": packet.talkgroup_id, "source_unit": packet.source_unit, ...}
    )
    record = await router.route(ready_packet)

    async with AsyncSessionLocal() as session:
        await persist_routing_result(session, packet.id, record, router.context)

    logger.info(f"[TRM] {packet.id} → thread={record.thread_decision}:{record.thread_id} event={record.event_decision}:{record.event_id}")
```

### Persistence Function

`db/persist_routing_result()` — called after every successful `router.route()` call. Must be atomic per packet.

**Insertion order within the transaction matters** due to the circular FK between `events.opened_at` and `transmissions.id`:
- `transmissions` already exists (written by capture)
- `threads` and `events` must be upserted before `transmissions` can reference them via `thread_id` / `event_id`
- `events.opened_at` references `transmissions.id` which already exists — safe to set on upsert

The safe order within each transaction:

```python
async def persist_routing_result(session, packet_id, record, context):
    async with session.begin():
        # 1. Upsert thread — must exist before transmissions.thread_id references it
        if record.thread_decision in ('new', 'existing'):
            thread = get_thread_from_context(context, record.thread_id)
            await upsert_thread(session, thread)

        # 2. Upsert event — must exist before transmissions.event_id references it
        #    events.opened_at → transmissions.id is safe because the transmission already exists
        if record.event_decision in ('new', 'existing'):
            event = get_event_from_context(context, record.event_id)
            await upsert_event(session, event)

        # 3. Upsert thread_events join
        if record.thread_id and record.event_id:
            await upsert_thread_event(session, record.thread_id, record.event_id)

        # 4. Write routing record (uses record.to_orm())
        await session.merge(record.to_orm(packet_id))

        # 5. Update transmission — thread_id and event_id now have valid FK targets
        await update_transmission(session, packet_id, record)
```

**Critical:** Everything inside `session.begin()` is one transaction. If any write fails, nothing is committed and the packet status does not flip to `'routed'`. The next poll will pick it up and retry.

**Known limitation:** `router.route()` calls `_apply()` internally, which mutates in-memory state before `persist_routing_result()` runs. If the DB write fails, in-memory state has already been updated — they will drift. This doesn't affect the mock pipeline but is a real consistency gap for production. Fixing it requires splitting `_apply()` out of `route()` so it can be called after persistence succeeds. Deferred consciously — tracked as an open problem in `docs/trm_runtime_loop.md`.

### Done When

- Running `python src/main_live.py` with mock capture and preprocessing active routes all 12 packets
- All records in `transmissions` end with `status = 'routed'`
- `threads`, `events`, `thread_events`, and `routing_records` tables are populated correctly
- In-memory TRM state and DB state match after every packet
- Script exits cleanly after all packets are routed

---

## Sub-phase 3.4 — UI Hydration from Database

### New API Endpoints

`api/routes/live.py` — three GET endpoints registered at `/api` prefix:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/live/threads` | All open threads with their packets (joined from transmissions) |
| `GET` | `/api/live/events` | All open events with linked thread IDs |
| `GET` | `/api/live/transmissions` | All routed transmissions ordered by timestamp |

Response shapes mirror the existing TypeScript types in `web/src/types/trm.ts` so the frontend needs no type changes. Queries avoid N+1 — each endpoint runs 2–3 flat queries and assembles in Python.

All endpoints use `Depends(get_session)` from `db/session.py`.

### Frontend Changes

`web/src/hooks/useLiveData.ts` — new hook. Fetches all three endpoints on mount, reconstructs `TRMContext` from responses, polls every 3 seconds for updates. Returns the same state shape as `useRunSocket` (`status`, `context`, `routingRecords`, `latestPacketId`, `error`).

Live updates use client-side polling rather than WebSocket. The TRM (`main_live.py`) and API (`uvicorn`) run as separate processes with no IPC — the database is their only shared state. Polling at 3s satisfies the "within a few seconds" requirement. The REST endpoints built here become the hydration layer if a WebSocket push is added later.

`web/src/app/live/page.tsx` — new page. Mirrors the run dashboard (`run/[runId]/page.tsx`) with these differences:
- Uses `useLiveData()` instead of `useRunSocket(runId)`
- No `IncomingBanner` or `BufferZone` — buffer state is transient TRM state, not persisted to DB
- TopBar shows "Live Pipeline" with no speed factor
- Same ThreadLane, EventCard, TimelineRow, TabBar, ContextInspector components

`web/src/components/TopBar.tsx` — `speedFactor` prop made optional; hidden when null.

### Done When

- `/live` page renders current DB state on load
- Page refresh shows the same state — nothing lost
- A second browser tab opened mid-run shows the same state as the first
- New packets routed by the TRM appear in the UI within a few seconds via polling

**Done.** Three API endpoints in `api/routes/live.py`, `useLiveData` hook with 3s polling, `/live` page reusing all existing dashboard components. 7 new tests cover the endpoints (empty state, filtering, ordering, response shapes). 43 tests total.

---

## Running a Full Simulation

`main_live.py` requires `ANTHROPIC_API_KEY` set in `.env`. The mock capture and preprocessing scripts do not need it.

```bash
# 1. Apply migrations (required before first run and after fresh clone)
alembic upgrade head

# 2. Reset the database (between runs)
python db/reset.py

# 3. Start mock preprocessing in background
python preprocessing/mock/run.py &

# 4. Start mock capture in background
python capture/mock/run.py &

# 5. Start TRM live runner
python src/main_live.py

# 6. Start API
uvicorn api.main:app --reload

# 7. Open the web UI
# http://localhost:3000/live
```

Packets appear in the UI every ~20 seconds (10s capture + 10s ASR delay). Refresh at any point — state is fully restored from the DB.