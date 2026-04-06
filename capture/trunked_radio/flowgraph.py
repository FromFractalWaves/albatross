"""P25 trunked radio flowgraph — Process 1.

GNU Radio top_block that tunes an RTL-SDR, decodes the P25 control channel,
and runs 8 pooled voice channelizers.

Requires: GNU Radio 3.10+, gr-osmosdr, gr-op25 (boatbod fork), RTL-SDR hardware.
"""

import logging
import math
import sys

import zmq

from capture.trunked_radio import config
from capture.trunked_radio.lane_manager import LaneManager
from capture.trunked_radio.metadata_poller import MetadataPoller
from capture.trunked_radio.tsbk import TSBKParser

# OP25 app-layer import (p25_demod_fb hierarchical block)
sys.path.insert(0, config.OP25_APPS_DIR)

from gnuradio import analog, filter as gr_filter, gr, zeromq  # noqa: E402
from gnuradio.fft import window as gr_window  # noqa: E402

import osmosdr  # noqa: E402
import op25_repeater  # noqa: E402
from p25_demodulator import p25_demod_fb  # noqa: E402

logger = logging.getLogger(__name__)


class P25Flowgraph(gr.top_block):
    """GNU Radio flowgraph — SDR source, control lane, 8 voice lanes."""

    def __init__(self):
        super().__init__()

        # SDR source
        self.source = osmosdr.source(args="rtl=0")
        self.source.set_center_freq(config.CENTER_FREQ)
        self.source.set_sample_rate(config.SDR_SAMPLE_RATE)
        self.source.set_gain(config.SDR_RF_GAIN)
        self.source.set_if_gain(config.SDR_IF_GAIN)
        self.source.set_bb_gain(config.SDR_BB_GAIN)

        # Shared filter taps and FM demod gain
        taps = gr_filter.firdes.low_pass(
            1,
            config.SDR_SAMPLE_RATE,
            config.CHANNEL_FILTER_CUTOFF,
            config.CHANNEL_FILTER_TRANSITION,
            gr_window.WIN_HAMMING,
        )
        fm_gain = config.CHANNEL_RATE / (2 * math.pi * config.FM_DEVIATION)

        # --- Control lane ---
        self.msg_queue = gr.msg_queue(50)

        ctrl_channelizer = gr_filter.freq_xlating_fir_filter_ccf(
            config.CHANNEL_DECIMATION, taps, config.CONTROL_OFFSET, config.SDR_SAMPLE_RATE,
        )
        ctrl_demod = analog.quadrature_demod_cf(fm_gain)
        ctrl_p25 = p25_demod_fb(input_rate=config.CHANNEL_RATE)
        ctrl_assembler = op25_repeater.frame_assembler(
            do_imbe=True,
            do_output=False,
            do_msgq=True,
            do_audio_output=False,
            queue=self.msg_queue,
        )

        self.connect(self.source, ctrl_channelizer, ctrl_demod, ctrl_p25, ctrl_assembler)

        # --- Voice lanes (x8) ---
        self.voice_channelizers: dict[int, gr_filter.freq_xlating_fir_filter_ccf] = {}

        for lane_id in range(config.NUM_LANES):
            channelizer = gr_filter.freq_xlating_fir_filter_ccf(
                config.CHANNEL_DECIMATION, taps, 0, config.SDR_SAMPLE_RATE,
            )
            demod = analog.quadrature_demod_cf(fm_gain)
            p25 = p25_demod_fb(input_rate=config.CHANNEL_RATE)
            assembler = op25_repeater.frame_assembler(
                do_imbe=True,
                do_output=True,
                do_msgq=False,
                do_audio_output=True,
            )
            sink = zeromq.push_sink(
                gr.sizeof_short,
                1,
                f"tcp://*:{config.PCM_BASE_PORT + lane_id}",
                config.ZMQ_SINK_TIMEOUT,
            )

            self.connect(self.source, channelizer, demod, p25, assembler, sink)
            self.voice_channelizers[lane_id] = channelizer

        # --- Lane manager + metadata poller ---
        def _retune(lane_id: int, freq: int) -> None:
            offset = freq - config.CENTER_FREQ
            self.voice_channelizers[lane_id].set_center_freq(offset)
            logger.debug("Retuned lane %d to %d Hz (offset %d)", lane_id, freq, offset)

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
