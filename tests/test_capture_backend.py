import pytest
import pytest_asyncio
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from capture.trunked_radio.backend import CaptureBackend
from capture.trunked_radio.models import CompletedCall
from contracts.models import TransmissionPacket
from db.base import Base
import db.models as orm_models


class RecordingSink:
    """Test sink that records emitted packets."""

    def __init__(self):
        self.packets: list[TransmissionPacket] = []

    async def emit(self, packet: TransmissionPacket) -> None:
        self.packets.append(packet)

    async def close(self) -> None:
        pass


def _make_call(audio: bytes = b"\x00\x01" * 800) -> CompletedCall:
    return CompletedCall(
        tgid=100,
        lane_id=1,
        frequency=851000000,
        source_unit=42,
        start_time=datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 6, 12, 0, 5, tzinfo=timezone.utc),
        end_reason="inactivity_timeout",
        audio_bytes=audio,
    )


@pytest_asyncio.fixture
async def test_db():
    """In-memory SQLite for capture backend tests."""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_finalize_calls_writes_wav_and_db(tmp_path, test_db, monkeypatch):
    """End-to-end: _finalize_calls produces a WAV file, a DB row, and a sink packet."""
    engine, factory = test_db

    # Patch AsyncSessionLocal to use our test DB
    monkeypatch.setattr(
        "capture.trunked_radio.backend.AsyncSessionLocal",
        factory,
    )

    sink = RecordingSink()
    backend = CaptureBackend(sink=sink)
    backend.wav_writer.output_dir = tmp_path

    call = _make_call()
    await backend._finalize_calls([call])

    # WAV file exists
    wav_files = list(tmp_path.glob("*.wav"))
    assert len(wav_files) == 1
    assert "100" in wav_files[0].name

    # DB row exists with correct fields
    async with factory() as session:
        result = await session.execute(
            select(orm_models.Transmission).where(
                orm_models.Transmission.talkgroup_id == 100
            )
        )
        row = result.scalar_one()
        assert row.status == "captured"
        assert row.talkgroup_id == 100
        assert row.source_unit == 42
        assert row.frequency == 851000000.0
        assert row.duration == 5.0
        assert row.text is None

    # Sink received the packet
    assert len(sink.packets) == 1
    assert sink.packets[0].talkgroup_id == 100
    assert sink.packets[0].metadata["system"] == "p25_phase1"


@pytest.mark.asyncio
async def test_finalize_multiple_calls(tmp_path, test_db, monkeypatch):
    """Multiple calls produce multiple WAV files and DB rows."""
    engine, factory = test_db
    monkeypatch.setattr(
        "capture.trunked_radio.backend.AsyncSessionLocal",
        factory,
    )

    sink = RecordingSink()
    backend = CaptureBackend(sink=sink)
    backend.wav_writer.output_dir = tmp_path

    calls = [
        CompletedCall(
            tgid=tgid, lane_id=1, frequency=851000000, source_unit=None,
            start_time=datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 4, 6, 12, 0, 3, tzinfo=timezone.utc),
            end_reason="inactivity_timeout", audio_bytes=b"\x00" * 320,
        )
        for tgid in (100, 200, 300)
    ]

    await backend._finalize_calls(calls)

    assert len(list(tmp_path.glob("*.wav"))) == 3
    assert len(sink.packets) == 3

    async with factory() as session:
        result = await session.execute(select(orm_models.Transmission))
        rows = result.scalars().all()
        assert len(rows) == 3
