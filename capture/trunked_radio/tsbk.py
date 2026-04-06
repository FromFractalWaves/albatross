# TSBK (Trunking Signalling Block) Parser for P25 Phase 1
#
# Copyright (C) 2026 Albatross Contributors
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This module is licensed under the GNU General Public License v3.0
# or later. See <https://www.gnu.org/licenses/gpl-3.0.html>.
#
# Standalone — no Albatross imports.


class TSBKParser:
    """Decodes P25 TSBK messages from raw 12-byte frames."""

    def __init__(self):
        self.freq_table: dict[int, dict] = {}

    def decode(self, data: bytes) -> dict | None:
        """Decode a 12-byte TSBK frame (2-byte NAC + 10-byte body).

        Returns a structured dict or None for unhandled opcodes.
        """
        if len(data) < 12:
            return None

        nac = (data[0] << 8) | data[1]
        body = data[2:]
        opcode = body[0]

        if opcode == 0x00:
            result = self._decode_grant(body)
        elif opcode == 0x02:
            result = self._decode_grant_update(body)
        elif opcode == 0x03:
            result = self._decode_grant_update_explicit(body)
        elif opcode in (0x33, 0x34, 0x3D):
            result = self._decode_iden_up(body)
        else:
            return None

        if result is not None:
            result["nac"] = nac
        return result

    def _decode_grant(self, body: bytes) -> dict:
        """Opcode 0x00 — Channel Grant."""
        channel_id = (body[1] << 8) | body[2]
        tgid = (body[3] << 8) | body[4]
        srcaddr = (body[5] << 16) | (body[6] << 8) | body[7]

        return {
            "type": "grant",
            "opcode": 0x00,
            "tgid": tgid,
            "frequency": self._resolve_frequency(channel_id),
            "srcaddr": srcaddr,
            "channel_id": channel_id,
            "tdma_slot": None,
        }

    def _decode_grant_update(self, body: bytes) -> dict:
        """Opcode 0x02 — Channel Grant Update (two tgid/freq pairs)."""
        channel_id_1 = (body[1] << 8) | body[2]
        tgid_1 = (body[3] << 8) | body[4]
        channel_id_2 = (body[5] << 8) | body[6]
        tgid_2 = (body[7] << 8) | body[8]

        return {
            "type": "grant_update",
            "opcode": 0x02,
            "tgid": tgid_1,
            "frequency": self._resolve_frequency(channel_id_1),
            "channel_id": channel_id_1,
            "tgid2": tgid_2,
            "frequency2": self._resolve_frequency(channel_id_2),
            "channel_id2": channel_id_2,
        }

    def _decode_grant_update_explicit(self, body: bytes) -> dict:
        """Opcode 0x03 — Channel Grant Update Explicit."""
        channel_id = (body[1] << 8) | body[2]
        tgid = (body[3] << 8) | body[4]
        srcaddr = (body[5] << 16) | (body[6] << 8) | body[7]

        return {
            "type": "grant",
            "opcode": 0x03,
            "tgid": tgid,
            "frequency": self._resolve_frequency(channel_id),
            "srcaddr": srcaddr,
            "channel_id": channel_id,
            "tdma_slot": None,
        }

    def _decode_iden_up(self, body: bytes) -> dict:
        """Opcodes 0x33, 0x34, 0x3D — Identifier Update."""
        opcode = body[0]
        table_id = (body[1] >> 4) & 0x0F
        base_freq = (
            (body[2] << 24) | (body[3] << 16) | (body[4] << 8) | body[5]
        )
        step = (body[6] << 8) | body[7]
        offset = (body[8] << 8) | body[9]

        self.freq_table[table_id] = {
            "base_freq": base_freq,
            "step": step,
            "offset": offset,
        }

        return {
            "type": "iden_up",
            "opcode": opcode,
            "table_id": table_id,
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

        Checks msg.type() == 7, extracts bytes, delegates to decode().
        """
        if msg.type() != 7:
            return None
        return self.decode(msg.to_string())
