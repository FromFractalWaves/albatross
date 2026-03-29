import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import WebSocket
from starlette.websockets import WebSocketState

from src.models.packets import ReadyPacket
from src.pipeline.loader import PacketLoader
from src.pipeline.queue import PacketQueue
from src.pipeline.router import TRMRouter

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@dataclass
class Run:
    run_id: str
    status: str  # pending | running | complete | error
    scenario_tier: str
    scenario_name: str
    speed_factor: float
    buffer_count: int = 5
    messages: list[dict] = field(default_factory=list)
    subscribers: list[WebSocket] = field(default_factory=list)
    router: TRMRouter | None = None


class RunManager:
    def __init__(self):
        self.runs: dict[str, Run] = {}

    def create_run(self, tier: str, scenario: str, speed_factor: float, buffer_count: int = 5) -> str:
        packets_path = DATA_DIR / tier / scenario / "packets.json"
        if not packets_path.exists():
            raise FileNotFoundError(f"Scenario not found: {tier}/{scenario}")

        run_id = uuid.uuid4().hex[:12]
        run = Run(
            run_id=run_id,
            status="pending",
            scenario_tier=tier,
            scenario_name=scenario,
            speed_factor=speed_factor,
            buffer_count=buffer_count,
        )
        self.runs[run_id] = run
        asyncio.create_task(self._execute_run(run, packets_path))
        return run_id

    async def _execute_run(self, run: Run, packets_path: Path) -> None:
        try:
            run.status = "running"
            queue = PacketQueue()
            loader = PacketLoader(packets_path, queue, speed_factor=run.speed_factor)
            router = TRMRouter(buffers=run.buffer_count)
            run.router = router

            await self._broadcast(run, {
                "type": "run_started",
                "run_id": run.run_id,
                "scenario": {"tier": run.scenario_tier, "name": run.scenario_name},
            })

            load_task = asyncio.create_task(loader.load())

            total = 0
            while True:
                packet = await queue.get()
                if packet is None:
                    queue.task_done()
                    break

                record = await router.route(packet)
                queue.task_done()
                total += 1

                context_snapshot = router.context.model_dump(mode="json")
                incoming = context_snapshot.pop("incoming_packet", None)

                await self._broadcast(run, {
                    "type": "packet_routed",
                    "packet_id": record.packet_id,
                    "routing_record": record.model_dump(mode="json"),
                    "context": context_snapshot,
                    "incoming_packet": incoming,
                })

            await load_task

            run.status = "complete"
            await self._broadcast(run, {
                "type": "run_complete",
                "run_id": run.run_id,
                "total_packets": total,
                "routing_records": [r.model_dump(mode="json") for r in router.routing_records],
            })

        except Exception as e:
            logger.exception(f"Run {run.run_id} failed")
            run.status = "error"
            await self._broadcast(run, {
                "type": "run_error",
                "run_id": run.run_id,
                "error": str(e),
            })

    async def _broadcast(self, run: Run, message: dict) -> None:
        run.messages.append(message)
        dead = []
        for ws in run.subscribers:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            run.subscribers.remove(ws)

    def subscribe(self, run_id: str, ws: WebSocket) -> Run:
        run = self.runs.get(run_id)
        if run is None:
            raise KeyError(f"Run not found: {run_id}")
        run.subscribers.append(ws)
        return run

    def unsubscribe(self, run_id: str, ws: WebSocket) -> None:
        run = self.runs.get(run_id)
        if run and ws in run.subscribers:
            run.subscribers.remove(ws)
