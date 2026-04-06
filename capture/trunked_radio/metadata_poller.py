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
        push_sock.bind(f"tcp://*:{config.METADATA_PORT}")

        logger.info("MetadataPoller started — PUSH on :%d", config.METADATA_PORT)

        last_sweep = time.time()

        while True:
            msg = self.msg_queue.delete_head_nowait()
            if msg is None:
                time.sleep(0.005)
            else:
                event = self.tsbk_parser.process_qmsg(msg)
                if event is not None:
                    if event["type"] in GRANT_TYPES:
                        lane_id = self.lane_manager.on_grant(
                            event["tgid"],
                            event.get("frequency"),
                            event.get("srcaddr"),
                        )
                        event["lane_id"] = lane_id

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

                    push_sock.send(json.dumps(event).encode())

            now = time.time()
            if now - last_sweep >= config.STALE_SWEEP_INTERVAL:
                released = self.lane_manager.sweep_stale()
                if released:
                    logger.debug("Swept stale tgids: %s", released)
                last_sweep = now
