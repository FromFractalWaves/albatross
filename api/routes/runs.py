from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

router = APIRouter()


class CreateRunRequest(BaseModel):
    source: str = "scenario"
    tier: str
    scenario: str
    speed_factor: float = 20.0


@router.post("/api/runs")
async def create_run(body: CreateRunRequest, request: Request):
    run_manager = request.app.state.run_manager
    try:
        run_id = run_manager.create_run(body.tier, body.scenario, body.speed_factor)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"run_id": run_id}


@router.websocket("/ws/runs/{run_id}")
async def run_websocket(websocket: WebSocket, run_id: str):
    run_manager = websocket.app.state.run_manager

    await websocket.accept()

    if run_id not in run_manager.runs:
        await websocket.close(code=4004, reason="Run not found")
        return

    run = run_manager.subscribe(run_id, websocket)

    # Send backlog
    for message in list(run.messages):
        await websocket.send_json(message)

    try:
        # Keep connection alive until client disconnects or run ends
        while True:
            # Wait for client messages (ping/pong or close)
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        run_manager.unsubscribe(run_id, websocket)
