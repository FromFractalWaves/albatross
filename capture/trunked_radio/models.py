from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4


@dataclass
class MetadataEvent:
    type: str
    tgid: int | None
    frequency: int | None
    source_unit: int | None
    lane_id: int | None
    timestamp: float


@dataclass
class LaneAssignment:
    lane_id: int
    tgid: int
    frequency: int | None
    source_unit: int | None


@dataclass
class ActiveCall:
    tgid: int
    lane_id: int
    frequency: int | None
    source_unit: int | None
    start_time: datetime
    last_pcm_at: float
    pcm_chunks: list[bytes] = field(default_factory=list)

    def total_pcm_bytes(self) -> int:
        return sum(len(c) for c in self.pcm_chunks)


@dataclass
class CompletedCall:
    tgid: int
    lane_id: int
    frequency: int | None
    source_unit: int | None
    start_time: datetime
    end_time: datetime
    end_reason: str
    audio_bytes: bytes
    call_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()
