"""P25 trunked radio flowgraph — Process 1.

GNU Radio top_block that tunes an RTL-SDR, decodes the P25 control channel,
and runs pooled voice channelizers.

Requires: GNU Radio 3.10+, gr-osmosdr, gr-op25 (boatbod fork), RTL-SDR hardware.
"""

import logging
import math
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

from gnuradio import analog, blocks, filter as gr_filter, gr, zeromq  # noqa: E402
from gnuradio.fft import window as gr_window  # noqa: E402

import osmosdr  # noqa: E402
from gnuradio import op25, op25_repeater  # noqa: E402
from p25_demodulator import p25_demod_cb  # noqa: E402

import op25_c4fm_mod  # noqa: E402

logger = logging.getLogger(__name__)

# OP25 demod defaults for P25 Phase 1
_IF_RATE = 24000
_SYMBOL_RATE = 4800


class P25Flowgraph(gr.top_block):
    """GNU Radio flowgraph — SDR source, control + voice lanes.

    Control lane uses p25_demod_cb (complex input, full demod chain with AGC/FLL).
    Voice lanes use lightweight channelizer → FM demod → FSK4 (no AGC/FLL needed
    since frequencies are known from grants).
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

        # --- Voice lanes (lightweight channelizer + FM demod + FSK4) ---
        # Decimate 3.2 MHz → _IF_RATE (24 kHz) per voice channel
        voice_decim = config.SDR_SAMPLE_RATE // _IF_RATE  # 133

        voice_taps = gr_filter.firdes.low_pass(
            1,
            config.SDR_SAMPLE_RATE,
            _IF_RATE / 2 - 1000,     # 11 kHz cutoff
            2000,                     # transition
            gr_window.WIN_HAMMING,
        )

        # FM demod gain and C4FM symbol filter for voice
        fm_gain = _IF_RATE / (2 * math.pi * 600.0)  # 600 Hz symbol deviation
        sps = _IF_RATE // _SYMBOL_RATE  # 5 samples per symbol
        c4fm_taps = op25_c4fm_mod.c4fm_taps(
            sample_rate=_IF_RATE, span=9,
            generator=op25_c4fm_mod.transfer_function_rx,
        ).generate()

        self.voice_channelizers: dict[int, gr_filter.freq_xlating_fir_filter_ccf] = {}

        for lane_id in range(config.NUM_LANES):
            # Channelizer: translate + decimate to _IF_RATE
            channelizer = gr_filter.freq_xlating_fir_filter_ccf(
                voice_decim, voice_taps, 0, config.SDR_SAMPLE_RATE,
            )

            # FM demod
            fm_demod = analog.quadrature_demod_cf(fm_gain)

            # Baseband amp + C4FM matched filter + FSK4 demod + slicer
            bb_amp = blocks.multiply_const_ff(1.0)
            sym_filter = gr_filter.fir_filter_fff(1, c4fm_taps)
            autotuneq = gr.msg_queue(2)
            fsk4_demod = op25.fsk4_demod_ff(autotuneq, _IF_RATE, _SYMBOL_RATE)
            levels = [-2.0, 0.0, 2.0, 4.0]
            slicer = op25_repeater.fsk4_slicer_fb(0, 0, levels)

            # Frame assembler → PCM output
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

            self.connect(
                self.source, channelizer, fm_demod,
                bb_amp, sym_filter, fsk4_demod, slicer,
                assembler, sink,
            )
            self.voice_channelizers[lane_id] = channelizer

        # --- Lane manager + metadata poller ---
        def _retune(lane_id: int, freq: int) -> None:
            offset = freq - config.CENTER_FREQ
            self.voice_channelizers[lane_id].set_center_freq(offset)
            logger.info("Retuned lane %d → %.4f MHz (offset %+d Hz)", lane_id, freq / 1e6, offset)

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
