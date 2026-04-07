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

**SDR source:** `osmosdr.source()` centered at 855.9625 MHz, 3.2 Msps. RF gain 30 dB, IF gain 20 dB, BB gain 20 dB. The center frequency is the midpoint of the control channel (854.6125 MHz) and the highest voice channel (857.3125 MHz), giving all channels equal margin within `p25_demod_cb`'s tunable range (max offset = 1.55 MHz, worst-case offset = 1.35 MHz).

**Control lane** — uses `p25_demod_cb` (OP25's complex-input demodulator with AGC, FLL, and full symbol recovery). This is the heavy demod chain but provides robust lock on the continuously-broadcasting control channel:

```
source → p25_demod_cb(input_rate=3200000, demod_type='fsk4',
                       relative_freq=1137500, if_rate=24000)
       → p25_frame_assembler(do_msgq=True, do_output=False)
       → gr.msg_queue(50)
```

The `relative_freq` follows OP25's convention: `CENTER_FREQ - CONTROL_FREQ` (positive when channel is below center). The `p25_demod_cb` block does its own two-stage decimation (3.2M → 100k → 25k), bandpass filtering, mixing, resampling to 24 kHz, AGC, FLL, FM demod, and FSK4 symbol recovery internally.

The frame assembler writes P25 frames into the message queue. DUID 7 messages are TSBKs (12 bytes: 2-byte NAC + 10-byte body, CRC stripped by OP25).

**Voice lanes** (3 pooled, dynamically retuned) — use the same `p25_demod_cb` as the control channel:

```
source → p25_demod_cb(input_rate=3200000, demod_type='fsk4',
                       relative_freq=0, if_rate=24000)
       → p25_frame_assembler(do_output=True, do_audio_output=True)
       → zeromq.push_sink(sizeof_short, tcp://*:5560+lane_id, timeout=100ms)
```

Voice lanes start at relative_freq 0 (idle). The LaneManager retunes them via `demod.set_relative_frequency(center - freq)` when channel grants arrive (OP25 convention: positive when channel is below center).

**CPU budget:** Both control and voice lanes use `p25_demod_cb`, which has efficient two-stage decimation built in (BPF decim=32 → 100 kHz, then LPF decim=4 → 25 kHz, then arb_resampler → 24 kHz). The BPF at the input rate has ~200 taps at 100 kHz bandwidth, vs ~3,855 taps for a single-stage `freq_xlating_fir_filter` with 11 kHz cutoff at 3.2 MHz — roughly 18x less work per voice lane. Lane count is 3 (sufficient for DeKalb County traffic volume).

### LaneManager

Pure logic, no GNU Radio dependency. Thread-safe (all methods locked).

- `on_grant(tgid, freq, srcaddr) -> lane_id | None` — Existing tgid: update/retune. Same freq: preempt. Else allocate free. Else drop (pool exhausted).
- `sweep_stale(max_age=5.0) -> list[released_tgids]` — Releases lanes not seen in grant stream for `max_age` seconds. P25 control channel rebroadcasts active grants every ~1-2s, so absence is a reliable end-of-call signal.
- Retune callback wired by the flowgraph to `voice_demod.set_relative_frequency(center_freq - freq)`.

### MetadataPoller

Daemon thread bridging `gr.msg_queue` to ZMQ.

1. Drains `gr.msg_queue` (non-blocking, 5ms sleep on empty)
2. Calls `TSBKParser.process_qmsg()` on each message
3. For grants/grant_updates: calls `LaneManager.on_grant()`, injects returned `lane_id` into the event dict
4. Pushes all parsed events as JSON via ZMQ PUSH on :5557 (NOBLOCK, drops if no consumer)
5. Every ~2s: calls `LaneManager.sweep_stale()`
6. Every ~10s: logs a status line with message/TSBK/decoded counts

---

## Process 2: Bridge

Correlates metadata (which tgid is on which lane) with PCM (which lane is producing audio). Three types of daemon threads in a single process.

**LaneState** — Thread-safe mapping of `lane_id -> {tgid, freq, source_unit}`. Updated by metadata events, read by PCM subscribers.

**MetadataSubscriber** — Pulls JSON from :5557. For grant/grant_update events, updates LaneState. Translates `srcaddr` (P25 domain) to `source_unit` (Albatross domain) at this boundary. Forwards all messages to :5581 for the backend. Send HWM set to 1000.

**PCMLaneSubscriber** (x8) — One per voice lane. Pulls raw int16 PCM from :5560+lane_id. Looks up tgid in LaneState. If no tgid assigned, drops the PCM. Otherwise wraps in ZMQ multipart and pushes to :5580 (send HWM 1000):

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

**Event Loop** — Async (`zmq.asyncio`). Polls PCM (:5580) and control (:5581) with 10ms timeout. Every 0.5s sweeps for timed-out calls. On call end: writes WAV, builds packet, writes `Transmission` row to DB (`status="captured"`), pushes packet via `PacketSink` to :5590. Per-call finalization is wrapped in try/except — a single bad call does not crash the loop.

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

Decodes P25 TSBKs from OP25's `gr.msg_queue` frames. The `process_qmsg()` method handles the OP25 wire format:

- `msg.type()` is packed as `(protocol << 16 | DUID)`. DUID 7 = TSBK.
- `msg.to_string()` returns bytes: 2-byte NAC + 10-byte body (CRC already stripped by OP25).
- The 10-byte body is converted to a 96-bit integer (left-shifted 16 for missing CRC) matching OP25's `tk_p25.py` convention before field extraction via bit shifts.

TSBK body layout (96-bit integer after shift): bits 93-88 = opcode (6 bits, after LB/protected flags). Field positions match OP25's `decode_tsbk()` in `tk_p25.py`.

Handled opcodes:
- **0x00** — Group Voice Channel Grant (tgid, channel_id, srcaddr). Skips Motorola mfrid=0x90 variants.
- **0x02** — Group Voice Channel Grant Update (two tgid/channel pairs). Handles Motorola mfrid=0x90 variant (single pair + srcaddr).
- **0x03** — Group Voice Channel Grant Update Explicit. Handles standard and Motorola variants.
- **0x33, 0x34, 0x3D** — Identifier Update (frequency table entries). Populates `freq_table` used by `_resolve_frequency()`.

Frequency resolution: channel_id bits 15-12 select a table entry, bits 11-0 are the channel number. `frequency = base + (step × channel_number)`. Units match OP25: base in 5 Hz units × 5, step in 125 Hz units × 125, offset in 250 kHz units × 250000.

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
