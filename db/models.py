from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    opened_at: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("transmissions.id", use_alter=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Transmission(Base):
    __tablename__ = "transmissions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)

    # Capture fields
    talkgroup_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_unit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    frequency: Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)
    encryption_status: Mapped[bool] = mapped_column(Boolean, nullable=False)
    audio_path: Mapped[str] = mapped_column(String, nullable=False)

    # Preprocessing fields
    text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    asr_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    asr_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    asr_passes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # TRM fields
    thread_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("threads.id"), nullable=True
    )
    event_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("events.id"), nullable=True
    )
    thread_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    event_decision: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ThreadEvent(Base):
    __tablename__ = "thread_events"

    thread_id: Mapped[str] = mapped_column(
        String, ForeignKey("threads.id"), primary_key=True
    )
    event_id: Mapped[str] = mapped_column(
        String, ForeignKey("events.id"), primary_key=True
    )


class RoutingRecord(Base):
    __tablename__ = "routing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    packet_id: Mapped[str] = mapped_column(
        String, ForeignKey("transmissions.id"), nullable=False
    )
    thread_decision: Mapped[str] = mapped_column(String, nullable=False)
    thread_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("threads.id"), nullable=True
    )
    event_decision: Mapped[str] = mapped_column(String, nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("events.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
