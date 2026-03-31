"""Tests for the mock pipeline (Phase 3.2b).

Tests capture → DB, preprocessing update, and DB reset using in-memory SQLite.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from contracts.models import TransmissionPacket
from db.base import Base
from db.models import Transmission, Thread, Event, ThreadEvent
from db.models import RoutingRecord as RoutingRecordORM

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest_asyncio.fixture
async def session():
    """In-memory SQLite session for mock pipeline tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_capture_writes_transmission(session):
    """TransmissionPacket.to_orm() produces a valid captured row."""
    path = DATA_DIR / "tier_one" / "scenario_02_interleaved" / "packets_radio.json"
    data = json.loads(path.read_text())
    entry = data[0]

    tp = TransmissionPacket(
        id=entry["id"],
        timestamp=entry["timestamp"],
        talkgroup_id=entry["metadata"]["talkgroup_id"],
        source_unit=entry["metadata"]["source_unit"],
        frequency=entry["metadata"]["frequency"],
        duration=entry["metadata"]["duration"],
        encryption_status=entry["metadata"]["encryption_status"],
        audio_path=entry["metadata"]["audio_path"],
    )

    orm_obj = tp.to_orm()
    session.add(orm_obj)
    await session.commit()

    result = await session.execute(select(Transmission).where(Transmission.id == "pkt_001"))
    row = result.scalar_one()

    assert row.status == "captured"
    assert row.text is None
    assert row.talkgroup_id == 1001
    assert row.source_unit == 4021
    assert row.frequency == 851.0125
    assert row.encryption_status is False
    assert isinstance(row.timestamp, datetime)


@pytest.mark.asyncio
async def test_preprocessing_updates_transmission(session):
    """Simulated preprocessing updates text, ASR fields, and status."""
    # Insert a captured row
    t = Transmission(
        id="pkt_test",
        timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        status="captured",
        talkgroup_id=1001,
        source_unit=4021,
        frequency=851.0125,
        duration=2.1,
        encryption_status=False,
        audio_path="out/wav/mock_test.wav",
        text=None,
    )
    session.add(t)
    await session.commit()

    # Simulate preprocessing: flip to processing, then processed
    result = await session.execute(select(Transmission).where(Transmission.id == "pkt_test"))
    row = result.scalar_one()
    row.status = "processing"
    await session.commit()

    row.text = "Hello world"
    row.asr_model = "mock"
    row.asr_confidence = 1.0
    row.asr_passes = 1
    row.status = "processed"
    await session.commit()

    # Verify
    result = await session.execute(select(Transmission).where(Transmission.id == "pkt_test"))
    row = result.scalar_one()
    assert row.status == "processed"
    assert row.text == "Hello world"
    assert row.asr_model == "mock"
    assert row.asr_confidence == 1.0
    assert row.asr_passes == 1


@pytest.mark.asyncio
async def test_reset_clears_all_tables(session):
    """DB reset deletes all rows from all tables in FK-safe order."""
    # Insert a thread
    session.add(Thread(id="thread_A", label="Test thread", status="open"))
    await session.flush()

    # Insert an event
    session.add(Event(id="event_A", label="Test event", status="open"))
    await session.flush()

    # Insert a transmission referencing the thread and event
    session.add(Transmission(
        id="pkt_reset",
        timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        status="routed",
        talkgroup_id=1001,
        source_unit=4021,
        frequency=851.0125,
        duration=2.1,
        encryption_status=False,
        audio_path="out/wav/mock.wav",
        text="test",
        thread_id="thread_A",
        event_id="event_A",
    ))
    await session.flush()

    # Insert thread_event join
    session.add(ThreadEvent(thread_id="thread_A", event_id="event_A"))
    await session.flush()

    # Insert routing record
    session.add(RoutingRecordORM(
        packet_id="pkt_reset",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="new",
        event_id="event_A",
    ))
    await session.commit()

    # Run reset logic (same order as db/reset.py)
    tables = ["routing_records", "thread_events", "transmissions", "threads", "events"]
    for table in tables:
        await session.execute(text(f"DELETE FROM {table}"))
    await session.commit()

    # Verify all empty
    for model in [RoutingRecordORM, ThreadEvent, Transmission, Thread, Event]:
        result = await session.execute(select(model))
        assert result.scalars().all() == [], f"{model.__tablename__} not empty"
