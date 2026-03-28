import json
import asyncio
import logging
from pathlib import Path

from src.models.packets import ReadyPacket
from src.pipeline.queue import PacketQueue

logger = logging.getLogger(__name__)


class PacketLoader:
    def __init__(self, packets_path: Path, queue: PacketQueue, speed_factor: float = 1.0):
        self.packets_path = packets_path
        self.queue = queue
        self.speed_factor = speed_factor

    async def load(self) -> None:
        logger.info(f"Loading packets from {self.packets_path} at {self.speed_factor}x speed")

        raw = self.packets_path.read_text()
        data = json.loads(raw)

        prev_timestamp = None

        for entry in data:
            packet = ReadyPacket(**entry)

            if prev_timestamp is not None:
                delta = (packet.timestamp - prev_timestamp).total_seconds()
                delay = delta / self.speed_factor
                logger.debug(f"Waiting {delay:.2f}s before {packet.id} (real gap: {delta:.0f}s)")
                await asyncio.sleep(delay)

            await self.queue.put(packet)
            logger.debug(f"Queued {packet.id}")
            prev_timestamp = packet.timestamp

        await self.queue.put(None)
        logger.info(f"Loaded {len(data)} packets")