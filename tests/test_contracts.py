"""Tests for the contracts layer (Phase 3.2).

Validates that boundary types are importable and behave correctly.
"""

import json
from pathlib import Path

from contracts.models import (
    TransmissionPacket,
    ProcessedPacket,
    ReadyPacket,
    RoutingRecord,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def test_all_boundary_types_importable():
    """All four boundary types are importable from contracts.models."""
    assert TransmissionPacket is not None
    assert ProcessedPacket is not None
    assert ReadyPacket is not None
    assert RoutingRecord is not None


def test_ready_packet_is_alias():
    """ReadyPacket is a type alias for ProcessedPacket, not a subclass."""
    assert ReadyPacket is ProcessedPacket


def test_transmission_packet_from_radio_dataset():
    """TransmissionPacket can be constructed from packets_radio.json data."""
    path = DATA_DIR / "tier_one" / "scenario_02_interleaved" / "packets_radio.json"
    data = json.loads(path.read_text())

    packet = TransmissionPacket(
        id=data[0]["id"],
        timestamp=data[0]["timestamp"],
        talkgroup_id=data[0]["metadata"]["talkgroup_id"],
        source_unit=data[0]["metadata"]["source_unit"],
        frequency=data[0]["metadata"]["frequency"],
        duration=data[0]["metadata"]["duration"],
        encryption_status=data[0]["metadata"]["encryption_status"],
        audio_path=data[0]["metadata"]["audio_path"],
    )

    assert packet.id == data[0]["id"]
    assert packet.talkgroup_id == data[0]["metadata"]["talkgroup_id"]
    assert packet.source_unit == data[0]["metadata"]["source_unit"]
    assert packet.frequency == data[0]["metadata"]["frequency"]
    assert packet.encryption_status == data[0]["metadata"]["encryption_status"]


def test_routing_record_string_decisions():
    """RoutingRecord uses plain strings for decision fields."""
    record = RoutingRecord(
        packet_id="pkt_001",
        thread_decision="new",
        thread_id="thread_A",
        event_decision="none",
        event_id=None,
    )

    dumped = record.model_dump()
    assert dumped["thread_decision"] == "new"
    assert dumped["event_decision"] == "none"
    assert dumped["thread_id"] == "thread_A"
    assert dumped["event_id"] is None


def test_processed_packet_datetime_parsing():
    """ProcessedPacket parses ISO8601 string timestamps into datetime objects."""
    packet = ProcessedPacket(
        id="pkt_001",
        timestamp="2024-01-15T14:00:00Z",
        text="Hello world",
    )

    from datetime import datetime, timezone
    assert isinstance(packet.timestamp, datetime)
    assert packet.timestamp.tzinfo is not None
