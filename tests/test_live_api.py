"""Tests for the live pipeline API endpoints (Phase 3.4)."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.main import app
from db.base import Base
from db.models import Event, Thread, ThreadEvent, Transmission
from db.session import get_session
import db.models  # noqa: F401


@pytest_asyncio.fixture
async def live_client():
    """Test client with DB dependency overridden to use in-memory SQLite."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def override_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, factory

    app.dependency_overrides.clear()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_transmission(packet_id, status="routed", thread_id=None, event_id=None,
                       thread_decision=None, event_decision=None, text="Hello",
                       timestamp=None):
    return Transmission(
        id=packet_id,
        timestamp=timestamp or datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        status=status,
        talkgroup_id=1001,
        source_unit=4021,
        frequency=851.0125,
        duration=2.1,
        encryption_status=False,
        audio_path="out/wav/mock.wav",
        text=text,
        thread_id=thread_id,
        event_id=event_id,
        thread_decision=thread_decision,
        event_decision=event_decision,
    )


# --- Threads ---


@pytest.mark.asyncio
async def test_threads_empty(live_client):
    client, _ = live_client
    resp = await client.get("/api/live/threads")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_threads_with_packets_and_event_ids(live_client):
    client, factory = live_client
    async with factory() as session:
        session.add(Thread(id="thread_A", label="Conversation A", status="open"))
        session.add(Event(id="event_A", label="Incident", status="open"))
        session.add(ThreadEvent(thread_id="thread_A", event_id="event_A"))
        session.add(_make_transmission(
            "pkt_001", thread_id="thread_A", event_id="event_A",
            thread_decision="new", event_decision="new",
        ))
        session.add(_make_transmission(
            "pkt_002", thread_id="thread_A", event_id="event_A",
            thread_decision="existing", event_decision="existing",
            timestamp=datetime(2024, 1, 15, 9, 0, 10, tzinfo=timezone.utc),
        ))
        await session.commit()

    resp = await client.get("/api/live/threads")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1

    thread = data[0]
    assert thread["thread_id"] == "thread_A"
    assert thread["label"] == "Conversation A"
    assert thread["status"] == "open"
    assert len(thread["packets"]) == 2
    assert thread["packets"][0]["id"] == "pkt_001"
    assert thread["packets"][1]["id"] == "pkt_002"
    assert thread["event_ids"] == ["event_A"]

    # Verify packet shape
    pkt = thread["packets"][0]
    assert pkt["text"] == "Hello"
    assert pkt["metadata"]["talkgroup_id"] == 1001


@pytest.mark.asyncio
async def test_threads_only_open(live_client):
    client, factory = live_client
    async with factory() as session:
        session.add(Thread(id="thread_A", label="Open", status="open"))
        session.add(Thread(id="thread_B", label="Closed", status="closed"))
        await session.commit()

    resp = await client.get("/api/live/threads")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["thread_id"] == "thread_A"


# --- Events ---


@pytest.mark.asyncio
async def test_events_with_thread_ids(live_client):
    client, factory = live_client
    async with factory() as session:
        session.add(Thread(id="thread_A", label="Conv", status="open"))
        session.add(Event(id="event_A", label="Incident", status="open", opened_at="pkt_001"))
        session.add(ThreadEvent(thread_id="thread_A", event_id="event_A"))
        # Need the transmission for the FK on opened_at
        session.add(_make_transmission("pkt_001", thread_id="thread_A", event_id="event_A"))
        await session.commit()

    resp = await client.get("/api/live/events")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1

    event = data[0]
    assert event["event_id"] == "event_A"
    assert event["label"] == "Incident"
    assert event["opened_at"] == "pkt_001"
    assert event["thread_ids"] == ["thread_A"]


@pytest.mark.asyncio
async def test_events_only_open(live_client):
    client, factory = live_client
    async with factory() as session:
        session.add(Event(id="event_A", label="Open", status="open"))
        session.add(Event(id="event_B", label="Closed", status="closed"))
        await session.commit()

    resp = await client.get("/api/live/events")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event_id"] == "event_A"


# --- Transmissions ---


@pytest.mark.asyncio
async def test_transmissions_ordered_by_timestamp(live_client):
    client, factory = live_client
    async with factory() as session:
        session.add(_make_transmission(
            "pkt_002", timestamp=datetime(2024, 1, 15, 9, 0, 20, tzinfo=timezone.utc),
        ))
        session.add(_make_transmission(
            "pkt_001", timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
        ))
        session.add(_make_transmission(
            "pkt_003", timestamp=datetime(2024, 1, 15, 9, 0, 40, tzinfo=timezone.utc),
        ))
        await session.commit()

    resp = await client.get("/api/live/transmissions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert [t["id"] for t in data] == ["pkt_001", "pkt_002", "pkt_003"]


@pytest.mark.asyncio
async def test_transmissions_only_routed(live_client):
    client, factory = live_client
    async with factory() as session:
        session.add(_make_transmission("pkt_001", status="routed"))
        session.add(_make_transmission("pkt_002", status="processed"))
        session.add(_make_transmission("pkt_003", status="captured"))
        await session.commit()

    resp = await client.get("/api/live/transmissions")
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "pkt_001"
