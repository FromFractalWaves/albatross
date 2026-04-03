"""WebSocket message types for the live mock pipeline."""

from typing import Any, Literal, Optional

from pydantic import BaseModel


class PipelineStageDefinition(BaseModel):
    id: str
    label: str
    message_type: str


class PipelineStarted(BaseModel):
    type: Literal["pipeline_started"] = "pipeline_started"
    stages: list[PipelineStageDefinition] = []


class PacketCaptured(BaseModel):
    type: Literal["packet_captured"] = "packet_captured"
    packet_id: str
    timestamp: str
    metadata: dict[str, Any] = {}


class PacketPreprocessed(BaseModel):
    type: Literal["packet_preprocessed"] = "packet_preprocessed"
    packet_id: str
    text: str


class PacketRouted(BaseModel):
    type: Literal["packet_routed"] = "packet_routed"
    packet_id: str
    routing_record: dict[str, Any]
    context: dict[str, Any]
    incoming_packet: Optional[dict[str, Any]] = None


class PipelineComplete(BaseModel):
    type: Literal["pipeline_complete"] = "pipeline_complete"
    total_packets: int
    routing_records: list[dict[str, Any]]


class PipelineError(BaseModel):
    type: Literal["pipeline_error"] = "pipeline_error"
    error: str
