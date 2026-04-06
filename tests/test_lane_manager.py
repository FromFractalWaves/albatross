import time

from capture.trunked_radio.lane_manager import LaneManager


class TestLaneManagerGrants:
    def test_grant_assigns_lane(self):
        lm = LaneManager()
        lane_id = lm.on_grant(6005, 856012500, 100)

        assert lane_id is not None
        assert 0 <= lane_id < 8

    def test_existing_tgid_returns_same_lane(self):
        lm = LaneManager()
        lane_a = lm.on_grant(6005, 856012500, 100)
        lane_b = lm.on_grant(6005, 856012500, 100)

        assert lane_a == lane_b

    def test_freq_change_triggers_retune(self):
        retune_calls = []
        lm = LaneManager(retune_callback=lambda lid, f: retune_calls.append((lid, f)))

        lane_id = lm.on_grant(6005, 856012500, 100)
        lm.on_grant(6005, 856312500, 100)

        assert (lane_id, 856312500) in retune_calls

    def test_same_freq_preempts(self):
        lm = LaneManager()
        lane_a = lm.on_grant(6005, 856012500, 100)
        lane_b = lm.on_grant(6038, 856012500, 200)

        assert lane_b == lane_a
        # Old tgid is evicted
        assert 6005 not in lm._tgid_to_lane
        assert lm._tgid_to_lane[6038] == lane_b

    def test_pool_exhaustion(self):
        lm = LaneManager(num_lanes=8)
        for i in range(8):
            assert lm.on_grant(6000 + i, 856000000 + i * 25000, i) is not None

        assert lm.on_grant(9999, 857000000, 999) is None


class TestLaneManagerSweep:
    def test_sweep_stale_releases(self):
        lm = LaneManager()
        lane_id = lm.on_grant(6005, 856012500, 100)

        # Manually backdate last_seen
        lm._lanes[lane_id]["last_seen"] = time.time() - 10

        released = lm.sweep_stale(max_age=5.0)
        assert 6005 in released
        assert lane_id not in lm._lanes

    def test_sweep_stale_keeps_fresh(self):
        lm = LaneManager()
        lm.on_grant(6005, 856012500, 100)

        released = lm.sweep_stale(max_age=5.0)
        assert released == []

    def test_free_lane_after_stale_sweep(self):
        lm = LaneManager()
        # Fill all 8 lanes
        for i in range(8):
            lm.on_grant(6000 + i, 856000000 + i * 25000, i)

        # Pool is full
        assert lm.on_grant(9999, 857000000, 999) is None

        # Stale one lane
        lane_0 = lm._tgid_to_lane[6000]
        lm._lanes[lane_0]["last_seen"] = time.time() - 10
        lm.sweep_stale(max_age=5.0)

        # Now a new grant should succeed
        lane_id = lm.on_grant(9999, 857000000, 999)
        assert lane_id is not None
