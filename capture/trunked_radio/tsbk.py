# TSBK (Trunking Signalling Block) Parser for P25 Phase 1
#
# Copyright (C) 2026 Albatross Contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module is licensed under the GNU General Public License v3.0
# or later. See <https://www.gnu.org/licenses/gpl-3.0.html>.
#
# Standalone — no Albatross imports.
#
# Bit layout matches OP25 (boatbod fork) tk_p25.py conventions:
#   msg.to_string() → 2-byte NAC + 10-byte body (CRC already stripped).
#   Body is converted to a 96-bit integer (left-shifted 16 for missing CRC)
#   before field extraction via bit shifts.


class TSBKParser:
    """Decodes P25 TSBK messages from OP25 msg_queue frames."""

    def __init__(self):
        self.freq_table: dict[int, dict] = {}

    def decode(self, nac: int, body_int: int) -> dict | None:
        """Decode a TSBK from its NAC and 96-bit body integer.

        body_int is the 10-byte body left-shifted 16 (to account for
        the missing 2-byte CRC), matching OP25's convention.

        Returns a structured dict or None for unhandled opcodes.
        """
        opcode = (body_int >> 88) & 0x3F

        if opcode == 0x00:
            result = self._decode_grant(body_int)
        elif opcode == 0x02:
            result = self._decode_grant_update(body_int)
        elif opcode == 0x03:
            result = self._decode_grant_update_explicit(body_int)
        elif opcode in (0x33, 0x34, 0x3D):
            result = self._decode_iden_up(opcode, body_int)
        else:
            return None

        if result is not None:
            result["nac"] = nac
        return result

    def _decode_grant(self, t: int) -> dict:
        """Opcode 0x00 — Group Voice Channel Grant."""
        mfrid = (t >> 80) & 0xFF
        if mfrid == 0x90:
            # Motorola GRG_ADD_CMD — not a voice grant, skip
            return None
        ch = (t >> 56) & 0xFFFF
        tgid = (t >> 40) & 0xFFFF
        srcaddr = (t >> 16) & 0xFFFFFF

        return {
            "type": "grant",
            "opcode": 0x00,
            "tgid": tgid,
            "frequency": self._resolve_frequency(ch),
            "srcaddr": srcaddr,
            "channel_id": ch,
        }

    def _decode_grant_update(self, t: int) -> dict:
        """Opcode 0x02 — Group Voice Channel Grant Update (two pairs)."""
        mfrid = (t >> 80) & 0xFF
        if mfrid == 0x90:
            # Motorola variant — single pair with srcaddr
            ch = (t >> 56) & 0xFFFF
            tgid = (t >> 40) & 0xFFFF
            srcaddr = (t >> 16) & 0xFFFFFF
            return {
                "type": "grant_update",
                "opcode": 0x02,
                "tgid": tgid,
                "frequency": self._resolve_frequency(ch),
                "channel_id": ch,
                "tgid2": None,
                "frequency2": None,
                "channel_id2": None,
                "srcaddr": srcaddr,
            }

        ch1 = (t >> 64) & 0xFFFF
        tgid1 = (t >> 48) & 0xFFFF
        ch2 = (t >> 32) & 0xFFFF
        tgid2 = (t >> 16) & 0xFFFF

        return {
            "type": "grant_update",
            "opcode": 0x02,
            "tgid": tgid1,
            "frequency": self._resolve_frequency(ch1),
            "channel_id": ch1,
            "tgid2": tgid2,
            "frequency2": self._resolve_frequency(ch2),
            "channel_id2": ch2,
        }

    def _decode_grant_update_explicit(self, t: int) -> dict:
        """Opcode 0x03 — Group Voice Channel Grant Update Explicit."""
        mfrid = (t >> 80) & 0xFF
        if mfrid == 0x90:
            # Motorola variant — two supergroup pairs
            ch1 = (t >> 64) & 0xFFFF
            sg1 = (t >> 48) & 0xFFFF
            ch2 = (t >> 32) & 0xFFFF
            sg2 = (t >> 16) & 0xFFFF
            return {
                "type": "grant_update",
                "opcode": 0x03,
                "tgid": sg1,
                "frequency": self._resolve_frequency(ch1),
                "channel_id": ch1,
                "tgid2": sg2,
                "frequency2": self._resolve_frequency(ch2),
                "channel_id2": ch2,
            }

        # Standard: opts + transmit ch + receive ch + tgid
        ch1 = (t >> 48) & 0xFFFF
        ch2 = (t >> 32) & 0xFFFF
        tgid = (t >> 16) & 0xFFFF

        return {
            "type": "grant",
            "opcode": 0x03,
            "tgid": tgid,
            "frequency": self._resolve_frequency(ch2),
            "srcaddr": None,
            "channel_id": ch2,
        }

    def _decode_iden_up(self, opcode: int, t: int) -> dict:
        """Opcodes 0x33, 0x34, 0x3D — Identifier Update."""
        iden = (t >> 76) & 0xF

        if opcode == 0x3D:
            # Standard iden_up
            bw = (t >> 67) & 0x1FF
            toff0 = (t >> 58) & 0x1FF
            spac = (t >> 48) & 0x3FF
            freq = (t >> 16) & 0xFFFFFFFF

            toff_sign = (toff0 >> 8) & 1
            toff = toff0 & 0xFF
            if toff_sign == 0:
                toff = -toff

            base_freq = freq * 5          # 5 Hz units → Hz
            step = spac * 125             # 125 Hz units → Hz
            offset = toff * 250000        # 250 kHz units → Hz

        elif opcode == 0x34:
            # iden_up VHF/UHF
            bw = (t >> 67) & 0x1FF
            toff0 = (t >> 58) & 0x1FF
            spac = (t >> 48) & 0x3FF
            freq = (t >> 16) & 0xFFFFFFFF

            toff_sign = (toff0 >> 8) & 1
            toff = toff0 & 0xFF
            if toff_sign == 0:
                toff = -toff

            base_freq = freq * 5
            step = spac * 125
            offset = toff * 250000

        elif opcode == 0x33:
            # iden_up TDMA
            bw = (t >> 67) & 0x1FF
            toff0 = (t >> 58) & 0x1FF
            spac = (t >> 48) & 0x3FF
            freq = (t >> 16) & 0xFFFFFFFF

            toff_sign = (toff0 >> 8) & 1
            toff = toff0 & 0xFF
            if toff_sign == 0:
                toff = -toff

            base_freq = freq * 5
            step = spac * 125
            offset = toff * 250000
        else:
            return None

        self.freq_table[iden] = {
            "base_freq": base_freq,
            "step": step,
            "offset": offset,
        }

        return {
            "type": "iden_up",
            "opcode": opcode,
            "table_id": iden,
            "base_freq": base_freq,
            "step": step,
            "offset": offset,
        }

    def _resolve_frequency(self, channel_id: int) -> int | None:
        """Resolve a channel ID to a frequency in Hz.

        Bits 15-12: table ID (selects freq_table entry)
        Bits 11-0:  channel number
        """
        table_id = (channel_id >> 12) & 0x0F
        channel_number = channel_id & 0x0FFF

        entry = self.freq_table.get(table_id)
        if entry is None:
            return None

        return entry["base_freq"] + (entry["step"] * channel_number)

    def process_qmsg(self, msg) -> dict | None:
        """Convenience wrapper for Process 1 integration.

        OP25 packs msg.type() as (protocol << 16 | duid).
        DUID 7 = TSBK. msg.to_string() returns NAC (2 bytes) + body (10 bytes,
        CRC already stripped by OP25).
        """
        duid = msg.type() & 0xFFFF
        if duid != 7:
            return None

        s = msg.to_string()
        # msg.to_string() returns bytes in Python 3 GR bindings
        if isinstance(s, bytes):
            raw = s
        else:
            raw = bytes(ord(c) for c in s)

        if len(raw) < 2:
            return None

        nac = (raw[0] << 8) | raw[1]
        body_bytes = raw[2:]

        # Convert body to integer and shift left 16 (for missing CRC),
        # matching OP25's convention: tsbk = t << 16
        body_int = 0
        for b in body_bytes:
            body_int = (body_int << 8) | b
        body_int <<= 16

        return self.decode(nac, body_int)
