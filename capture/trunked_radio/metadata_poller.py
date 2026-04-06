import json
import logging
import threading
import time

import zmq

from capture.trunked_radio import config
from capture.trunked_radio.lane_manager import LaneManager
from capture.trunked_radio.tsbk import TSBKParser

logger = logging.getLogger(__name__)

GRANT_TYPES = {"grant", "grant_update"}


class MetadataPoller(threading.Thread):
    """Daemon thread — drains gr.msg_queue, parses TSBKs, forwards via ZMQ.

    Bridges gr.msg_queue → TSBKParser → LaneManager → ZMQ PUSH on :5557.
    """

    def __init__(
        self,
        msg_queue,
        tsbk_parser: TSBKParser,
        lane_manager: LaneManager,
        zmq_context: zmq.Context,
    ):
        super().__init__(daemon=True)
        self.msg_queue = msg_queue
        self.tsbk_parser = tsbk_parser
        self.lane_manager = lane_manager
        self.ctx = zmq_context

    def run(self) -> None:
        push_sock = self.ctx.socket(zmq.PUSH)
        push_sock.sndhwm = 1000
        push_sock.bind(f"tcp://*:{config.METADATA_PORT}")

        logger.info("MetadataPoller started — PUSH on :%d", config.METADATA_PORT)

        last_sweep = time.time()
        last_status = time.time()
        msg_count = 0
        tsbk_count = 0
        decoded_count = 0

        while True:
            msg = self.msg_queue.delete_head_nowait()
            if msg is None:
                time.sleep(0.005)
            else:
                msg_count += 1
                duid = msg.type() & 0xFFFF
                if duid == 7:
                    tsbk_count += 1

                event = self.tsbk_parser.process_qmsg(msg)
                if event is not None:
                    decoded_count += 1
                    if event["type"] in GRANT_TYPES:
                        lane_id = self.lane_manager.on_grant(
                            event["tgid"],
                            event.get("frequency"),
                            event.get("srcaddr"),
                        )
                        event["lane_id"] = lane_id
                        freq_mhz = event.get("frequency")
                        freq_str = f"{freq_mhz / 1e6:.4f} MHz" if freq_mhz else "unresolved"
                        logger.info(
                            "[meta] %s tgid=%s freq=%s src=%s → lane=%s",
                            event["type"], event.get("tgid"), freq_str,
                            event.get("srcaddr"), lane_id,
                        )

                        if (
                            event["type"] == "grant_update"
                            and event.get("tgid2") is not None
                        ):
                            lane_id2 = self.lane_manager.on_grant(
                                event["tgid2"],
                                event.get("frequency2"),
                                event.get("srcaddr"),
                            )
                            event["lane_id2"] = lane_id2
                            freq2 = event.get("frequency2")
                            freq2_str = f"{freq2 / 1e6:.4f} MHz" if freq2 else "unresolved"
                            logger.info(
                                "[meta] grant_update pair2 tgid=%s freq=%s → lane=%s",
                                event["tgid2"], freq2_str, lane_id2,
                            )
                    elif event["type"] == "iden_up":
                        logger.info(
                            "[meta] iden_up table=%d base=%d step=%d offset=%d",
                            event["table_id"], event["base_freq"],
                            event["step"], event["offset"],
                        )

                    try:
                        push_sock.send(json.dumps(event).encode(), zmq.NOBLOCK)
                    except zmq.Again:
                        pass  # no consumer connected, drop silently

            now = time.time()
            if now - last_sweep >= config.STALE_SWEEP_INTERVAL:
                released = self.lane_manager.sweep_stale()
                if released:
                    logger.info("[meta] swept stale tgids: %s", released)
                last_sweep = now

            if now - last_status >= 10.0:
                logger.info(
                    "[meta] status: %d msgs, %d tsbk, %d decoded (last 10s)",
                    msg_count, tsbk_count, decoded_count,
                )
                msg_count = 0
                tsbk_count = 0
                decoded_count = 0
                last_status = now
