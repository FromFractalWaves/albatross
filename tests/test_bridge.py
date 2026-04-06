from capture.trunked_radio.bridge import GRANT_TYPES, LaneState, parse_grant


class TestLaneState:
    def test_update_and_get(self):
        ls = LaneState()
        ls.update(0, tgid=6005, freq=856012500, source_unit=100)
        info = ls.get(0)

        assert info == {"tgid": 6005, "freq": 856012500, "source_unit": 100}

    def test_get_unassigned_returns_none(self):
        ls = LaneState()
        assert ls.get(5) is None

    def test_update_overwrites_on_reassignment(self):
        ls = LaneState()
        ls.update(0, tgid=6005, freq=856012500, source_unit=100)
        ls.update(0, tgid=6038, freq=856312500, source_unit=200)

        info = ls.get(0)
        assert info["tgid"] == 6038
        assert info["source_unit"] == 200

    def test_clear_removes_assignment(self):
        ls = LaneState()
        ls.update(0, tgid=6005, freq=856012500, source_unit=100)
        ls.clear(0)

        assert ls.get(0) is None


class TestParseGrant:
    def test_srcaddr_to_source_unit(self):
        msg = {
            "type": "grant",
            "tgid": 6005,
            "frequency": 856012500,
            "srcaddr": 12345,
            "lane_id": 2,
        }
        grant = parse_grant(msg)

        assert grant["source_unit"] == 12345
        assert isinstance(grant["source_unit"], int)

    def test_grant_update_in_grant_types(self):
        assert "grant" in GRANT_TYPES
        assert "grant_update" in GRANT_TYPES


class TestPCMDropDecision:
    def test_drop_when_no_tgid(self):
        ls = LaneState()
        # Lane 3 has no assignment — PCM should be dropped
        assert ls.get(3) is None

    def test_no_drop_when_tgid_assigned(self):
        ls = LaneState()
        ls.update(3, tgid=6005, freq=856012500, source_unit=100)
        assert ls.get(3) is not None
