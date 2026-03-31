"""Tests for the run endpoints (Phase 2).

Uses a mock TRMRouter so no API key or LLM calls are needed.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from contracts.models import ReadyPacket, RoutingRecord
from src.models.router import TRMContext


def _make_mock_router():
    """Create a mock TRMRouter that returns canned routing decisions."""
    router = MagicMock()
    router.context = TRMContext(buffers_remaining=5)
    router.routing_records = []
    call_count = 0

    async def mock_route(packet: ReadyPacket) -> RoutingRecord:
        nonlocal call_count
        call_count += 1

        # Alternate between two threads
        if packet.metadata.get("speaker") in ("bob", "dylan"):
            thread_id = "thread_A"
        else:
            thread_id = "thread_B"

        is_first_in_thread = not any(
            r.thread_id == thread_id for r in router.routing_records
        )

        record = RoutingRecord(
            packet_id=packet.id,
            thread_decision="new" if is_first_in_thread else "existing",
            thread_id=thread_id,
            event_decision="none",
            event_id=None,
        )
        router.routing_records.append(record)

        # Update context to mimic real behavior
        router.context.incoming_packet = packet
        return record

    router.route = mock_route
    return router


@pytest.mark.asyncio
async def test_create_run(client):
    resp = await client.post("/api/runs", json={
        "source": "scenario",
        "tier": "tier_one",
        "scenario": "scenario_02_interleaved",
        "speed_factor": 100.0,
    })
    assert resp.status_code == 200
    assert "run_id" in resp.json()


@pytest.mark.asyncio
async def test_create_run_bad_scenario(client):
    resp = await client.post("/api/runs", json={
        "source": "scenario",
        "tier": "tier_one",
        "scenario": "nonexistent",
        "speed_factor": 100.0,
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_run_missing_fields(client):
    resp = await client.post("/api/runs", json={"source": "scenario"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_websocket_full_run(client):
    """Start a run with mocked LLM, connect via WebSocket, verify all messages arrive."""
    with patch("api.services.runner.TRMRouter", return_value=_make_mock_router()):
        # Create run
        resp = await client.post("/api/runs", json={
            "source": "scenario",
            "tier": "tier_one",
            "scenario": "scenario_02_interleaved",
            "speed_factor": 1000.0,
        })
        run_id = resp.json()["run_id"]

        # Give the run a moment to finish (mocked, so it's fast)
        await asyncio.sleep(2)

        # Connect via WebSocket — should get full backlog
        from api.main import app
        from starlette.testclient import TestClient

        # Use sync TestClient for WebSocket (httpx doesn't support WS)
        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(f"/ws/runs/{run_id}") as ws:
                messages = []
                # Receive all backlogged messages
                while True:
                    try:
                        msg = ws.receive_json(mode="text")
                        messages.append(msg)
                        if msg["type"] in ("run_complete", "run_error"):
                            break
                    except Exception:
                        break

                types = [m["type"] for m in messages]
                assert "run_started" in types
                assert "run_complete" in types
                assert types.count("packet_routed") == 12

                # Verify packet_routed messages have expected structure
                routed = [m for m in messages if m["type"] == "packet_routed"]
                for msg in routed:
                    assert "packet_id" in msg
                    assert "routing_record" in msg
                    assert "context" in msg
                    assert "thread_decision" in msg["routing_record"]
                    assert "event_decision" in msg["routing_record"]


@pytest.mark.asyncio
async def test_websocket_message_order(client):
    """Verify messages arrive in correct order: run_started, packet_routed..., run_complete."""
    with patch("api.services.runner.TRMRouter", return_value=_make_mock_router()):
        resp = await client.post("/api/runs", json={
            "source": "scenario",
            "tier": "tier_one",
            "scenario": "scenario_02_interleaved",
            "speed_factor": 1000.0,
        })
        run_id = resp.json()["run_id"]
        await asyncio.sleep(2)

        from api.main import app
        from starlette.testclient import TestClient

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(f"/ws/runs/{run_id}") as ws:
                messages = []
                while True:
                    try:
                        msg = ws.receive_json(mode="text")
                        messages.append(msg)
                        if msg["type"] in ("run_complete", "run_error"):
                            break
                    except Exception:
                        break

                assert messages[0]["type"] == "run_started"
                assert messages[-1]["type"] == "run_complete"
                for m in messages[1:-1]:
                    assert m["type"] == "packet_routed"


@pytest.mark.asyncio
async def test_websocket_run_not_found(client):
    """Connecting to a nonexistent run should close the WebSocket."""
    from api.main import app
    from starlette.testclient import TestClient

    with TestClient(app) as sync_client:
        with pytest.raises(Exception):
            with sync_client.websocket_connect("/ws/runs/nonexistent") as ws:
                ws.receive_json()


@pytest.mark.asyncio
async def test_run_complete_has_routing_records(client):
    """The run_complete message should include all routing records."""
    with patch("api.services.runner.TRMRouter", return_value=_make_mock_router()):
        resp = await client.post("/api/runs", json={
            "source": "scenario",
            "tier": "tier_one",
            "scenario": "scenario_02_interleaved",
            "speed_factor": 1000.0,
        })
        run_id = resp.json()["run_id"]
        await asyncio.sleep(2)

        from api.main import app
        from starlette.testclient import TestClient

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(f"/ws/runs/{run_id}") as ws:
                messages = []
                while True:
                    try:
                        msg = ws.receive_json(mode="text")
                        messages.append(msg)
                        if msg["type"] in ("run_complete", "run_error"):
                            break
                    except Exception:
                        break

                complete = messages[-1]
                assert complete["type"] == "run_complete"
                assert complete["total_packets"] == 12
                assert len(complete["routing_records"]) == 12
