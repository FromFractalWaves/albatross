"""Tests for the live pipeline manager and WebSocket endpoint."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.testclient import TestClient

from api.main import app
from api.services.live_pipeline import LivePipelineManager
from contracts.models import ReadyPacket, RoutingRecord
from db.base import Base
from trm.models.router import TRMContext
import db.models  # noqa: F401


def _make_mock_router():
    """Create a mock TRMRouter that returns canned routing decisions."""
    router = MagicMock()
    router.context = TRMContext(buffers_remaining=5)
    router.routing_records = []

    async def mock_route(packet: ReadyPacket) -> RoutingRecord:
        record = RoutingRecord(
            packet_id=packet.id,
            thread_decision="new" if len(router.routing_records) == 0 else "existing",
            thread_id="thread_A",
            event_decision="none",
            event_id=None,
        )
        router.routing_records.append(record)
        router.context.incoming_packet = packet
        return record

    router.route = mock_route
    return router


@pytest_asyncio.fixture
async def pipeline_session_factory():
    """In-memory SQLite session factory for pipeline tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _fast_pipeline():
    """Patch capture interval and ASR delay to near-zero for fast tests."""
    return (
        patch("api.services.live_pipeline.CAPTURE_INTERVAL", 0.01),
        patch("api.services.live_pipeline.ASR_DELAY", 0.01),
        patch("api.services.live_pipeline.TRMRouter", return_value=_make_mock_router()),
        patch("api.services.live_pipeline.reset_db", return_value=None),
    )


@pytest.mark.asyncio
async def test_manager_status_lifecycle(pipeline_session_factory):
    """Manager status should reflect running/stopped state."""
    manager = LivePipelineManager()
    assert manager.status == "stopped"

    with _fast_pipeline()[0], _fast_pipeline()[1], _fast_pipeline()[2], _fast_pipeline()[3]:
        await manager.start(pipeline_session_factory)
        assert manager.status == "running"

        for _ in range(120):
            if manager.status == "stopped":
                break
            await asyncio.sleep(0.25)

        assert manager.status == "stopped"


@pytest.mark.asyncio
async def test_manager_stop_cancels_task(pipeline_session_factory):
    """Calling stop should cancel the running pipeline task."""
    manager = LivePipelineManager()

    with _fast_pipeline()[0], _fast_pipeline()[1], _fast_pipeline()[2], _fast_pipeline()[3]:
        await manager.start(pipeline_session_factory)
        assert manager.status == "running"

        await manager.stop()
        assert manager.status == "stopped"


@pytest.mark.asyncio
async def test_manager_collects_messages(pipeline_session_factory):
    """Pipeline should collect broadcast messages in the backlog."""
    manager = LivePipelineManager()

    with _fast_pipeline()[0], _fast_pipeline()[1], _fast_pipeline()[2], _fast_pipeline()[3]:
        await manager.start(pipeline_session_factory)

        for _ in range(120):
            if manager.status == "stopped":
                break
            await asyncio.sleep(0.25)

        types = [m["type"] for m in manager._messages]
        assert "pipeline_started" in types
        assert "packet_captured" in types
        assert "packet_preprocessed" in types
        assert "packet_routed" in types
        assert "pipeline_complete" in types


@pytest.mark.asyncio
async def test_manager_message_order(pipeline_session_factory):
    """Messages should arrive in pipeline order."""
    manager = LivePipelineManager()

    with _fast_pipeline()[0], _fast_pipeline()[1], _fast_pipeline()[2], _fast_pipeline()[3]:
        await manager.start(pipeline_session_factory)

        for _ in range(120):
            if manager.status == "stopped":
                break
            await asyncio.sleep(0.25)

        types = [m["type"] for m in manager._messages]
        assert types[0] == "pipeline_started"
        assert types[-1] == "pipeline_complete"


def test_websocket_receives_backlog():
    """A WebSocket connecting after pipeline completes should receive the full backlog."""
    manager = LivePipelineManager()
    # Manually populate backlog
    manager._messages = [
        {"type": "pipeline_started", "total_packets": 2},
        {"type": "packet_captured", "packet_id": "pkt_001", "timestamp": "2024-01-01T00:00:00Z", "metadata": {}},
        {"type": "packet_preprocessed", "packet_id": "pkt_001", "text": "hello"},
        {"type": "packet_routed", "packet_id": "pkt_001", "routing_record": {}, "context": {}, "incoming_packet": None},
        {"type": "pipeline_complete", "total_packets": 1, "routing_records": []},
    ]
    app.state.live_pipeline_manager = manager

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live/mock") as ws:
            messages = []
            # Receive all backlog messages
            for _ in range(len(manager._messages)):
                msg = ws.receive_json(mode="text")
                messages.append(msg)

            types = [m["type"] for m in messages]
            assert types == [
                "pipeline_started",
                "packet_captured",
                "packet_preprocessed",
                "packet_routed",
                "pipeline_complete",
            ]

    # Restore
    app.state.live_pipeline_manager = LivePipelineManager()


def test_websocket_two_clients_receive_backlog():
    """Two clients connecting should both receive the backlog."""
    manager = LivePipelineManager()
    manager._messages = [
        {"type": "pipeline_started", "total_packets": 1},
        {"type": "pipeline_complete", "total_packets": 1, "routing_records": []},
    ]
    app.state.live_pipeline_manager = manager

    with TestClient(app) as client:
        with client.websocket_connect("/ws/live/mock") as ws1:
            with client.websocket_connect("/ws/live/mock") as ws2:
                msg1 = ws1.receive_json(mode="text")
                msg2 = ws2.receive_json(mode="text")
                assert msg1["type"] == "pipeline_started"
                assert msg2["type"] == "pipeline_started"

    app.state.live_pipeline_manager = LivePipelineManager()
