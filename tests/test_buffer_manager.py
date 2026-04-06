import time

from capture.trunked_radio.buffer_manager import BufferManager
from capture.trunked_radio.models import MetadataEvent


def _grant_event(tgid: int, lane_id: int = 1, frequency: int | None = 851000000,
                 source_unit: int | None = 42, ts: float | None = None) -> MetadataEvent:
    return MetadataEvent(
        type="grant",
        tgid=tgid,
        frequency=frequency,
        source_unit=source_unit,
        lane_id=lane_id,
        timestamp=ts or time.time(),
    )


class TestBufferManager:
    def test_pcm_opens_new_call(self):
        bm = BufferManager()
        now = time.time()
        bm.handle_pcm(tgid=100, pcm_data=b"\x00" * 320, lane_id=1,
                       frequency=851000000, source_unit=42, timestamp=now)

        assert 100 in bm.active_calls
        assert bm.active_calls[100].tgid == 100
        assert len(bm.active_calls[100].pcm_chunks) == 1

    def test_pcm_appends_to_existing(self):
        bm = BufferManager()
        now = time.time()
        bm.handle_pcm(tgid=100, pcm_data=b"\x01" * 320, lane_id=1,
                       frequency=851000000, source_unit=42, timestamp=now)
        bm.handle_pcm(tgid=100, pcm_data=b"\x02" * 320, lane_id=1,
                       frequency=851000000, source_unit=42, timestamp=now + 0.04)

        assert len(bm.active_calls[100].pcm_chunks) == 2
        assert bm.active_calls[100].total_pcm_bytes() == 640

    def test_inactivity_timeout(self):
        bm = BufferManager()
        old = time.time() - 5.0
        bm.handle_pcm(tgid=100, pcm_data=b"\x00" * 320, lane_id=1,
                       frequency=851000000, source_unit=42, timestamp=old)

        closed = bm.sweep(time.time(), timeout=1.5)
        assert len(closed) == 1
        assert closed[0].tgid == 100
        assert closed[0].end_reason == "inactivity_timeout"
        assert 100 not in bm.active_calls

    def test_grant_opens_new_call(self):
        bm = BufferManager()
        event = _grant_event(tgid=200, lane_id=3)
        closed = bm.handle_metadata(event)

        assert closed == []
        assert 200 in bm.active_calls
        assert bm.active_calls[200].lane_id == 3

    def test_lane_reassignment(self):
        bm = BufferManager()
        now = time.time()
        # First call on lane 1
        bm.handle_pcm(tgid=100, pcm_data=b"\x00" * 160, lane_id=1,
                       frequency=851000000, source_unit=10, timestamp=now)

        # New grant assigns tgid 200 to same lane 1
        event = _grant_event(tgid=200, lane_id=1, ts=now + 1.0)
        closed = bm.handle_metadata(event)

        assert len(closed) == 1
        assert closed[0].tgid == 100
        assert closed[0].end_reason == "lane_reassigned"
        assert 100 not in bm.active_calls
        assert 200 in bm.active_calls

    def test_drain_returns_all(self):
        bm = BufferManager()
        now = time.time()
        bm.handle_pcm(tgid=100, pcm_data=b"\x00" * 160, lane_id=1,
                       frequency=None, source_unit=None, timestamp=now)
        bm.handle_pcm(tgid=200, pcm_data=b"\x00" * 160, lane_id=2,
                       frequency=None, source_unit=None, timestamp=now)

        closed = bm.drain()
        assert len(closed) == 2
        assert len(bm.active_calls) == 0

    def test_sweep_no_timeouts(self):
        bm = BufferManager()
        now = time.time()
        bm.handle_pcm(tgid=100, pcm_data=b"\x00" * 160, lane_id=1,
                       frequency=None, source_unit=None, timestamp=now)

        closed = bm.sweep(now + 0.1, timeout=1.5)
        assert closed == []
