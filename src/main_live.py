"""DB-driven TRM entry point — polls for processed transmissions and routes them."""

import asyncio
import logging

from dotenv import load_dotenv
from sqlalchemy import select

from contracts.models import ReadyPacket
from db.models import Transmission
from db.persist import persist_routing_result
from db.session import AsyncSessionLocal
from src.pipeline.router import TRMRouter

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("trm_live")

POLL_INTERVAL = 2   # seconds between polls
MAX_IDLE = 10        # exit after ~20 seconds of nothing


async def main():
    router = TRMRouter(buffers=5)
    idle_cycles = 0

    logger.info("[TRM] live runner started — polling for processed packets")

    while True:
        # Fetch next processed packet
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transmission)
                .where(Transmission.status == "processed")
                .order_by(Transmission.timestamp)
                .limit(1)
            )
            row = result.scalar_one_or_none()

            if row is None:
                idle_cycles += 1
                if idle_cycles >= MAX_IDLE:
                    logger.info("[TRM] no more packets — exiting")
                    break
                await asyncio.sleep(POLL_INTERVAL)
                continue

            idle_cycles = 0

            # Flip to routing
            row.status = "routing"
            packet_id = row.id
            timestamp = str(row.timestamp)
            text = row.text
            talkgroup_id = row.talkgroup_id
            source_unit = row.source_unit
            frequency = row.frequency
            duration = row.duration
            await session.commit()

        # Build ReadyPacket from DB fields
        ready_packet = ReadyPacket(
            id=packet_id,
            timestamp=timestamp,
            text=text,
            metadata={
                "talkgroup_id": talkgroup_id,
                "source_unit": source_unit,
                "frequency": frequency,
                "duration": duration,
            },
        )

        # Route
        record = await router.route(ready_packet)

        # Persist
        async with AsyncSessionLocal() as session:
            await persist_routing_result(session, packet_id, record, router.context)

        logger.info(
            f"[TRM] {packet_id} → thread={record.thread_decision}:{record.thread_id} "
            f"event={record.event_decision}:{record.event_id}"
        )

    logger.info("[TRM] done — all packets routed")


if __name__ == "__main__":
    asyncio.run(main())
