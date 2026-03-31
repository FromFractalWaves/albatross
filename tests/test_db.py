from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, select

from db.models import Event, RoutingRecord, Thread, ThreadEvent, Transmission


def _make_transmission(**overrides):
    """Return a dict of default Transmission fields, with overrides applied."""
    defaults = {
        "id": "pkt_001",
        "timestamp": datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        "status": "captured",
        "talkgroup_id": 1001,
        "source_unit": 4021,
        "frequency": 851.0125,
        "duration": 3.2,
        "encryption_status": False,
        "audio_path": "out/wav/mock_pkt_001.wav",
    }
    defaults.update(overrides)
    return defaults


def test_models_importable():
    assert Transmission is not None
    assert Thread is not None
    assert Event is not None
    assert ThreadEvent is not None
    assert RoutingRecord is not None


@pytest.mark.asyncio
async def test_tables_created(db_engine):
    async with db_engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    expected = {"transmissions", "threads", "events", "thread_events", "routing_records"}
    assert expected.issubset(set(table_names))


@pytest.mark.asyncio
async def test_insert_query_thread(db_session):
    thread = Thread(id="thread_A", label="Bob and Dylan chat", status="open")
    db_session.add(thread)
    await db_session.commit()

    result = await db_session.get(Thread, "thread_A")
    assert result is not None
    assert result.label == "Bob and Dylan chat"
    assert result.status == "open"


@pytest.mark.asyncio
async def test_insert_query_event(db_session):
    event = Event(id="event_A", label="Shift schedule discussion", status="open")
    db_session.add(event)
    await db_session.commit()

    result = await db_session.get(Event, "event_A")
    assert result is not None
    assert result.label == "Shift schedule discussion"
    assert result.status == "open"
    assert result.opened_at is None


@pytest.mark.asyncio
async def test_insert_query_transmission(db_session):
    thread = Thread(id="thread_A", label="Test thread")
    db_session.add(thread)
    await db_session.flush()

    t = Transmission(**_make_transmission(thread_id="thread_A"))
    db_session.add(t)
    await db_session.commit()

    result = await db_session.get(Transmission, "pkt_001")
    assert result is not None
    assert result.status == "captured"
    assert result.talkgroup_id == 1001
    assert result.frequency == 851.0125
    assert result.encryption_status is False
    assert result.thread_id == "thread_A"
    assert result.text is None


@pytest.mark.asyncio
async def test_insert_query_routing_record(db_session):
    thread = Thread(id="thread_A", label="Test thread")
    db_session.add(thread)
    await db_session.flush()

    t = Transmission(**_make_transmission(thread_id="thread_A"))
    db_session.add(t)
    await db_session.flush()

    rr = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="none",
        event_id=None,
    )
    db_session.add(rr)
    await db_session.commit()

    result = (await db_session.execute(select(RoutingRecord))).scalar_one()
    assert result.id is not None
    assert result.packet_id == "pkt_001"
    assert result.thread_decision == "new"
    assert result.event_decision == "none"


@pytest.mark.asyncio
async def test_thread_event_join(db_session):
    thread = Thread(id="thread_A", label="Test thread")
    event = Event(id="event_A", label="Test event")
    db_session.add_all([thread, event])
    await db_session.flush()

    te = ThreadEvent(thread_id="thread_A", event_id="event_A")
    db_session.add(te)
    await db_session.commit()

    result = (await db_session.execute(select(ThreadEvent))).scalar_one()
    assert result.thread_id == "thread_A"
    assert result.event_id == "event_A"
