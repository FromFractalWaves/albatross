import json
import logging
from pathlib import Path

from src.models.packets import ReadyPacket
from src.pipeline.queue import PacketQueue

logger = logging.getLogger(__name__)


class PacketLoader:
    def __init__(self, packets_path: Path, queue: PacketQueue):
        self.packets_path = packets_path
        self.queue = queue

    async def load(self) -> None:
        logger.info(f"Loading packets from {self.packets_path}")

        raw = self.packets_path.read_text()
        data = json.loads(raw)

        for entry in data:
            packet = ReadyPacket(**entry)
            await self.queue.put(packet)
            logger.debug(f"Queued {packet.id}")

        # Sentinel — signals to the router that the stream is done
        await self.queue.put(None)
        logger.info(f"Loaded {len(data)} packets")