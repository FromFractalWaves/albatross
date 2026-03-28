import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter()

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@router.get("/scenarios")
def list_scenarios():
    if not DATA_DIR.is_dir():
        return []

    tiers = []
    for tier_dir in sorted(DATA_DIR.iterdir()):
        if not tier_dir.is_dir():
            continue
        scenarios = []
        for scenario_dir in sorted(tier_dir.iterdir()):
            if not scenario_dir.is_dir():
                continue
            if not (scenario_dir / "packets.json").exists():
                continue
            scenarios.append({
                "name": scenario_dir.name,
                "path": f"{tier_dir.name}/{scenario_dir.name}",
            })
        if scenarios:
            tiers.append({"tier": tier_dir.name, "scenarios": scenarios})

    return tiers


@router.get("/scenarios/{tier}/{scenario}")
def get_scenario(tier: str, scenario: str):
    scenario_dir = DATA_DIR / tier / scenario

    if not scenario_dir.is_dir():
        raise HTTPException(status_code=404, detail="Scenario not found")

    packets_path = scenario_dir / "packets.json"
    expected_path = scenario_dir / "expected_output.json"
    readme_path = scenario_dir / "README.md"

    if not packets_path.exists():
        raise HTTPException(status_code=404, detail="Scenario missing packets.json")

    packets = json.loads(packets_path.read_text())
    expected_output = json.loads(expected_path.read_text()) if expected_path.exists() else None
    readme = readme_path.read_text() if readme_path.exists() else None

    return {
        "tier": tier,
        "name": scenario,
        "readme": readme,
        "packets": packets,
        "expected_output": expected_output,
    }
