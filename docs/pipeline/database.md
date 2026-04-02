# Database & Data Pipeline

*Schema, contracts layer, mock pipeline, and persistence — the persistent backbone of the Albatross pipeline.*

---

## Overview

Every pipeline stage (Capture, Preprocessing, TRM) reads from and writes to a shared database. The UI hydrates from the same database on load. A transmission's UUID is assigned at capture and never changes — every stage enriches the same record.

```
capture/mock ──> DB ──> preprocessing/mock ──> DB ──> TRM ──> DB ──> UI
```

### Stack

- **ORM:** SQLAlchemy 2.0 async (`sqlalchemy[asyncio]`)
- **Dev engine:** SQLite via `aiosqlite`
- **Prod engine:** PostgreSQL via `asyncpg`
- **Migrations:** Alembic
- **Config:** `DATABASE_URL` env var, defaults to `sqlite+aiosqlite:///./albatross.db`

### File Structure

```
db/
├── __init__.py
├── base.py          # DeclarativeBase, metadata
├── models.py        # All ORM models
├── session.py       # Engine setup, AsyncSession factory, get_session dependency
├── persist.py       # persist_routing_result() — atomic per-packet TRM writes
├── reset.py         # Truncates all data tables in FK-safe order
└── migrations/
    ├── env.py
    ├── script.py.mako
    └── versions/
```

---

## ORM Models

All models use `mapped_column` and `Mapped` (SQLAlchemy 2.0 style). Timestamps use `func.now()` server defaults.

### Transmission

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

### Thread

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

### Event

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

### ThreadEvent (join table)

```python
class ThreadEvent(Base):
    __tablename__ = "thread_events"

    thread_id: Mapped[str] = mapped_column(String, ForeignKey("threads.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(String, ForeignKey("events.id"), primary_key=True)
```

### RoutingRecord

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
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./albatross.db")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
```

`albatross.db` is gitignored and gets recreated on `alembic upgrade head`.

---

## Contracts Layer

The `contracts/` package is the single source of truth for Pydantic types that cross module boundaries. Every module imports boundary types from `contracts/`, not from each other.

### What Goes Where

**In `contracts/models.py`** — types that cross stage boundaries:
- `TransmissionPacket` — capture output, preprocessing input
- `ProcessedPacket` — preprocessing output, TRM input (domain-agnostic)
- `ReadyPacket` — alias for `ProcessedPacket` once dequeued by TRM
- `RoutingRecord` — TRM output, DB/analysis input

**Stays in `trm/models/`** — types that are TRM-internal:
- `Thread`, `Event` — in-memory context state
- `TRMContext` — the full session state sent to the LLM each turn
- `ThreadDecision` / `EventDecision` — enums used internally by the router

The rule: if a type is only ever used inside the TRM, it stays in `trm/`. If it crosses a stage boundary, it lives in `contracts/`.

### Pydantic-to-ORM Mapping

Both `TransmissionPacket` and `RoutingRecord` have a `to_orm()` method that returns the corresponding ORM instance. Mapping logic is colocated with the type definition:

```python
class TransmissionPacket(BaseModel):
    ...
    def to_orm(self) -> "db.models.Transmission":
        from db.models import Transmission
        return Transmission(
            id=self.id, timestamp=self.timestamp,
            talkgroup_id=self.talkgroup_id, ...
            status="captured", text=None,
        )
```

---

## Mock Pipeline

Simulates the full Capture -> Preprocessing flow using `packets_radio.json` as source data. Both scripts run concurrently in separate terminals.

### Mock Capture (`capture/mock/run.py`)

1. Loads `data/tier_one/scenario_02_interleaved/packets_radio.json`
2. For each packet: constructs `TransmissionPacket`, calls `to_orm()`, writes to DB with `status = 'captured'` and `text = null`
3. Waits 10 seconds between packets
4. Exits after the last packet

### Mock Preprocessing (`preprocessing/mock/run.py`)

1. Loads `packets_radio.json` and builds an `id -> text` lookup dict
2. Polls for `status = 'captured'` rows every 2 seconds
3. Flips status to `'processing'` immediately (prevents double-pickup)
4. Waits 10 seconds (simulated ASR)
5. Writes text from lookup, sets `asr_model = 'mock'`, `asr_confidence = 1.0`, `asr_passes = 1`
6. Flips status to `'processed'`
7. Exits when no `captured` or `processing` records remain

### Simulation Parameters

| Parameter | Value |
|-----------|-------|
| Packet arrival interval | 10 seconds |
| Mock ASR delay | 10 seconds |
| Loop | No — run through dataset once and stop |

Total wall time: ~4 minutes from first capture to last routed packet.

### DB Reset (`db/reset.py`)

Truncates all data tables in FK-safe order: `routing_records` -> `thread_events` -> `transmissions` -> `threads` -> `events`.

---

## TRM Persistence

### Entry Point

`trm/main_live.py` — polls for `processed` records from the DB, feeds them into `TRMRouter`, writes results back. Exits after ~30 seconds of idle (no more packets to process).

### Persistence Function

`db/persist.py` provides `persist_routing_result()` — called after every successful `router.route()` call. Atomic per packet.

Insertion order within the transaction matters due to FK dependencies:

```python
async def persist_routing_result(session, packet_id, record, context):
    async with session.begin():
        # 1. Upsert thread (must exist before transmissions.thread_id references it)
        # 2. Upsert event (events.opened_at -> transmissions.id is safe — transmission already exists)
        # 3. Upsert thread_events join
        # 4. Write routing record (uses record.to_orm())
        # 5. Update transmission — thread_id and event_id now have valid FK targets
```

Everything inside `session.begin()` is one transaction. If any write fails, nothing is committed and the next poll retries.

### Known Limitation

`router.route()` calls `_apply()` internally, which mutates in-memory state before `persist_routing_result()` runs. If the DB write fails, in-memory state has already been updated — they will drift. Fixing this requires splitting `_apply()` out of `route()`. Deferred — tracked as an open problem in `docs/trm/runtime_loop.md`.

---

## Live API & UI Hydration

Three GET endpoints in `api/routes/live.py`, all using `Depends(get_session)`:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/live/threads` | Open threads with their packets (joined from transmissions) |
| `GET` | `/api/live/events` | Open events with linked thread IDs |
| `GET` | `/api/live/transmissions` | Routed transmissions ordered by timestamp |

Response shapes mirror the TypeScript types in `web/src/types/trm.ts`. Queries avoid N+1 — each endpoint runs 2-3 flat queries and assembles in Python.

The `/live/[source]` page uses `useLiveData` hook — fetches all three endpoints on mount, reconstructs `TRMContext`, polls every 3 seconds. Same dashboard components as the run page, minus `IncomingBanner`/`BufferZone` (transient state not persisted to DB).

---

## Running a Full Simulation

`main_live.py` requires `ANTHROPIC_API_KEY` set in `.env`. The mock scripts do not.

```bash
alembic upgrade head              # ensure schema exists
python db/reset.py                # clear all tables (between runs)
python preprocessing/mock/run.py & # start preprocessing (polls for captured rows)
python capture/mock/run.py &      # start capture (writes packets to DB every 10s)
python trm/main_live.py           # start TRM (polls for processed rows, routes + persists)
```

Packets appear in the UI every ~20 seconds (10s capture + 10s ASR delay). Refresh at any point — state is fully restored from the DB.

---

## Not Yet Implemented

- Real radio capture (hardware-dependent)
- Real ASR / Whisper integration
- Scorer
- UI scenario builder
- Prompt versioning
- Multi-run comparison
