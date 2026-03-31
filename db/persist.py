"""Atomic persistence for TRM routing results."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contracts.models import RoutingRecord
from db.models import (
    Event as ORMEvent,
    Thread as ORMThread,
    ThreadEvent as ORMThreadEvent,
    Transmission,
)
from src.models.router import TRMContext

logger = logging.getLogger(__name__)


async def persist_routing_result(
    session: AsyncSession,
    packet_id: str,
    record: RoutingRecord,
    context: TRMContext,
) -> None:
    """Write a single routing result to the database atomically.

    Insertion order within the transaction matters due to FK constraints:
    1. Upsert thread (must exist before transmissions.thread_id references it)
    2. Upsert event (must exist before transmissions.event_id references it)
    3. Upsert thread_events join
    4. Write routing record
    5. Update transmission with routing fields and status='routed'
    """
    async with session.begin():
        # 1. Upsert thread
        if record.thread_decision in ("new", "existing") and record.thread_id:
            ctx_thread = _get_thread_from_context(context, record.thread_id)
            if ctx_thread:
                orm_thread = ORMThread(
                    id=ctx_thread.thread_id,
                    label=ctx_thread.label,
                    status=ctx_thread.status,
                )
                await session.merge(orm_thread)

        # 2. Upsert event
        if record.event_decision in ("new", "existing") and record.event_id:
            ctx_event = _get_event_from_context(context, record.event_id)
            if ctx_event:
                orm_event = ORMEvent(
                    id=ctx_event.event_id,
                    label=ctx_event.label,
                    status=ctx_event.status,
                    opened_at=ctx_event.opened_at,
                )
                await session.merge(orm_event)

        # 3. Upsert thread_events join
        if record.thread_id and record.event_id:
            existing = await session.execute(
                select(ORMThreadEvent).where(
                    ORMThreadEvent.thread_id == record.thread_id,
                    ORMThreadEvent.event_id == record.event_id,
                )
            )
            if existing.scalar_one_or_none() is None:
                session.add(ORMThreadEvent(
                    thread_id=record.thread_id,
                    event_id=record.event_id,
                ))

        # 4. Write routing record
        session.add(record.to_orm())

        # 5. Update transmission
        result = await session.execute(
            select(Transmission).where(Transmission.id == packet_id)
        )
        transmission = result.scalar_one()
        transmission.thread_id = record.thread_id
        transmission.event_id = record.event_id
        transmission.thread_decision = record.thread_decision
        transmission.event_decision = record.event_decision
        transmission.status = "routed"


def _get_thread_from_context(context: TRMContext, thread_id: str):
    return next(
        (t for t in context.active_threads if t.thread_id == thread_id), None
    )


def _get_event_from_context(context: TRMContext, event_id: str):
    return next(
        (e for e in context.active_events if e.event_id == event_id), None
    )
