from pydantic import BaseModel
from datetime import datetime
from typing import Any, Optional


class TransmissionPacket(BaseModel):
    """Output of the capture stage. Input to preprocessing."""
    id: str
    timestamp: str  # ISO8601 — capture doesn't need datetime arithmetic
    talkgroup_id: int
    source_unit: Optional[int] = None
    frequency: float
    duration: float
    encryption_status: bool
    audio_path: str
    metadata: dict[str, Any] = {}

    def to_orm(self):
        """Convert to SQLAlchemy Transmission model with status='captured'."""
        from datetime import datetime as dt
        from db.models import Transmission
        return Transmission(
            id=self.id,
            timestamp=dt.fromisoformat(self.timestamp.replace("Z", "+00:00")),
            talkgroup_id=self.talkgroup_id,
            source_unit=self.source_unit,
            frequency=self.frequency,
            duration=self.duration,
            encryption_status=self.encryption_status,
            audio_path=self.audio_path,
            status="captured",
            text=None,
        )


class ProcessedPacket(BaseModel):
    """Output of preprocessing. Input to the TRM. Domain-agnostic."""
    id: str
    timestamp: datetime
    text: str
    metadata: dict[str, Any] = {}


ReadyPacket = ProcessedPacket


class RoutingRecord(BaseModel):
    """Output of the TRM. One per packet."""
    packet_id: str
    thread_decision: str   # 'new' | 'existing' | 'buffer' | 'unknown'
    thread_id: Optional[str] = None
    event_decision: str    # 'new' | 'existing' | 'none' | 'unknown'
    event_id: Optional[str] = None

    def to_orm(self):
        """Convert to SQLAlchemy RoutingRecord model."""
        from db.models import RoutingRecord as ORMRoutingRecord
        return ORMRoutingRecord(
            packet_id=self.packet_id,
            thread_decision=self.thread_decision,
            thread_id=self.thread_id,
            event_decision=self.event_decision,
            event_id=self.event_id,
        )
