import wave
from pathlib import Path

from .models import CompletedCall


class WavWriter:
    """Writes CompletedCall audio to mono int16 WAV files at 8000 Hz."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, call: CompletedCall) -> Path:
        source = call.source_unit if call.source_unit is not None else "unknown"
        filename = (
            f"{call.start_time.strftime('%Y%m%dT%H%M%S')}"
            f"_{call.tgid}_{source}_{call.call_id}.wav"
        )
        path = self.output_dir / filename

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(call.audio_bytes)

        return path.resolve()
