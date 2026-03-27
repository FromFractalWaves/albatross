import asyncio
import logging
from pathlib import Path

from src.pipeline.loader import PacketLoader
from src.pipeline.queue import PacketQueue

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def consume(queue: PacketQueue) -> None:
    while True:
        packet = await queue.get()
        if packet is None:
            logger.info("Stream exhausted — consumer done")
            queue.task_done()
            break
        logger.info(f"Router received: {packet.id} | speaker={packet.metadata.get('speaker')} | {packet.text[:60]}")
        queue.task_done()


async def main() -> None:
    packets_path = Path("data/tier_one/scenario_02_interleaved/packets.json")

    queue = PacketQueue()
    loader = PacketLoader(packets_path, queue)

    await asyncio.gather(
        loader.load(),
        consume(queue),
    )


if __name__ == "__main__":
    asyncio.run(main())