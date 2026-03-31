import asyncio
import logging
from pathlib import Path

from trm.pipeline.loader import PacketLoader
from trm.pipeline.queue import PacketQueue
from trm.pipeline.router import TRMRouter
from dotenv import load_dotenv
import os

load_dotenv()  # loads .env into environment

import anthropic
client = anthropic.Anthropic()  # auto-reads ANTHROPIC_API_KEY

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def consume(queue: PacketQueue, router: TRMRouter) -> None:
    while True:
        packet = await queue.get()
        if packet is None:
            logger.info("Stream exhausted — consumer done")
            queue.task_done()
            break
        await router.route(packet)
        queue.task_done()


async def main() -> None:
    packets_path = Path(__file__).parent.parent / "data/tier_one/scenario_02_interleaved/packets.json"

    queue = PacketQueue()
    loader = PacketLoader(packets_path, queue, speed_factor=20.0)
    router = TRMRouter(buffers=5)

    await asyncio.gather(
        loader.load(),
        consume(queue, router),
    )

    logger.info("--- Routing complete ---")
    for record in router.routing_records:
        logger.info(record.model_dump_json())


if __name__ == "__main__":
    asyncio.run(main())