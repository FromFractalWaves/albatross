# Trunked Radio Capture — Hardware & Dependencies

*What you need to run the capture pipeline against live RF.*

---

## Hardware

- **RTL-SDR dongle** — RTL2832U-based. Tested with RTL-SDR Blog V4 (R828D tuner). The flowgraph uses `osmosdr.source(args="rtl=0")`.
- **Antenna** — tuned for 850-860 MHz range (P25 band). A dipole cut for ~855 MHz, discone, or wideband scanner antenna works.

---

## Software Dependencies

### Compiled (C++ GNU Radio blocks)

| Package | Version | What it provides |
|---------|---------|-----------------|
| GNU Radio | 3.10+ | Core DSP framework, `gr.top_block`, filter blocks, ZMQ blocks |
| gr-osmosdr | (matches GR version) | `osmosdr.source()` — RTL-SDR source block |
| gr-op25 / gr-op25_repeater | boatbod fork | `p25_frame_assembler`, `fsk4_slicer_fb`, `costas_loop_cc`, `gardner_cc` — P25 frame assembly, symbol slicing, carrier/timing recovery |

### Python (OP25 app layer)

The flowgraph imports `p25_demod_cb` from OP25's Python app directory. This is a hierarchical block that does channelization, AGC, FLL, FM demodulation, and FSK4 symbol recovery. It also requires `op25_c4fm_mod.py` (in OP25's `apps/tx/` subdirectory) for C4FM matched filter tap generation.

Set the `OP25_APPS_DIR` environment variable to point to the OP25 apps directory:

```bash
export OP25_APPS_DIR=/path/to/op25/op25/gr-op25_repeater/apps
```

Default: `/usr/local/lib/op25/apps`

Both the apps directory and its `tx/` subdirectory are added to `sys.path` by the flowgraph.

### Python packages

All listed in `requirements.txt`:
- `pyzmq` — ZMQ bindings (used by all three processes)
- Standard library: `wave`, `json`, `uuid`, `dataclasses`, `threading`

---

## Target System

The reference deployment targets a specific P25 system:

| Parameter | Value |
|-----------|-------|
| County | DeKalb |
| Protocol | P25 Phase 1 |
| NAC | 0x01F0 |
| Control channel | 854.6125 MHz |
| SDR center frequency | 855.75 MHz |
| Freq table 0 | base=851.006250 MHz, step=6.250 kHz, offset=-45 MHz |
| Freq table 1 | base=762.006250 MHz, step=6.250 kHz, offset=+30 MHz |
| Voice channels observed | 856.0125, 856.3125, 856.3375, 856.9625, 857.3125 MHz |
| Active talkgroups observed | 6002, 6005, 6006, 6007, 6009, 6121, 6122, 6241, 6256, 6296 |

These values are hardcoded in `config.py`. To target a different P25 system, update `CENTER_FREQ`, `CONTROL_FREQ`, and the SDR gain values.

---

## Running

Start the three processes in separate terminals (order matters — backend first, flowgraph last):

```bash
# Terminal 1 — backend (no hardware needed)
source trm/.venv/bin/activate
python -m capture.trunked_radio.backend

# Terminal 2 — bridge (no hardware needed)
source trm/.venv/bin/activate
python -m capture.trunked_radio.bridge

# Terminal 3 — flowgraph (needs RTL-SDR + GNU Radio + OP25)
export OP25_APPS_DIR=/path/to/op25/op25/gr-op25_repeater/apps
python3 -m capture.trunked_radio.flowgraph
```

The backend and bridge can run without hardware — they just wait for ZMQ connections. The flowgraph requires the RTL-SDR dongle to be connected and GNU Radio + OP25 installed.

Note: the flowgraph must be run with the system `python3` (not the venv `python`) since GNU Radio and gr-op25 are installed as system packages. The backend and bridge can use either as long as `pyzmq` is available.

---

## What Can Be Tested Without Hardware

| Component | Testable? | How |
|-----------|-----------|-----|
| TSBK parser | Yes | `tests/test_tsbk.py` — binary decode, frequency resolution |
| LaneManager | Yes | `tests/test_lane_manager.py` — grant logic, preemption, stale sweep |
| BufferManager | Yes | `tests/test_buffer_manager.py` — PCM accumulation, timeout, drain |
| WAV writer | Yes | `tests/test_wav_writer.py` — output format, filenames |
| Packet builder | Yes | `tests/test_packet_builder.py` — field mapping |
| Backend finalization | Yes | `tests/test_capture_backend.py` — WAV + DB with mock ZMQ |
| Bridge LaneState | Yes | `tests/test_bridge.py` — thread-safe state, srcaddr translation |
| MetadataPoller | No | Needs `gr.msg_queue` (GNU Radio runtime) |
| Flowgraph | No | Needs GNU Radio + RTL-SDR hardware |

---

## What This Does NOT Cover

- ASR / transcription (downstream of capture)
- Multi-SDR expansion
- Encrypted talkgroup handling
- P25 Phase 2 / TDMA
- Process supervision (systemd, shell script, etc.)
