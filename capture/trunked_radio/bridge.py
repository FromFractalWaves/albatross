import json
import logging
import threading
import time

import zmq

from capture.trunked_radio import config

logger = logging.getLogger(__name__)

GRANT_TYPES = {"grant", "grant_update"}


def parse_grant(msg: dict) -> dict:
    """Extract grant fields from a raw metadata JSON message.

    Translates srcaddr (P25 domain) → source_unit (Albatross domain).
    """
    return {
        "tgid": msg.get("tgid"),
        "freq": msg.get("frequency"),
        "source_unit": msg.get("srcaddr"),
        "lane_id": msg.get("lane_id"),
    }


class LaneState:
    """Thread-safe mapping of lane_id → {tgid, freq, source_unit}."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lanes: dict[int, dict] = {}

    def update(self, lane_id: int, tgid: int, freq: int | None, source_unit: int | None) -> None:
        with self._lock:
            self._lanes[lane_id] = {
                "tgid": tgid,
                "freq": freq,
                "source_unit": source_unit,
            }

    def get(self, lane_id: int) -> dict | None:
        with self._lock:
            return self._lanes.get(lane_id)

    def clear(self, lane_id: int) -> None:
        with self._lock:
            self._lanes.pop(lane_id, None)


class MetadataSubscriber(threading.Thread):
    """Pulls metadata JSON from the flowgraph, updates LaneState, forwards to backend."""

    def __init__(self, lane_state: LaneState, zmq_context: zmq.Context):
        super().__init__(daemon=True)
        self.lane_state = lane_state
        self.ctx = zmq_context

    def run(self) -> None:
        meta_sock = self.ctx.socket(zmq.PULL)
        meta_sock.connect(config.metadata_endpoint())

        control_sock = self.ctx.socket(zmq.PUSH)
        control_sock.sndhwm = 1000
        control_sock.connect(config.control_backend_endpoint())

        logger.info("MetadataSubscriber connected — pull %s, push %s",
                     config.metadata_endpoint(), config.control_backend_endpoint())

        while True:
            raw = meta_sock.recv()
            msg = json.loads(raw)

            if msg.get("type") in GRANT_TYPES:
                grant = parse_grant(msg)
                lane_id = grant["lane_id"]
                if lane_id is not None:
                    self.lane_state.update(
                        lane_id, grant["tgid"], grant["freq"], grant["source_unit"],
                    )

                # grant_update carries a second tgid/freq pair
                if msg.get("type") == "grant_update" and msg.get("tgid2") is not None:
                    lane_id2 = msg.get("lane_id2")
                    if lane_id2 is not None:
                        self.lane_state.update(
                            lane_id2,
                            msg["tgid2"],
                            msg.get("frequency2"),
                            msg.get("srcaddr"),  # grant_update has no per-pair srcaddr
                        )

            # Translate srcaddr → source_unit before forwarding to backend
            if "srcaddr" in msg:
                msg["source_unit"] = msg["srcaddr"]
            control_sock.send(json.dumps(msg).encode())


class PCMLaneSubscriber(threading.Thread):
    """Pulls raw PCM for one voice lane, tags with tgid, pushes multipart to backend."""

    def __init__(self, lane_id: int, lane_state: LaneState, zmq_context: zmq.Context):
        super().__init__(daemon=True)
        self.lane_id = lane_id
        self.lane_state = lane_state
        self.ctx = zmq_context

    def run(self) -> None:
        pcm_sock = self.ctx.socket(zmq.PULL)
        pcm_sock.connect(config.pcm_endpoint(self.lane_id))

        push_sock = self.ctx.socket(zmq.PUSH)
        push_sock.sndhwm = 1000
        push_sock.connect(config.pcm_backend_endpoint())

        logger.info("PCMLaneSubscriber[%d] connected — pull %s, push %s",
                     self.lane_id, config.pcm_endpoint(self.lane_id),
                     config.pcm_backend_endpoint())

        while True:
            pcm_data = pcm_sock.recv()
            info = self.lane_state.get(self.lane_id)
            if info is None:
                continue

            header = json.dumps({
                "lane_id": self.lane_id,
                "tgid": info["tgid"],
                "freq": info["freq"],
                "source_unit": info["source_unit"],
                "ts": time.time(),
            }).encode()

            push_sock.send_multipart([header, pcm_data])


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    ctx = zmq.Context()
    lane_state = LaneState()

    MetadataSubscriber(lane_state, ctx).start()
    for lane_id in range(config.NUM_LANES):
        PCMLaneSubscriber(lane_id, lane_state, ctx).start()

    logger.info("Bridge started — %d PCM lanes, metadata on :%d",
                config.NUM_LANES, config.METADATA_PORT)

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        logger.info("Bridge shutting down")
    finally:
        ctx.term()


if __name__ == "__main__":
    main()
