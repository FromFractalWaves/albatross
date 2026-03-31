"""Tests for the TRM persistence layer (Phase 3.3).

Tests RoutingRecord.to_orm() and persist_routing_result() using in-memory SQLite.
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from contracts.models import RoutingRecord
from db.base import Base
from db.models import (
    Event as ORMEvent,
    RoutingRecord as ORMRoutingRecord,
    Thread as ORMThread,
    ThreadEvent as ORMThreadEvent,
    Transmission,
)
from db.persist import persist_routing_result
from trm.models.router import Event, Thread, TRMContext
from contracts.models import ReadyPacket


@pytest_asyncio.fixture
async def session():
    """In-memory SQLite session for persistence tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _insert_transmission(session, packet_id="pkt_001", status="processed"):
    """Helper to insert a processed transmission row."""
    t = Transmission(
        id=packet_id,
        timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        status=status,
        talkgroup_id=1001,
        source_unit=4021,
        frequency=851.0125,
        duration=2.1,
        encryption_status=False,
        audio_path="out/wav/mock.wav",
        text="Hello world",
    )
    session.add(t)
    return t


def _make_context_with_thread_and_event():
    """Build a TRMContext with one thread and one event."""
    packet = ReadyPacket(
        id="pkt_001",
        timestamp="2024-01-15T09:00:00+00:00",
        text="Hello world",
    )
    thread = Thread(
        thread_id="thread_A",
        label="Test conversation",
        packets=[packet],
        event_ids=["event_A"],
    )
    event = Event(
        event_id="event_A",
        label="Test event",
        opened_at="pkt_001",
        thread_ids=["thread_A"],
    )
    return TRMContext(
        active_threads=[thread],
        active_events=[event],
        buffers_remaining=5,
    )


# --- Tests ---


@pytest.mark.asyncio
async def test_routing_record_to_orm():
    """RoutingRecord.to_orm() produces a valid ORM instance."""
    record = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="new",
        event_id="event_A",
    )
    orm = record.to_orm()
    assert isinstance(orm, ORMRoutingRecord)
    assert orm.packet_id == "pkt_001"
    assert orm.thread_decision == "new"
    assert orm.thread_id == "thread_A"
    assert orm.event_decision == "new"
    assert orm.event_id == "event_A"


@pytest.mark.asyncio
async def test_persist_new_thread_and_event(session):
    """persist_routing_result creates thread, event, join, routing record, and updates transmission."""
    _insert_transmission(session, "pkt_001")
    await session.commit()

    record = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="new",
        event_id="event_A",
    )
    context = _make_context_with_thread_and_event()

    await persist_routing_result(session, "pkt_001", record, context)

    # Verify transmission updated
    result = await session.execute(select(Transmission).where(Transmission.id == "pkt_001"))
    t = result.scalar_one()
    assert t.status == "routed"
    assert t.thread_id == "thread_A"
    assert t.event_id == "event_A"
    assert t.thread_decision == "new"
    assert t.event_decision == "new"

    # Verify thread created
    result = await session.execute(select(ORMThread).where(ORMThread.id == "thread_A"))
    thread = result.scalar_one()
    assert thread.label == "Test conversation"

    # Verify event created
    result = await session.execute(select(ORMEvent).where(ORMEvent.id == "event_A"))
    event = result.scalar_one()
    assert event.label == "Test event"
    assert event.opened_at == "pkt_001"

    # Verify thread_event join
    result = await session.execute(select(ORMThreadEvent))
    join = result.scalar_one()
    assert join.thread_id == "thread_A"
    assert join.event_id == "event_A"

    # Verify routing record
    result = await session.execute(select(ORMRoutingRecord))
    rr = result.scalar_one()
    assert rr.packet_id == "pkt_001"
    assert rr.thread_decision == "new"


@pytest.mark.asyncio
async def test_persist_existing_thread(session):
    """Second packet joining an existing thread upserts correctly."""
    # First packet creates thread
    _insert_transmission(session, "pkt_001")
    await session.commit()

    record1 = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="none",
        event_id=None,
    )
    packet1 = ReadyPacket(id="pkt_001", timestamp="2024-01-15T09:00:00+00:00", text="Hello")
    ctx1 = TRMContext(
        active_threads=[Thread(thread_id="thread_A", label="Conversation", packets=[packet1])],
        buffers_remaining=5,
    )
    await persist_routing_result(session, "pkt_001", record1, ctx1)

    # Second packet joins existing thread
    _insert_transmission(session, "pkt_002")
    await session.commit()

    record2 = RoutingRecord(
        packet_id="pkt_002",
        thread_decision="existing",
        thread_id="thread_A",
        event_decision="none",
        event_id=None,
    )
    packet2 = ReadyPacket(id="pkt_002", timestamp="2024-01-15T09:00:10+00:00", text="World")
    ctx2 = TRMContext(
        active_threads=[Thread(
            thread_id="thread_A",
            label="Conversation updated",
            packets=[packet1, packet2],
        )],
        buffers_remaining=5,
    )
    await persist_routing_result(session, "pkt_002", record2, ctx2)

    # Thread label should be updated
    result = await session.execute(select(ORMThread).where(ORMThread.id == "thread_A"))
    thread = result.scalar_one()
    assert thread.label == "Conversation updated"

    # Two routing records
    result = await session.execute(select(ORMRoutingRecord))
    assert len(result.scalars().all()) == 2

    # Both transmissions routed
    result = await session.execute(select(Transmission).where(Transmission.status == "routed"))
    assert len(result.scalars().all()) == 2


@pytest.mark.asyncio
async def test_persist_buffer_decision(session):
    """Buffer decision writes routing record and updates transmission but skips thread/event."""
    _insert_transmission(session, "pkt_001")
    await session.commit()

    record = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="buffer",
        thread_id=None,
        event_decision="unknown",
        event_id=None,
    )
    context = TRMContext(buffers_remaining=4)

    await persist_routing_result(session, "pkt_001", record, context)

    # Transmission updated
    result = await session.execute(select(Transmission).where(Transmission.id == "pkt_001"))
    t = result.scalar_one()
    assert t.status == "routed"
    assert t.thread_id is None
    assert t.thread_decision == "buffer"

    # No threads or events created
    result = await session.execute(select(ORMThread))
    assert result.scalars().all() == []
    result = await session.execute(select(ORMEvent))
    assert result.scalars().all() == []

    # Routing record still written
    result = await session.execute(select(ORMRoutingRecord))
    rr = result.scalar_one()
    assert rr.thread_decision == "buffer"


@pytest.mark.asyncio
async def test_persist_none_event(session):
    """Thread with no event skips event upsert and thread_events join."""
    _insert_transmission(session, "pkt_001")
    await session.commit()

    record = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="none",
        event_id=None,
    )
    packet = ReadyPacket(id="pkt_001", timestamp="2024-01-15T09:00:00+00:00", text="Hello")
    context = TRMContext(
        active_threads=[Thread(thread_id="thread_A", label="Chat", packets=[packet])],
        buffers_remaining=5,
    )

    await persist_routing_result(session, "pkt_001", record, context)

    # Thread created
    result = await session.execute(select(ORMThread))
    assert len(result.scalars().all()) == 1

    # No events
    result = await session.execute(select(ORMEvent))
    assert result.scalars().all() == []

    # No thread_events
    result = await session.execute(select(ORMThreadEvent))
    assert result.scalars().all() == []
