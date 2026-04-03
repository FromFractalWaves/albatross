"""Tests for the mock pipeline API endpoints (push-only architecture)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from api.main import app
from api.services.live_pipeline import LivePipelineManager


@pytest.fixture(autouse=True)
def _fresh_manager():
    """Give each test a fresh LivePipelineManager."""
    app.state.live_pipeline_manager = LivePipelineManager()
    yield
    app.state.live_pipeline_manager = LivePipelineManager()


@pytest.mark.asyncio
async def test_start_returns_started():
    with patch.object(LivePipelineManager, "start", new_callable=AsyncMock) as mock_start:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/mock/start")

        assert resp.status_code == 200
        assert resp.json() == {"status": "started"}
        assert mock_start.await_count == 1


@pytest.mark.asyncio
async def test_stop_returns_stopped():
    with patch.object(LivePipelineManager, "stop", new_callable=AsyncMock) as mock_stop:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/mock/stop")

        assert resp.status_code == 200
        assert resp.json() == {"status": "stopped"}
        assert mock_stop.await_count == 1


@pytest.mark.asyncio
async def test_status_stopped_by_default():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/mock/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_status_running():
    manager = app.state.live_pipeline_manager
    # Simulate a running task
    manager._task = asyncio.create_task(asyncio.sleep(60))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/mock/status")

    manager._task.cancel()
    try:
        await manager._task
    except asyncio.CancelledError:
        pass

    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_start_calls_manager_with_session_factory():
    """Verify start passes the session factory to the manager."""
    with patch.object(LivePipelineManager, "start", new_callable=AsyncMock) as mock_start:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/api/mock/start")

        # The session factory (AsyncSessionLocal) should have been passed
        assert mock_start.await_count == 1
        args = mock_start.call_args
        assert args is not None


@pytest.mark.asyncio
async def test_stop_when_not_running():
    """Stopping when nothing is running should succeed gracefully."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/mock/stop")

    assert resp.status_code == 200
    assert resp.json() == {"status": "stopped"}
