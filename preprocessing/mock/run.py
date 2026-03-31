"""Mock preprocessing script — polls for captured transmissions and simulates ASR."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from db.models import Transmission
from db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("preprocess")

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "tier_one" / "scenario_02_interleaved" / "packets_radio.json"
POLL_INTERVAL = 2   # seconds between polls
ASR_DELAY = 10      # simulated ASR processing time


async def main():
    # Build text lookup from source dataset
    raw = json.loads(DATA_PATH.read_text())
    text_lookup = {p["id"]: p["text"] for p in raw}

    logger.info(f"[PREPROCESS] ready — {len(text_lookup)} packets in lookup")

    idle_cycles = 0

    while True:
        async with AsyncSessionLocal() as session:
            # Pick up one captured row
            result = await session.execute(
                select(Transmission)
                .where(Transmission.status == "captured")
                .limit(1)
            )
            row = result.scalar_one_or_none()

            if row is None:
                # Check if any processing rows remain (our own in-flight work)
                result = await session.execute(
                    select(Transmission)
                    .where(Transmission.status == "processing")
                    .limit(1)
                )
                in_flight = result.scalar_one_or_none()

                if in_flight is None:
                    idle_cycles += 1
                    if idle_cycles >= 3:
                        break
                else:
                    idle_cycles = 0

                await asyncio.sleep(POLL_INTERVAL)
                continue

            idle_cycles = 0

            # Flip to processing immediately to prevent double-pickup
            row.status = "processing"
            await session.commit()

            packet_id = row.id

        now = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[PREPROCESS] {now} {packet_id} → processing...")

        # Simulate ASR delay
        await asyncio.sleep(ASR_DELAY)

        # Write text and ASR metadata
        text = text_lookup.get(packet_id, "")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transmission).where(Transmission.id == packet_id)
            )
            row = result.scalar_one()
            row.text = text
            row.asr_model = "mock"
            row.asr_confidence = 1.0
            row.asr_passes = 1
            row.status = "processed"
            await session.commit()

        now = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[PREPROCESS] {now} {packet_id} → processed (text: {len(text)} chars)")

    logger.info("[PREPROCESS] done — all packets processed")


if __name__ == "__main__":
    asyncio.run(main())
