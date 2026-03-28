"""Tests for the scenario endpoints (Phase 1).

No API key needed — these just read files from data/.
"""

import pytest


@pytest.mark.asyncio
async def test_list_scenarios(client):
    resp = await client.get("/api/scenarios")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    tier_one = next(t for t in data if t["tier"] == "tier_one")
    names = [s["name"] for s in tier_one["scenarios"]]
    assert "scenario_02_interleaved" in names


@pytest.mark.asyncio
async def test_list_scenarios_sorted(client):
    resp = await client.get("/api/scenarios")
    data = resp.json()

    tier_one = next(t for t in data if t["tier"] == "tier_one")
    names = [s["name"] for s in tier_one["scenarios"]]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_scenarios_have_paths(client):
    resp = await client.get("/api/scenarios")
    tier_one = next(t for t in resp.json() if t["tier"] == "tier_one")

    for scenario in tier_one["scenarios"]:
        assert "name" in scenario
        assert "path" in scenario
        assert scenario["path"] == f"tier_one/{scenario['name']}"


@pytest.mark.asyncio
async def test_get_scenario_detail(client):
    resp = await client.get("/api/scenarios/tier_one/scenario_02_interleaved")
    assert resp.status_code == 200

    data = resp.json()
    assert data["tier"] == "tier_one"
    assert data["name"] == "scenario_02_interleaved"
    assert isinstance(data["packets"], list)
    assert len(data["packets"]) == 12
    assert data["expected_output"] is not None
    assert data["readme"] is not None


@pytest.mark.asyncio
async def test_get_scenario_packets_structure(client):
    resp = await client.get("/api/scenarios/tier_one/scenario_02_interleaved")
    packets = resp.json()["packets"]

    for pkt in packets:
        assert "id" in pkt
        assert "timestamp" in pkt
        assert "text" in pkt
        assert "metadata" in pkt


@pytest.mark.asyncio
async def test_get_scenario_expected_output_structure(client):
    resp = await client.get("/api/scenarios/tier_one/scenario_02_interleaved")
    expected = resp.json()["expected_output"]

    assert "threads" in expected
    assert "events" in expected
    assert "routing" in expected


@pytest.mark.asyncio
async def test_get_scenario_readme_content(client):
    resp = await client.get("/api/scenarios/tier_one/scenario_02_interleaved")
    readme = resp.json()["readme"]

    assert "Interleaved" in readme


@pytest.mark.asyncio
async def test_get_scenario_not_found(client):
    resp = await client.get("/api/scenarios/tier_one/nonexistent_scenario")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_scenario_bad_tier(client):
    resp = await client.get("/api/scenarios/tier_999/scenario_02_interleaved")
    assert resp.status_code == 404
