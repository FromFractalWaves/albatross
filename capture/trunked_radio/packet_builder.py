from pathlib import Path
from uuid import uuid4

from contracts.models import TransmissionPacket
from .models import CompletedCall


def build_packet(call: CompletedCall, wav_path: Path) -> TransmissionPacket:
    """Convert a CompletedCall + WAV path into a TransmissionPacket."""
    return TransmissionPacket(
        id=str(uuid4()),
        timestamp=call.start_time.isoformat(),
        talkgroup_id=call.tgid,
        source_unit=call.source_unit,
        frequency=float(call.frequency) if call.frequency is not None else 0.0,
        duration=call.duration_seconds,
        encryption_status=False,
        audio_path=str(wav_path),
        metadata={
            "system": "p25_phase1",
            "lane_id": call.lane_id,
            "end_reason": call.end_reason,
            "sample_rate": 8000,
        },
    )
