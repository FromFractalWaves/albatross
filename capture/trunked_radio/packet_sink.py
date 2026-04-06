from pathlib import Path
from typing import Protocol

from contracts.models import TransmissionPacket


class PacketSink(Protocol):
    async def emit(self, packet: TransmissionPacket) -> None: ...
    async def close(self) -> None: ...


class ZmqPacketSink:
    """Pushes serialized packets over a ZMQ PUSH socket."""

    def __init__(self, port: int = 5590):
        import zmq
        import zmq.asyncio
        self._ctx = zmq.asyncio.Context()
        self._socket = self._ctx.socket(zmq.PUSH)
        self._socket.bind(f"tcp://*:{port}")

    async def emit(self, packet: TransmissionPacket) -> None:
        await self._socket.send_string(packet.model_dump_json())

    async def close(self) -> None:
        self._socket.close()
        self._ctx.term()


class StdoutPacketSink:
    """Prints serialized packets to stdout (debug sink)."""

    async def emit(self, packet: TransmissionPacket) -> None:
        print(packet.model_dump_json())

    async def close(self) -> None:
        pass


class JsonlPacketSink:
    """Appends serialized packets as JSON lines to a file (debug sink)."""

    def __init__(self, path: Path):
        self._path = path
        self._file = None

    async def emit(self, packet: TransmissionPacket) -> None:
        if self._file is None:
            self._file = open(self._path, "a")
        self._file.write(packet.model_dump_json() + "\n")
        self._file.flush()

    async def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
