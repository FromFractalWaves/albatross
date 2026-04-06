import threading
import time
from collections.abc import Callable

from capture.trunked_radio import config


class LaneManager:
    """Thread-safe lane allocation — tracks voice lane → talkgroup assignments.

    Pure logic, no GNU Radio dependency.
    """

    def __init__(
        self,
        num_lanes: int = config.NUM_LANES,
        retune_callback: Callable[[int, int], None] | None = None,
    ):
        self._num_lanes = num_lanes
        self._lock = threading.Lock()
        self._lanes: dict[int, dict] = {}
        self._tgid_to_lane: dict[int, int] = {}
        self._retune_callback = retune_callback

    def set_retune_callback(self, callback: Callable[[int, int], None]) -> None:
        self._retune_callback = callback

    def on_grant(self, tgid: int, freq: int | None, srcaddr: int | None) -> int | None:
        """Handle a channel grant.

        Returns lane_id if assigned, None if pool exhausted.
        """
        with self._lock:
            now = time.time()

            # 1. tgid already has a lane — update it
            if tgid in self._tgid_to_lane:
                lane_id = self._tgid_to_lane[tgid]
                lane = self._lanes[lane_id]
                old_freq = lane["freq"]
                lane["freq"] = freq
                lane["srcaddr"] = srcaddr
                lane["last_seen"] = now
                if freq is not None and freq != old_freq and self._retune_callback:
                    self._retune_callback(lane_id, freq)
                return lane_id

            # 2. Another tgid holds a lane on the same freq — preempt
            if freq is not None:
                for lane_id, lane in self._lanes.items():
                    if lane["freq"] == freq:
                        old_tgid = lane["tgid"]
                        del self._tgid_to_lane[old_tgid]
                        lane["tgid"] = tgid
                        lane["freq"] = freq
                        lane["srcaddr"] = srcaddr
                        lane["last_seen"] = now
                        self._tgid_to_lane[tgid] = lane_id
                        return lane_id

            # 3. Allocate a free lane
            for candidate in range(self._num_lanes):
                if candidate not in self._lanes:
                    self._lanes[candidate] = {
                        "tgid": tgid,
                        "freq": freq,
                        "srcaddr": srcaddr,
                        "last_seen": now,
                    }
                    self._tgid_to_lane[tgid] = candidate
                    if freq is not None and self._retune_callback:
                        self._retune_callback(candidate, freq)
                    return candidate

            # 4. Pool exhausted
            return None

    def sweep_stale(self, max_age: float = config.STALE_MAX_AGE) -> list[int]:
        """Release lanes not seen in grant stream for max_age seconds.

        Returns list of released tgids.
        """
        with self._lock:
            now = time.time()
            released: list[int] = []
            for lane_id in list(self._lanes):
                lane = self._lanes[lane_id]
                if now - lane["last_seen"] > max_age:
                    released.append(lane["tgid"])
                    del self._tgid_to_lane[lane["tgid"]]
                    del self._lanes[lane_id]
            return released
