from enum import Enum
from pydantic import BaseModel, Field
from src.models.packets import ReadyPacket


class ThreadDecision(str, Enum):
    NEW = "new"
    EXISTING = "existing"
    BUFFER = "buffer"
    UNKNOWN = "unknown"


class EventDecision(str, Enum):
    NEW = "new"
    EXISTING = "existing"
    NONE = "none"
    UNKNOWN = "unknown"


class Thread(BaseModel):
    thread_id: str
    label: str
    packets: list[ReadyPacket] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    status: str = "open"


class Event(BaseModel):
    event_id: str
    label: str
    opened_at: str
    thread_ids: list[str] = Field(default_factory=list)
    status: str = "open"


class RoutingRecord(BaseModel):
    packet_id: str
    thread_decision: ThreadDecision
    thread_id: str | None = None
    event_decision: EventDecision
    event_id: str | None = None


class TRMContext(BaseModel):
    active_threads: list[Thread] = Field(default_factory=list)
    active_events: list[Event] = Field(default_factory=list)
    packets_to_resolve: list[ReadyPacket] = Field(default_factory=list)
    buffers_remaining: int = 5
    incoming_packet: ReadyPacket | None = None