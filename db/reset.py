"""DB reset — truncates all data tables in FK-safe order."""

import asyncio
import logging

from sqlalchemy import text

from db.session import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger("db.reset")

TABLES = [
    "routing_records",
    "thread_events",
    "transmissions",
    "threads",
    "events",
]


async def reset():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            for table in TABLES:
                await session.execute(text(f"DELETE FROM {table}"))
                logger.info(f"[RESET] cleared {table}")

    logger.info("[RESET] done — all tables empty")


if __name__ == "__main__":
    asyncio.run(reset())
