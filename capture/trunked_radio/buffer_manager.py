from datetime import datetime, timezone
from uuid import uuid4

from .models import ActiveCall, CompletedCall, MetadataEvent


GRANT_EVENT_TYPES = {"grant", "grant_update"}
RELEASE_EVENT_TYPES: set[str] = set()


class BufferManager:
    """Call state machine — tracks active calls by tgid, accumulates PCM."""

    def __init__(self):
        self.active_calls: dict[int, ActiveCall] = {}

    def handle_metadata(self, event: MetadataEvent) -> list[CompletedCall]:
        if event.type in GRANT_EVENT_TYPES:
            return self._grant_or_update(event)
        return []

    def _grant_or_update(self, event: MetadataEvent) -> list[CompletedCall]:
        closed: list[CompletedCall] = []

        # If this lane is occupied by a different tgid, close the prior call
        if event.lane_id is not None:
            for tgid, call in list(self.active_calls.items()):
                if call.lane_id == event.lane_id and tgid != event.tgid:
                    closed.append(self._close_call(tgid, "lane_reassigned"))
                    break

        if event.tgid is None:
            return closed

        if event.tgid in self.active_calls:
            # Update existing call metadata
            call = self.active_calls[event.tgid]
            if event.frequency is not None:
                call.frequency = event.frequency
            if event.source_unit is not None:
                call.source_unit = event.source_unit
            if event.lane_id is not None:
                call.lane_id = event.lane_id
        else:
            # Open new call
            self.active_calls[event.tgid] = ActiveCall(
                tgid=event.tgid,
                lane_id=event.lane_id or 0,
                frequency=event.frequency,
                source_unit=event.source_unit,
                start_time=datetime.fromtimestamp(event.timestamp, tz=timezone.utc),
                last_pcm_at=event.timestamp,
            )

        return closed

    def handle_pcm(
        self,
        tgid: int,
        pcm_data: bytes,
        lane_id: int,
        frequency: int | None,
        source_unit: int | None,
        timestamp: float,
    ) -> None:
        if tgid in self.active_calls:
            call = self.active_calls[tgid]
            call.pcm_chunks.append(pcm_data)
            call.last_pcm_at = timestamp
        else:
            call = ActiveCall(
                tgid=tgid,
                lane_id=lane_id,
                frequency=frequency,
                source_unit=source_unit,
                start_time=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                last_pcm_at=timestamp,
                pcm_chunks=[pcm_data],
            )
            self.active_calls[tgid] = call

    def sweep(self, now: float, timeout: float) -> list[CompletedCall]:
        closed: list[CompletedCall] = []
        for tgid in list(self.active_calls):
            if now - self.active_calls[tgid].last_pcm_at > timeout:
                closed.append(self._close_call(tgid, "inactivity_timeout"))
        return closed

    def drain(self) -> list[CompletedCall]:
        closed: list[CompletedCall] = []
        for tgid in list(self.active_calls):
            closed.append(self._close_call(tgid, "inactivity_timeout"))
        return closed

    def _close_call(self, tgid: int, reason: str) -> CompletedCall:
        call = self.active_calls.pop(tgid)
        now = datetime.now(tz=timezone.utc)
        return CompletedCall(
            tgid=call.tgid,
            lane_id=call.lane_id,
            frequency=call.frequency,
            source_unit=call.source_unit,
            start_time=call.start_time,
            end_time=now,
            end_reason=reason,
            audio_bytes=b"".join(call.pcm_chunks),
            call_id=str(uuid4()),
        )
