# Trunked Radio Capture — Architecture

*How the P25 trunked radio capture pipeline works.*

---

## Overview

The capture pipeline turns a live P25 Phase 1 trunked radio signal into `TransmissionPacket` objects. It is the first stage of the Albatross pipeline — everything upstream of ASR/preprocessing.

Three cooperating OS processes connected by ZMQ:

```
[1] Flowgraph (capture/trunked_radio/flowgraph.py)
      ├── control lane → msg_queue → MetadataPoller → ZMQ PUSH :5557 (JSON)
      └── voice lanes (x8) → ZMQ PUSH :5560-:5567 (int16 PCM)

[2] Bridge (capture/trunked_radio/bridge.py)
      ├── pulls metadata from :5557, tracks lane→tgid mapping
      ├── pulls PCM from :5560-:5567, tags with tgid
      └── pushes to backend: :5580 (tagged PCM multipart), :5581 (metadata JSON)

[3] Backend (capture/trunked_radio/backend.py)
      ├── pulls from :5580 and :5581
      ├── accumulates PCM per talkgroup in memory
      ├── detects call boundaries (inactivity timeout or lane reassignment)
      └── on call end: WAV file + TransmissionPacket → DB write + ZMQ push :5590
```

ZMQ decouples processes so the flowgraph (real-time RF) never blocks on downstream processing. The backend is the only process that imports from `contracts/` or `db/`.

---

## Process 1: Flowgraph

GNU Radio `gr.top_block` subclass (`P25Flowgraph`). Requires GNU Radio 3.10+, gr-osmosdr, gr-op25 (boatbod fork), and a physical RTL-SDR dongle.

### Signal Chain

**SDR source:** `osmosdr.source()` centered at 855.75 MHz, 3.2 Msps. RF gain 30 dB, IF gain 20 dB, BB gain 20 dB. The center frequency is between the control channel (854.6125 MHz) and voice channels (856-857 MHz) so both fall within the visible band.

**Control lane** (one, fixed offset):

```
source → freq_xlating_fir_filter_ccf(decim=50, offset=-1,137,500 Hz)
       → quadrature_demod_cf(gain = 64000 / (2pi x 600))
       → p25_demod_fb(input_rate=64000)
       → frame_assembler(do_imbe=True, do_output=False, do_msgq=True)
       → gr.msg_queue(50)
```

The frame assembler writes raw 12-byte binary P25 TSBKs into the message queue (type 7 messages).

**Voice lanes** (8 pooled, dynamically retuned):

```
source → freq_xlating_fir_filter_ccf(decim=50, offset=0 initially)
       → quadrature_demod_cf(same gain)
       → p25_demod_fb(input_rate=64000)
       → frame_assembler(do_imbe=True, do_output=True, do_audio_output=True)
       → zeromq.push_sink(sizeof_short, tcp://*:5560+lane_id, timeout=100ms)
```

Voice lanes start at offset 0 (idle). The LaneManager retunes them via `set_center_freq()` when channel grants arrive.

**Channel filter taps:** Hamming-windowed low-pass, 6250 Hz cutoff, 1500 Hz transition, at the source sample rate.

**FM demod gain:** `channel_rate / (2pi x FM_deviation)` where channel_rate = 64000 Hz and FM_deviation = 600 Hz (P25 C4FM symbol deviation).

**`p25_demod_fb`:** Hierarchical block from OP25's app layer (`p25_demodulator.py`). Contains AGC, C4FM matched filter (using `op25_c4fm_mod` taps), and `fsk4_demod_ff` with symbol timing recovery. Imported via `sys.path` from `OP25_APPS_DIR`.

### LaneManager

Pure logic, no GNU Radio dependency. Thread-safe (all methods locked).

- `on_grant(tgid, freq, srcaddr) -> lane_id | None` — Existing tgid: update/retune. Same freq: preempt. Else allocate free. Else drop (pool exhausted).
- `sweep_stale(max_age=5.0) -> list[released_tgids]` — Releases lanes not seen in grant stream for `max_age` seconds. P25 control channel rebroadcasts active grants every ~1-2s, so absence is a reliable end-of-call signal.
- Retune callback wired by the flowgraph to `voice_channelizer.set_center_freq(freq - center_freq)`.

### MetadataPoller

Daemon thread bridging `gr.msg_queue` to ZMQ.

1. Drains `gr.msg_queue` (non-blocking, 5ms sleep on empty)
2. Calls `TSBKParser.process_qmsg()` on each message
3. For grants/grant_updates: calls `LaneManager.on_grant()`, injects returned `lane_id` into the event dict
4. Pushes all parsed events as JSON via ZMQ PUSH on :5557
5. Every ~2s: calls `LaneManager.sweep_stale()`

