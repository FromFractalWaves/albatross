"""Live mock pipeline manager — in-process async pipeline with WebSocket broadcast."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from fastapi import WebSocket
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.websockets import WebSocketState

from contracts.models import ReadyPacket, RoutingRecord, TransmissionPacket
from db.models import Transmission
from db.persist import persist_routing_result
from db.reset import reset as reset_db
from trm.pipeline.queue import PacketQueue
from trm.pipeline.router import TRMRouter

logger = logging.getLogger("api.live_pipeline")

DATA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "data"
    / "tier_one"
    / "scenario_02_interleaved"
    / "packets_radio.json"
)

CAPTURE_INTERVAL = 10  # seconds between captured packets
ASR_DELAY = 3          # simulated ASR processing time


class LivePipelineManager:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._subscribers: list[WebSocket] = []
        self._messages: list[dict] = []

    @property
    def status(self) -> str:
        if self._task is not None and not self._task.done():
            return "running"
        return "stopped"

    async def start(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        # Stop any existing run
        if self._task is not None and not self._task.done():
            await self.stop()

        # Clear state from previous run
        self._messages.clear()

        # Reset the database
        await reset_db()

        self._task = asyncio.create_task(self._run_pipeline(session_factory))

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def subscribe(self, ws: WebSocket) -> None:
        self._subscribers.append(ws)

    def unsubscribe(self, ws: WebSocket) -> None:
        if ws in self._subscribers:
            self._subscribers.remove(ws)

    async def _broadcast(self, message: dict) -> None:
        self._messages.append(message)
        dead: list[WebSocket] = []
        for ws in self._subscribers:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._subscribers.remove(ws)

    async def _run_pipeline(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        try:
            raw = json.loads(DATA_PATH.read_text())
            total = len(raw)

            # Build text lookup for preprocessing stage
            text_lookup = {p["id"]: p["text"] for p in raw}

            await self._broadcast({
                "type": "pipeline_started",
                "total_packets": total,
            })

            capture_queue: PacketQueue = PacketQueue()
            routing_queue: PacketQueue = PacketQueue()
            router = TRMRouter(buffers=5)

            await asyncio.gather(
                self._capture_stage(raw, capture_queue, session_factory),
                self._preprocessing_stage(capture_queue, routing_queue, text_lookup, session_factory),
                self._routing_stage(routing_queue, router, session_factory),
            )

            await self._broadcast({
                "type": "pipeline_complete",
                "total_packets": total,
                "routing_records": [r.model_dump(mode="json") for r in router.routing_records],
            })

        except asyncio.CancelledError:
            logger.info("[PIPELINE] cancelled")
            raise
        except Exception as e:
            logger.exception("[PIPELINE] failed")
            await self._broadcast({
                "type": "pipeline_error",
                "error": str(e),
            })

    async def _capture_stage(
        self,
        raw: list[dict],
        capture_queue: PacketQueue,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        total = len(raw)
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

            async with session_factory() as session:
                async with session.begin():
                    session.add(orm_obj)

            now = datetime.now().strftime("%H:%M:%S")
            logger.info(f"[CAPTURE] {now} {tp.id} → captured ({i}/{total})")

            await self._broadcast({
                "type": "packet_captured",
                "packet_id": tp.id,
                "timestamp": tp.timestamp,
                "metadata": entry.get("metadata", {}),
            })

            # Pass entry data to preprocessing via queue
            await capture_queue.put(entry)

            if i < total:
                await asyncio.sleep(CAPTURE_INTERVAL)

        # Sentinel
        await capture_queue.put(None)
        logger.info(f"[CAPTURE] done — {total} packets written")

    async def _preprocessing_stage(
        self,
        capture_queue: PacketQueue,
        routing_queue: PacketQueue,
        text_lookup: dict[str, str],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        while True:
            entry = await capture_queue.get()
            if entry is None:
                capture_queue.task_done()
                break

            packet_id = entry["id"]

            # Mark as processing in DB
            async with session_factory() as session:
                result = await session.execute(
                    select(Transmission).where(Transmission.id == packet_id)
                )
                row = result.scalar_one()
                row.status = "processing"
                await session.commit()

            now = datetime.now().strftime("%H:%M:%S")
            logger.info(f"[PREPROCESS] {now} {packet_id} → processing...")

            # Simulate ASR delay
            await asyncio.sleep(ASR_DELAY)

            text = text_lookup.get(packet_id, "")

            # Write text + ASR metadata, flip to processed
            async with session_factory() as session:
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

                # Read fields for ReadyPacket
                timestamp = str(row.timestamp)
                talkgroup_id = row.talkgroup_id
                source_unit = row.source_unit
                frequency = row.frequency
                duration = row.duration

            now = datetime.now().strftime("%H:%M:%S")
            logger.info(f"[PREPROCESS] {now} {packet_id} → processed (text: {len(text)} chars)")

            await self._broadcast({
                "type": "packet_preprocessed",
                "packet_id": packet_id,
                "text": text,
            })

            ready = ReadyPacket(
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
            await routing_queue.put(ready)
            capture_queue.task_done()

        # Forward sentinel
        await routing_queue.put(None)
        logger.info("[PREPROCESS] done — all packets processed")

    async def _routing_stage(
        self,
        routing_queue: PacketQueue,
        router: TRMRouter,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        while True:
            packet = await routing_queue.get()
            if packet is None:
                routing_queue.task_done()
                break

            packet_id = packet.id

            # Mark as routing in DB
            async with session_factory() as session:
                result = await session.execute(
                    select(Transmission).where(Transmission.id == packet_id)
                )
                row = result.scalar_one()
                row.status = "routing"
                await session.commit()

            # Route
            record = await router.route(packet)

            # Persist
            async with session_factory() as session:
                await persist_routing_result(session, packet_id, record, router.context)

            logger.info(
                f"[TRM] {packet_id} → thread={record.thread_decision}:{record.thread_id} "
                f"event={record.event_decision}:{record.event_id}"
            )

            # Broadcast — same shape as RunManager's packet_routed
            context_snapshot = router.context.model_dump(mode="json")
            incoming = context_snapshot.pop("incoming_packet", None)

            await self._broadcast({
                "type": "packet_routed",
                "packet_id": record.packet_id,
                "routing_record": record.model_dump(mode="json"),
                "context": context_snapshot,
                "incoming_packet": incoming,
            })

            routing_queue.task_done()

        logger.info("[TRM] done — all packets routed")
