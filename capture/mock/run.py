"""Mock capture script — reads packets_radio.json and writes to DB as captured transmissions."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from contracts.models import TransmissionPacket
from db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("capture")

DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "tier_one" / "scenario_02_interleaved" / "packets_radio.json"
CAPTURE_INTERVAL = 10  # seconds between packets


async def main():
    raw = json.loads(DATA_PATH.read_text())
    total = len(raw)

    logger.info(f"[CAPTURE] loading {total} packets from {DATA_PATH.name}")

    for i, entry in enumerate(raw, 1):
        tp = TransmissionPacket(
            id=entry["id"],
            timestamp=entry["timestamp"],
            talkgroup_id=entry["metadata"]["talkgroup_id"],
            source_unit=entry["metadata"]["source_unit"],
            frequency=entry["metadata"]["frequency"],
            duration=entry["metadata"]["duration"],
            encryption_status=entry["metadata"]["encryption_status"],
            audio_path=entry["metadata"]["audio_path"],
        )

        orm_obj = tp.to_orm()

        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(orm_obj)

        now = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[CAPTURE] {now} {tp.id} → captured ({i}/{total})")

        if i < total:
            await asyncio.sleep(CAPTURE_INTERVAL)

    logger.info(f"[CAPTURE] done — {total} packets written")


if __name__ == "__main__":
    asyncio.run(main())
