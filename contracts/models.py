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
