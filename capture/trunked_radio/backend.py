import asyncio
import json
import logging
import time

import zmq
import zmq.asyncio

from capture.trunked_radio import config
from capture.trunked_radio.buffer_manager import BufferManager
from capture.trunked_radio.models import CompletedCall, MetadataEvent
from capture.trunked_radio.packet_builder import build_packet
from capture.trunked_radio.packet_sink import PacketSink, StdoutPacketSink
from capture.trunked_radio.wav_writer import WavWriter
from db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


class CaptureBackend:
    """Backend event loop — pulls PCM + metadata from ZMQ, writes WAV + DB."""

    def __init__(self, sink: PacketSink | None = None):
        self.buffer_manager = BufferManager()
        self.wav_writer = WavWriter(config.CAPTURE_WAV_DIR)
        self.sink: PacketSink = sink or StdoutPacketSink()

    async def run(self):
        ctx = zmq.asyncio.Context()
        pcm_socket = ctx.socket(zmq.PULL)
        pcm_socket.bind(f"tcp://*:{config.PCM_PORT}")

        control_socket = ctx.socket(zmq.PULL)
        control_socket.bind(f"tcp://*:{config.CONTROL_PORT}")

        poller = zmq.asyncio.Poller()
        poller.register(pcm_socket, zmq.POLLIN)
        poller.register(control_socket, zmq.POLLIN)

        last_sweep = time.time()
        logger.info(
            "CaptureBackend started — PCM:%d Control:%d",
            config.PCM_PORT,
            config.CONTROL_PORT,
        )

        try:
            while True:
                events = dict(await poller.poll(timeout=config.POLL_TIMEOUT))

                if pcm_socket in events:
                    # Drain all pending PCM before processing metadata
                    # so split-triggering grants don't discard buffered audio
                    while True:
                        frames = await pcm_socket.recv_multipart()
                        await self._handle_pcm(frames)
                        if not await pcm_socket.poll(0):
                            break

                if control_socket in events:
                    data = await control_socket.recv()
                    await self._handle_metadata(data)

                now = time.time()
                if now - last_sweep >= config.SWEEP_INTERVAL:
                    await self._sweep_timeouts()
                    last_sweep = now

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Shutting down — draining active calls")
            await self._drain_and_finalize()
        finally:
            pcm_socket.close()
            control_socket.close()
            ctx.term()
            await self.sink.close()

    async def _handle_pcm(self, frames: list) -> None:
        header = json.loads(frames[0])
        pcm_data = frames[1]
        self.buffer_manager.handle_pcm(
            tgid=header["tgid"],
            pcm_data=pcm_data,
            lane_id=header["lane_id"],
            frequency=header.get("freq"),
            source_unit=header.get("source_unit"),
            timestamp=header["ts"],
        )

    async def _handle_metadata(self, data: bytes) -> None:
        raw = json.loads(data)
        event = MetadataEvent(
            type=raw["type"],
            tgid=raw.get("tgid"),
            frequency=raw.get("frequency"),
            source_unit=raw.get("source_unit"),
            lane_id=raw.get("lane_id"),
            timestamp=raw.get("timestamp", time.time()),
        )
        closed = self.buffer_manager.handle_metadata(event)
        if closed:
            await self._finalize_calls(closed)

    async def _sweep_timeouts(self) -> None:
        closed = self.buffer_manager.sweep(time.time(), config.INACTIVITY_TIMEOUT)
        if closed:
            await self._finalize_calls(closed)

    async def _drain_and_finalize(self) -> None:
        closed = self.buffer_manager.drain()
        if closed:
            await self._finalize_calls(closed)

    async def _finalize_calls(self, calls: list[CompletedCall]) -> None:
        for call in calls:
            if not call.audio_bytes:
                logger.debug(
                    "Skipping empty call tgid=%d lane=%d reason=%s",
                    call.tgid, call.lane_id, call.end_reason,
                )
                continue
            try:
                wav_path = self.wav_writer.write(call)
                packet = build_packet(call, wav_path)
                orm_obj = packet.to_orm()

                async with AsyncSessionLocal() as session:
                    async with session.begin():
                        session.add(orm_obj)

                await self.sink.emit(packet)
                logger.info(
                    "Finalized tgid=%d lane=%d duration=%.1fs reason=%s",
                    call.tgid,
                    call.lane_id,
                    call.duration_seconds,
                    call.end_reason,
                )
            except Exception:
                logger.exception(
                    "Failed to finalize tgid=%d lane=%d — skipping",
                    call.tgid,
                    call.lane_id,
                )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(CaptureBackend().run())
