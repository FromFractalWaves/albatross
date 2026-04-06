import struct

from capture.trunked_radio.tsbk import TSBKParser


def _make_frame(nac: int, body: bytes) -> bytes:
    """Build a 12-byte TSBK frame: 2-byte NAC + 10-byte body."""
    return struct.pack(">H", nac) + body.ljust(10, b"\x00")


class TestTSBKDecode:
    def test_grant_decode(self):
        parser = TSBKParser()
        # opcode=0x00, channel_id=0x1234, tgid=0x00FF, srcaddr=0x000ABC
        body = bytes([0x00, 0x12, 0x34, 0x00, 0xFF, 0x00, 0x0A, 0xBC, 0x00, 0x00])
        result = parser.decode(_make_frame(0x0293, body))

        assert result is not None
        assert result["type"] == "grant"
        assert result["opcode"] == 0x00
        assert result["tgid"] == 0x00FF
        assert result["srcaddr"] == 0x0ABC
        assert result["channel_id"] == 0x1234
        assert result["tdma_slot"] is None
        assert result["nac"] == 0x0293

    def test_grant_update_decode(self):
        parser = TSBKParser()
        # opcode=0x02, ch1=0x1000, tgid1=100, ch2=0x2000, tgid2=200
        body = bytes([0x02, 0x10, 0x00, 0x00, 0x64, 0x20, 0x00, 0x00, 0xC8, 0x00])
        result = parser.decode(_make_frame(0x0293, body))

        assert result is not None
        assert result["type"] == "grant_update"
        assert result["opcode"] == 0x02
        assert result["tgid"] == 100
        assert result["tgid2"] == 200

    def test_iden_up_populates_freq_table(self):
        parser = TSBKParser()
        # opcode=0x3D, table_id=2 (upper nibble of body[1])
        # base_freq=851000000 (0x32BD4A00 is close but let's use a simpler value)
        # We'll encode: table_id=2 in body[1] high nibble, base_freq in body[2:6], step in body[6:8], offset in body[8:10]
        table_id = 2
        base_freq = 851000000
        step = 12500
        offset = 0
        body = bytes([0x3D])
        body += bytes([(table_id << 4)])
        body += struct.pack(">I", base_freq)
        body += struct.pack(">H", step)
        body += struct.pack(">H", offset)

        result = parser.decode(_make_frame(0x0293, body))

        assert result is not None
        assert result["type"] == "iden_up"
        assert result["table_id"] == 2
        assert parser.freq_table[2]["base_freq"] == 851000000
        assert parser.freq_table[2]["step"] == 12500

    def test_frequency_resolution(self):
        parser = TSBKParser()
        # Seed freq table: table 1, base=851000000, step=12500
        parser.freq_table[1] = {"base_freq": 851000000, "step": 12500, "offset": 0}

        # channel_id with table_id=1 (bits 15-12) and channel_number=10 (bits 11-0)
        # table_id=1 → 0x1000, channel=10 → 0x000A → channel_id=0x100A
        body = bytes([0x00, 0x10, 0x0A, 0x00, 0x64, 0x00, 0x00, 0x01, 0x00, 0x00])
        result = parser.decode(_make_frame(0x0293, body))

        assert result["frequency"] == 851000000 + (12500 * 10)

    def test_unknown_opcode_returns_none(self):
        parser = TSBKParser()
        body = bytes([0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        result = parser.decode(_make_frame(0x0293, body))
        assert result is None

    def test_nac_extraction(self):
        parser = TSBKParser()
        parser.freq_table[0] = {"base_freq": 0, "step": 1, "offset": 0}
        body = bytes([0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x01, 0x00, 0x00])
        result = parser.decode(_make_frame(0xBEEF, body))
        assert result["nac"] == 0xBEEF

    def test_short_data_returns_none(self):
        parser = TSBKParser()
        assert parser.decode(b"\x00" * 5) is None
