"""Mock pipeline API — start/stop/status for the three mock pipeline scripts."""

import asyncio
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, Request

from db.reset import reset as reset_db

logger = logging.getLogger("api.mock")

router = APIRouter(prefix="/mock", tags=["mock"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

SCRIPTS = [
    ["capture/mock/run.py"],
    ["preprocessing/mock/run.py"],
    ["trm/main_live.py"],
]


async def _stop_processes(processes: list[asyncio.subprocess.Process]) -> None:
    """Terminate all running processes and wait for them to exit."""
    for proc in processes:
        if proc.returncode is None:
            proc.terminate()
    for proc in processes:
        if proc.returncode is None:
            try:
                await asyncio.wait_for(proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                proc.kill()


@router.post("/start")
async def start_mock(request: Request):
    # Stop any existing processes
    existing = getattr(request.app.state, "mock_processes", [])
    if existing:
        await _stop_processes(existing)

    # Reset the database
    await reset_db()

    # Launch the three scripts
    processes: list[asyncio.subprocess.Process] = []
    for script_parts in SCRIPTS:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, *script_parts,
            cwd=str(PROJECT_ROOT),
        )
        processes.append(proc)

    request.app.state.mock_processes = processes
    return {"status": "started"}


@router.post("/stop")
async def stop_mock(request: Request):
    processes = getattr(request.app.state, "mock_processes", [])
    if processes:
        await _stop_processes(processes)
        request.app.state.mock_processes = []
    return {"status": "stopped"}


@router.get("/status")
async def mock_status(request: Request):
    processes = getattr(request.app.state, "mock_processes", [])
    if processes and any(p.returncode is None for p in processes):
        return {"status": "running"}
    return {"status": "stopped"}
