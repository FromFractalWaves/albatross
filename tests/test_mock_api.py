"""Tests for the mock pipeline API endpoints."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from api.main import app


@pytest.fixture(autouse=True)
def _clear_mock_state():
    """Reset mock_processes state before each test."""
    app.state.mock_processes = []
    yield
    app.state.mock_processes = []


def _make_mock_process(alive: bool = True) -> MagicMock:
    proc = MagicMock(spec=asyncio.subprocess.Process)
    proc.returncode = None if alive else 0
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    return proc


@pytest.mark.asyncio
async def test_start_launches_processes():
    with patch("api.routes.mock.reset_db", new_callable=AsyncMock) as mock_reset, \
         patch("api.routes.mock.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(alive=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/mock/start")

        assert resp.status_code == 200
        assert resp.json() == {"status": "started"}
        assert mock_reset.await_count == 1
        assert mock_exec.await_count == 3


@pytest.mark.asyncio
async def test_status_running():
    app.state.mock_processes = [_make_mock_process(alive=True)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/mock/status")

    assert resp.status_code == 200
    assert resp.json() == {"status": "running"}


@pytest.mark.asyncio
async def test_status_stopped_no_processes():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/mock/status")

    assert resp.status_code == 200
    assert resp.json() == {"status": "stopped"}


@pytest.mark.asyncio
async def test_status_stopped_finished_processes():
    app.state.mock_processes = [_make_mock_process(alive=False)]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/mock/status")

    assert resp.status_code == 200
    assert resp.json() == {"status": "stopped"}


@pytest.mark.asyncio
async def test_stop_terminates_processes():
    procs = [_make_mock_process(alive=True) for _ in range(3)]
    app.state.mock_processes = procs

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/mock/stop")

    assert resp.status_code == 200
    assert resp.json() == {"status": "stopped"}
    for proc in procs:
        proc.terminate.assert_called_once()
    assert app.state.mock_processes == []


@pytest.mark.asyncio
async def test_start_while_running_restarts():
    old_procs = [_make_mock_process(alive=True) for _ in range(3)]
    app.state.mock_processes = old_procs

    with patch("api.routes.mock.reset_db", new_callable=AsyncMock), \
         patch("api.routes.mock.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = _make_mock_process(alive=True)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/mock/start")

    assert resp.status_code == 200
    for proc in old_procs:
        proc.terminate.assert_called_once()
    assert mock_exec.await_count == 3