---

## Process 2: Bridge

Correlates metadata (which tgid is on which lane) with PCM (which lane is producing audio). Three types of daemon threads in a single process.

**LaneState** — Thread-safe mapping of `lane_id -> {tgid, freq, source_unit}`. Updated by metadata events, read by PCM subscribers.

**MetadataSubscriber** — Pulls JSON from :5557. For grant/grant_update events, updates LaneState. Translates `srcaddr` (P25 domain) to `source_unit` (Albatross domain) at this boundary. Forwards all messages to :5581 for the backend.

**PCMLaneSubscriber** (x8) — One per voice lane. Pulls raw int16 PCM from :5560+lane_id. Looks up tgid in LaneState. If no tgid assigned, drops the PCM. Otherwise wraps in ZMQ multipart and pushes to :5580:

```
Part 0: JSON header {"lane_id": int, "tgid": int, "freq": int|null, "source_unit": int|null, "ts": float}
Part 1: Raw int16 PCM bytes
```

---

## Process 3: Backend

Accumulates PCM per talkgroup, detects call boundaries, writes WAV files, emits packets.

**BufferManager** — In-memory call state machine keyed by tgid. Opens `ActiveCall` on grant or first PCM. Appends PCM chunks. Closes to `CompletedCall` on inactivity timeout (1.5s) or lane reassignment.

**WAV Writer** — Writes `CompletedCall` audio as mono int16 WAV (8000 Hz). Filename: `{ISO8601}_{tgid}_{source_unit}_{uuid}.wav`.

**Packet Builder** — Maps `CompletedCall` + WAV path to `TransmissionPacket` (from `contracts.models`). Sets `metadata` with `system`, `lane_id`, `end_reason`, `sample_rate`.

**Event Loop** — Async (`zmq.asyncio`). Polls PCM (:5580) and control (:5581) with 10ms timeout. Every 0.5s sweeps for timed-out calls. On call end: writes WAV, builds packet, writes `Transmission` row to DB (`status="captured"`), pushes packet via `PacketSink` to :5590.

---

## ZMQ Port Map

| Port | Direction | Format | Description |
|------|-----------|--------|-------------|
| 5557 | Flowgraph → Bridge | JSON | Parsed TSBK events (grants, updates, iden_up) |
| 5560-5567 | Flowgraph → Bridge | Raw int16 PCM | Voice lane audio (one port per lane) |
| 5580 | Bridge → Backend | Multipart (JSON header + PCM) | Tagged PCM with tgid/lane metadata |
| 5581 | Bridge → Backend | JSON | Forwarded metadata events |
| 5590 | Backend → API | JSON | Completed `TransmissionPacket`s |

---

## TSBK Parser

Standalone module (`tsbk.py`). No Albatross imports. GPL v3.

Decodes raw 12-byte P25 TSBKs (2-byte NAC + 10-byte body) into structured dicts. Maintains a frequency table populated from `iden_up` broadcasts. Handles opcodes: 0x00 (grant), 0x02 (grant update), 0x03 (grant update explicit), 0x33/0x34/0x3d (frequency table entries).

Frequency resolution: channel_id bits 15-12 select a table entry, bits 11-0 are the channel number. `frequency = base + (step x channel_number)`.

---

## File Map

```
capture/trunked_radio/
├── __init__.py
├── config.py              # All constants — ZMQ ports, SDR params, timeouts
├── models.py              # Internal dataclasses (MetadataEvent, ActiveCall, etc.)
├── tsbk.py                # TSBK binary parser (standalone, GPL v3)
├── lane_manager.py        # Voice lane allocation logic (pure, testable)
├── metadata_poller.py     # Daemon thread: msg_queue → parser → lane manager → ZMQ
├── flowgraph.py           # Process 1: GNU Radio top_block
├── bridge.py              # Process 2: metadata + PCM correlation
├── backend.py             # Process 3: PCM accumulation, WAV, DB, packet emit
├── buffer_manager.py      # Call state machine (used by backend)
├── wav_writer.py          # WAV file output (used by backend)
├── packet_builder.py      # CompletedCall → TransmissionPacket (used by backend)
└── packet_sink.py         # Packet emission protocol + implementations
```

---

## Data Flow: Source Unit Naming

The P25 source radio ID follows this naming path:

1. **TSBK parser** outputs `srcaddr` (P25 domain term, always `int | None`)
2. **MetadataPoller** passes `srcaddr` through in the JSON event dict
3. **Bridge** translates `srcaddr` → `source_unit` when updating LaneState and PCM headers
4. **Backend** receives `source_unit` in PCM headers and metadata events
5. **TransmissionPacket** carries `source_unit` (Albatross contract term)

The value is always `int | None`, never string.
