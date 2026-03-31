import asyncio
from contracts.models import ReadyPacket


class PacketQueue:
    def __init__(self):
        self._queue: asyncio.Queue[ReadyPacket | None] = asyncio.Queue()

    async def put(self, packet: ReadyPacket) -> None:
        await self._queue.put(packet)

    async def get(self) -> ReadyPacket | None:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    async def join(self) -> None:
        await self._queue.join()

    def empty(self) -> bool:
        return self._queue.empty()