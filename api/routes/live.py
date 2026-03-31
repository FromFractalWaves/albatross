"""Live pipeline endpoints — hydrate UI from database state."""

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Event, Thread, ThreadEvent, Transmission
from db.session import get_session

router = APIRouter()


@router.get("/live/threads")
async def list_threads(session: AsyncSession = Depends(get_session)):
    # 1. All open threads
    result = await session.execute(
        select(Thread).where(Thread.status == "open")
    )
    threads = result.scalars().all()
    if not threads:
        return []

    thread_ids = [t.id for t in threads]

    # 2. All routed transmissions belonging to these threads (avoid N+1)
    result = await session.execute(
        select(Transmission)
        .where(Transmission.thread_id.in_(thread_ids))
        .where(Transmission.status == "routed")
        .order_by(Transmission.timestamp)
    )
    transmissions = result.scalars().all()

    packets_by_thread: dict[str, list] = defaultdict(list)
    for t in transmissions:
        packets_by_thread[t.thread_id].append({
            "id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else "",
            "text": t.text or "",
            "metadata": {
                "talkgroup_id": t.talkgroup_id,
                "source_unit": t.source_unit,
                "frequency": t.frequency,
                "duration": t.duration,
                "encryption_status": t.encryption_status,
            },
        })

    # 3. Thread-event associations
    result = await session.execute(
        select(ThreadEvent).where(ThreadEvent.thread_id.in_(thread_ids))
    )
    thread_events = result.scalars().all()

    event_ids_by_thread: dict[str, list[str]] = defaultdict(list)
    for te in thread_events:
        event_ids_by_thread[te.thread_id].append(te.event_id)

    return [
        {
            "thread_id": t.id,
            "label": t.label,
            "packets": packets_by_thread.get(t.id, []),
            "event_ids": event_ids_by_thread.get(t.id, []),
            "status": t.status,
        }
        for t in threads
    ]


@router.get("/live/events")
async def list_events(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Event).where(Event.status == "open")
    )
    events = result.scalars().all()
    if not events:
        return []

    event_ids = [e.id for e in events]

    # Thread associations
    result = await session.execute(
        select(ThreadEvent).where(ThreadEvent.event_id.in_(event_ids))
    )
    thread_events = result.scalars().all()

    thread_ids_by_event: dict[str, list[str]] = defaultdict(list)
    for te in thread_events:
        thread_ids_by_event[te.event_id].append(te.thread_id)

    return [
        {
            "event_id": e.id,
            "label": e.label,
            "opened_at": e.opened_at or "",
            "thread_ids": thread_ids_by_event.get(e.id, []),
            "status": e.status,
        }
        for e in events
    ]


@router.get("/live/transmissions")
async def list_transmissions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(Transmission)
        .where(Transmission.status == "routed")
        .order_by(Transmission.timestamp)
    )
    transmissions = result.scalars().all()

    return [
        {
            "id": t.id,
            "timestamp": t.timestamp.isoformat() if t.timestamp else "",
            "text": t.text or "",
            "status": t.status,
            "thread_id": t.thread_id,
            "event_id": t.event_id,
            "thread_decision": t.thread_decision,
            "event_decision": t.event_decision,
            "metadata": {
                "talkgroup_id": t.talkgroup_id,
                "source_unit": t.source_unit,
                "frequency": t.frequency,
                "duration": t.duration,
                "encryption_status": t.encryption_status,
            },
        }
        for t in transmissions
    ]
