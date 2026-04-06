import wave
from datetime import datetime, timezone

from capture.trunked_radio.models import CompletedCall
from capture.trunked_radio.wav_writer import WavWriter


def _make_call(tgid: int = 100, audio: bytes = b"\x00\x01" * 800,
               source_unit: int | None = 42) -> CompletedCall:
    now = datetime.now(tz=timezone.utc)
    return CompletedCall(
        tgid=tgid,
        lane_id=1,
        frequency=851000000,
        source_unit=source_unit,
        start_time=now,
        end_time=now,
        end_reason="inactivity_timeout",
        audio_bytes=audio,
    )


class TestWavWriter:
    def test_wav_format(self, tmp_path):
        writer = WavWriter(tmp_path / "wav")
        call = _make_call(audio=b"\x00\x01" * 4000)
        path = writer.write(call)

        with wave.open(str(path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 8000
            # 8000 bytes of audio / 2 bytes per sample = 4000 frames
            assert wf.getnframes() == 4000

    def test_filename_contains_tgid_and_timestamp(self, tmp_path):
        writer = WavWriter(tmp_path / "wav")
        call = _make_call(tgid=555)
        path = writer.write(call)

        assert "555" in path.name
        assert call.start_time.strftime("%Y%m%dT%H%M%S") in path.name

    def test_creates_output_directory(self, tmp_path):
        out = tmp_path / "nested" / "dir"
        assert not out.exists()

        writer = WavWriter(out)
        assert out.exists()

    def test_source_unit_none(self, tmp_path):
        writer = WavWriter(tmp_path / "wav")
        call = _make_call(source_unit=None)
        path = writer.write(call)
        assert "unknown" in path.name
