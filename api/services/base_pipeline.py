"""Abstract base class for pipeline managers — shared lifecycle, fanout, and stage metadata."""

import asyncio
from abc import ABC, abstractmethod

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocketState

from contracts.ws import PipelineStageDefinition


class BasePipelineManager(ABC):
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._subscribers: list[WebSocket] = []
        self._messages: list[dict] = []

    @property
    @abstractmethod
    def pipeline_stages(self) -> list[PipelineStageDefinition]:
        ...

    @abstractmethod
    async def _run_pipeline(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        ...

    @property
    def status(self) -> str:
        if self._task is not None and not self._task.done():
            return "running"
        return "stopped"

    async def start(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if self._task is not None and not self._task.done():
            await self.stop()

        self._messages.clear()
        await self._pre_run(session_factory)
        self._task = asyncio.create_task(self._run_pipeline(session_factory))

    async def _pre_run(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Hook called before spawning the pipeline task. Override for setup like DB resets."""
        pass

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def subscribe(self, ws: WebSocket) -> None:
        self._subscribers.append(ws)

    def unsubscribe(self, ws: WebSocket) -> None:
        if ws in self._subscribers:
            self._subscribers.remove(ws)

    async def _broadcast(self, message: dict) -> None:
        self._messages.append(message)
        dead: list[WebSocket] = []
        for ws in self._subscribers:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._subscribers.remove(ws)
