from datetime import datetime, timezone
from pathlib import Path

from capture.trunked_radio.models import CompletedCall
from capture.trunked_radio.packet_builder import build_packet


def _make_call(**overrides) -> CompletedCall:
    defaults = dict(
        tgid=100,
        lane_id=1,
        frequency=851000000,
        source_unit=42,
        start_time=datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 4, 6, 12, 0, 5, tzinfo=timezone.utc),
        end_reason="inactivity_timeout",
        audio_bytes=b"\x00" * 1600,
    )
    defaults.update(overrides)
    return CompletedCall(**defaults)


class TestPacketBuilder:
    def test_field_mapping(self):
        call = _make_call()
        wav_path = Path("/tmp/test.wav")
        packet = build_packet(call, wav_path)

        assert packet.talkgroup_id == 100
        assert packet.source_unit == 42
        assert packet.frequency == 851000000.0
        assert packet.duration == 5.0
        assert packet.encryption_status is False
        assert packet.audio_path == "/tmp/test.wav"
        assert packet.timestamp == call.start_time.isoformat()

    def test_metadata_dict(self):
        call = _make_call()
        packet = build_packet(call, Path("/tmp/test.wav"))

        assert packet.metadata["system"] == "p25_phase1"
        assert packet.metadata["lane_id"] == 1
        assert packet.metadata["end_reason"] == "inactivity_timeout"
        assert packet.metadata["sample_rate"] == 8000

    def test_to_orm_output(self):
        call = _make_call()
        packet = build_packet(call, Path("/tmp/test.wav"))
        orm = packet.to_orm()

        assert orm.status == "captured"
        assert orm.text is None
        assert orm.talkgroup_id == 100

    def test_source_unit_none(self):
        call = _make_call(source_unit=None)
        packet = build_packet(call, Path("/tmp/test.wav"))

        assert packet.source_unit is None
        orm = packet.to_orm()
        assert orm.source_unit is None

    def test_frequency_none_defaults_to_zero(self):
        call = _make_call(frequency=None)
        packet = build_packet(call, Path("/tmp/test.wav"))
        assert packet.frequency == 0.0
