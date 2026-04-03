"""Mock pipeline API — start/stop/status + live WebSocket."""

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from db.session import AsyncSessionLocal

logger = logging.getLogger("api.mock")

router = APIRouter(tags=["mock"])


@router.post("/api/mock/start")
async def start_mock(request: Request):
    manager = request.app.state.live_pipeline_manager
    await manager.start(AsyncSessionLocal)
    return {"status": "started"}


@router.post("/api/mock/stop")
async def stop_mock(request: Request):
    manager = request.app.state.live_pipeline_manager
    await manager.stop()
    return {"status": "stopped"}


@router.get("/api/mock/status")
async def mock_status(request: Request):
    manager = request.app.state.live_pipeline_manager
    return {
        "status": manager.status,
        "stages": [s.model_dump() for s in manager.pipeline_stages],
    }


@router.websocket("/ws/live/mock")
async def live_websocket(websocket: WebSocket):
    manager = websocket.app.state.live_pipeline_manager

    await websocket.accept()

    manager.subscribe(websocket)

    # Send backlog
    for message in list(manager._messages):
        await websocket.send_json(message)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.unsubscribe(websocket)
