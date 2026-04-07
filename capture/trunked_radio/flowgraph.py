"""P25 trunked radio flowgraph — Process 1.

GNU Radio top_block that tunes an RTL-SDR, decodes the P25 control channel,
and runs pooled voice demodulators.

Requires: GNU Radio 3.10+, gr-osmosdr, gr-op25 (boatbod fork), RTL-SDR hardware.
"""

import logging
import os
import sys

import zmq

from capture.trunked_radio import config
from capture.trunked_radio.lane_manager import LaneManager
from capture.trunked_radio.metadata_poller import MetadataPoller
from capture.trunked_radio.tsbk import TSBKParser

# OP25 app-layer imports
# p25_demodulator imports op25_c4fm_mod from the tx/ subdirectory
sys.path.insert(0, config.OP25_APPS_DIR)
sys.path.insert(0, os.path.join(config.OP25_APPS_DIR, "tx"))

from gnuradio import blocks, gr, zeromq  # noqa: E402

import osmosdr  # noqa: E402
from gnuradio import op25_repeater  # noqa: E402
from p25_demodulator import p25_demod_cb  # noqa: E402

logger = logging.getLogger(__name__)

# OP25 demod defaults for P25 Phase 1
_IF_RATE = 24000
_SYMBOL_RATE = 4800


class P25Flowgraph(gr.top_block):
    """GNU Radio flowgraph — SDR source, control + voice lanes.

    Both control and voice lanes use p25_demod_cb (complex input, full demod
    chain with two-stage decimation, AGC, and FLL). At 3.2 Msps, p25_demod_cb
    uses efficient BPF(decim=32) → mixer → LPF(decim=4) → arb_resampler,
    which is ~18x lighter than a single-stage freq_xlating_fir_filter.
    """

    def __init__(self):
        super().__init__()

        # SDR source
        self.source = osmosdr.source(args="rtl=0")
        self.source.set_center_freq(config.CENTER_FREQ)
        self.source.set_sample_rate(config.SDR_SAMPLE_RATE)
        self.source.set_gain(config.SDR_RF_GAIN)
        self.source.set_if_gain(config.SDR_IF_GAIN)
        self.source.set_bb_gain(config.SDR_BB_GAIN)

        # --- Control lane (p25_demod_cb — heavy but robust) ---
        self.msg_queue = gr.msg_queue(50)

        ctrl_demod = p25_demod_cb(
            input_rate=config.SDR_SAMPLE_RATE,
            demod_type='fsk4',
            relative_freq=-config.CONTROL_OFFSET,
            offset=0,
            if_rate=_IF_RATE,
            symbol_rate=_SYMBOL_RATE,
        )
        ctrl_assembler = op25_repeater.p25_frame_assembler(
            "",        # udp_host (unused)
            0,         # port (unused)
            0,         # debug
            True,      # do_imbe
            False,     # do_output
            True,      # do_msgq
            self.msg_queue,
            False,     # do_audio_output
            False,     # do_phase2_tdma
            False,     # do_nocrypt
        )

        self.connect(self.source, ctrl_demod, ctrl_assembler)

        # --- Voice lanes (p25_demod_cb — same two-stage decim as control) ---
        self.voice_demods: dict[int, p25_demod_cb] = {}

        for lane_id in range(config.NUM_LANES):
            demod = p25_demod_cb(
                input_rate=config.SDR_SAMPLE_RATE,
                demod_type='fsk4',
                relative_freq=0,       # idle — retuned on grant
                offset=0,
                if_rate=_IF_RATE,
                symbol_rate=_SYMBOL_RATE,
            )

            voice_queue = gr.msg_queue(2)
            assembler = op25_repeater.p25_frame_assembler(
                "",        # udp_host
                0,         # port
                0,         # debug
                True,      # do_imbe
                True,      # do_output
                False,     # do_msgq
                voice_queue,
                True,      # do_audio_output
                False,     # do_phase2_tdma
                False,     # do_nocrypt
            )
            sink = zeromq.push_sink(
                gr.sizeof_short,
                1,
                f"tcp://*:{config.PCM_BASE_PORT + lane_id}",
                config.ZMQ_SINK_TIMEOUT,
            )

            self.connect(self.source, demod, assembler, sink)
            self.voice_demods[lane_id] = demod

        # --- Lane manager + metadata poller ---
        def _retune(lane_id: int, freq: int) -> None:
            # OP25 convention: relative_freq = CENTER - CHANNEL
            relative_freq = config.CENTER_FREQ - freq
            ok = self.voice_demods[lane_id].set_relative_frequency(relative_freq)
            if ok:
                logger.info("Retuned lane %d → %.4f MHz (relative %+d Hz)", lane_id, freq / 1e6, relative_freq)
            else:
                logger.warning("Retune FAILED lane %d → %.4f MHz (relative %+d Hz) — out of tunable range", lane_id, freq / 1e6, relative_freq)

        self.lane_manager = LaneManager(retune_callback=_retune)
        self.tsbk_parser = TSBKParser()
        self.zmq_ctx = zmq.Context()
        self.metadata_poller = MetadataPoller(
            self.msg_queue, self.tsbk_parser, self.lane_manager, self.zmq_ctx,
        )

    def start(self):
        self.metadata_poller.start()
        logger.info(
            "P25Flowgraph starting — center=%.4f MHz, %d voice lanes",
            config.CENTER_FREQ / 1e6,
            config.NUM_LANES,
        )
        super().start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fg = P25Flowgraph()
    try:
        fg.start()
        fg.wait()
    except KeyboardInterrupt:
        logger.info("Flowgraph shutting down")
        fg.stop()
        fg.wait()
    finally:
        fg.zmq_ctx.term()
