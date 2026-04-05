# Capture Pipeline — Transplant Spec

*Extracted from `albatross1a` prototype, validated against live P25 RF on 2026-04-04.*

This spec describes the capture layer: the system that turns a live P25 trunked radio signal into `TransmissionPacket` objects. It is the first stage of the Albatross pipeline — everything upstream of ASR/preprocessing.

---

## What It Does

A single RTL-SDR dongle receives P25 Phase 1 trunked radio. The system:

1. Decodes the P25 control channel to learn which talkgroups are active on which frequencies
2. Dynamically tunes voice decoders to active voice channels
3. Captures decoded audio per talkgroup
4. Detects transmission boundaries (call start/end)
5. Writes each completed transmission as a WAV file
6. Emits a `TransmissionPacket` for each transmission

Output: WAV files + structured packet records conforming to the Albatross `TransmissionPacket` contract.

---

## Three-Process Architecture

The capture layer runs as three cooperating processes connected by ZMQ:

```
[1] Flowgraph (GNU Radio)
      ├── control lane → msg_queue → MetadataPoller → ZMQ PUSH :5557 (JSON)
      └── voice lanes (×8) → ZMQ PUSH :5560-:5567 (int16 PCM)

[2] Bridge
      ├── pulls metadata from :5557, tracks lane→tgid mapping
      ├── pulls PCM from :5560-:5567, tags with tgid
      └── pushes to backend: :5580 (tagged PCM multipart), :5581 (metadata JSON)

[3] Backend
      ├── pulls from :5580 and :5581
      ├── accumulates PCM per talkgroup in memory
      ├── detects call boundaries (inactivity timeout)
      └── on call end: WAV file + TransmissionPacket
```

This is three OS processes, not three async tasks. ZMQ decouples them so the flowgraph (real-time RF) never blocks on downstream processing.

---

## Process 1: Flowgraph

GNU Radio flowgraph using gr-op25 blocks. Handles all RF and P25 signal processing.

### SDR Configuration

| Parameter | Value | Notes |
|-----------|-------|-------|
| Center frequency | 855.75 MHz | Between control and voice channels |
| Sample rate | 3.2 Msps | ±1.6 MHz visible band |
| Gain | 30 dB | RTL-SDR RF gain |
| IF gain | 20 dB | |
| BB gain | 20 dB | |

The SDR is NOT centered on the control channel. It's centered between the control channel (854.6125 MHz) and the voice channels (856-857 MHz) so both fall within the visible band (854.15-857.35 MHz).

### Control Lane

One fixed channelizer offset from center to the control channel frequency:

```
source → freq_xlating_fir_filter_ccf(decim=50, offset=-1,137,500 Hz)
       → quadrature_demod_cf(gain = 64000 / (2π × 600))
       → p25_demod_fb(input_rate=64000)
       → p25_frame_assembler(do_imbe=True, do_output=False, do_msgq=True, do_audio_output=False)
```

The frame assembler writes raw binary P25 TSBKs into a `gr.msg_queue`. These are NOT JSON — they are 12-byte binary messages (2-byte NAC + 10-byte TSBK body) with message type 7.

**Channel filter taps:** Hamming-windowed low-pass, 6250 Hz cutoff, 1500 Hz transition, at the source sample rate.

**FM demod gain:** `channel_rate / (2π × 600)` where 600 Hz is the P25 C4FM symbol deviation.

**p25_demod_fb:** This is a hierarchical block from OP25's app layer (`p25_demodulator.py`). It contains AGC, a C4FM matched filter (using `op25_c4fm_mod` taps), and `fsk4_demod_ff` with symbol timing recovery. Using this instead of bare `fsk4_demod_ff` is critical — the C4FM matched filter is what makes the decoder lock reliably.

### Voice Lanes

8 pooled voice channelizers, initially at offset 0 (idle). Retuned on channel grants:

```
source → freq_xlating_fir_filter_ccf(decim=50, offset=voice_freq - center_freq)
       → quadrature_demod_cf(same gain)
       → p25_demod_fb(input_rate=64000)
       → p25_frame_assembler(do_imbe=True, do_output=True, do_msgq=False, do_audio_output=True)
       → zeromq.push_sink(sizeof_short, timeout=100ms)
```

The frame assembler with `do_audio_output=True` outputs int16 PCM at 2 bytes per sample. Each lane has its own ZMQ PUSH socket on a dedicated port (5560 + lane_id).

The 100ms ZMQ timeout means PCM is dropped (not queued) if no subscriber is connected. This prevents backpressure from stalling the flowgraph.

### TSBK Parser

A standalone Python module that decodes raw binary TSBKs into structured dicts. Extracted from OP25's `trunking.py` (GPL v3, attributed).

**Input:** 12-byte binary message from `gr.msg_queue` (type 7)

**Output:** Dict with fields:
```python
{
    "type": "grant" | "grant_update" | "iden_up" | "other",
    "opcode": int,
    "nac": int,
    "tgid": int | None,
    "frequency": int | None,     # Hz, resolved from channel ID
    "srcaddr": int | None,       # source radio ID (24-bit)
    "channel_id": int | None,    # raw 16-bit channel ID
    "tdma_slot": int | None,
    # grant_update also has tgid2, frequency2, channel_id2, tdma_slot2
}
```

**Opcodes handled:**
- `0x00` — group voice channel grant (tgid, frequency, srcaddr)
- `0x02` — grant update (two tgid/frequency pairs, no srcaddr)
- `0x03` — grant update explicit
- `0x33` — frequency table entry (TDMA)
- `0x34` — frequency table entry (VHF/UHF)
- `0x3d` — frequency table entry (generic) — **this is the one this system uses**

**Frequency resolution:** Channel IDs are 16-bit values where bits 15-12 select a frequency table entry and bits 11-0 are the channel number. The table entry provides a base frequency and step size. `frequency = base + (step × channel_number)`. The table is populated from `iden_up` TSBKs broadcast on the control channel.

**Important:** The frequency table must accumulate across calls. It's populated by `iden_up` TSBKs that the system broadcasts periodically. Until the table entries are received, channel grants can't resolve to frequencies.

### Lane Manager

Tracks which voice lanes are assigned to which talkgroups.

**Grant handling:**
1. If tgid already has a lane, update it (retune if freq changed)
2. If another tgid holds a lane on the same frequency, preempt it (the system reassigned the channel)
3. Otherwise allocate a free lane
4. If no free lanes, drop the grant

**Stale release:** Every ~2 seconds, sweep all assigned lanes. Any tgid not seen in the grant stream for 5 seconds is released. The P25 control channel rebroadcasts active grants every ~1-2 seconds, so absence is a reliable signal that the call ended.

**Thread safety:** All operations are locked. The MetadataPoller and the main loop access it concurrently.

### MetadataPoller

A daemon thread that:
1. Drains the `gr.msg_queue` (non-blocking poll, 5ms sleep on empty)
2. Decodes each message via `TSBKParser.process_qmsg()`
3. For grants/grant_updates: calls `LaneManager.on_grant()`, annotates event with lane_id
4. Forwards parsed events as JSON over ZMQ PUSH to :5557
5. Periodically sweeps stale lanes

---

## Process 2: Bridge

Correlates metadata (which tgid is on which lane) with PCM (which lane is producing audio) and forwards both to the backend.

### Lane State

Thread-safe mapping of `lane_id → {tgid, freq, srcaddr}`. Updated from metadata events (grants set tgid, releases clear it).

### Metadata Subscriber

Pulls JSON from :5557. Parses grant/release events. Updates LaneState. Forwards to backend control socket (:5581).

### PCM Lane Subscribers

One thread per voice lane. Each pulls raw int16 PCM from `pcm_endpoint(lane_id)`. Looks up current tgid in LaneState. If no active tgid, drops the PCM. Otherwise wraps in a ZMQ multipart message and pushes to :5580:

```
Part 0: JSON header {"lane_id": int, "tgid": int, "freq": int|null, "source_radio_id": str|null, "ts": float}
Part 1: Raw int16 PCM bytes
```

---

## Process 3: Backend

Accumulates PCM per talkgroup, detects call boundaries, writes WAV files, emits packets.

### Buffer Manager

In-memory call state machine. Tracks active calls by tgid.

**State transitions:**
- **Grant + PCM arrives:** Open new `ActiveCall`, start accumulating chunks
- **PCM arrives for existing call:** Append chunk, update `last_pcm_at`
- **Lane reassigned (new tgid on same lane):** Close prior call with reason "lane_reassigned"
- **Inactivity timeout (1.5s no PCM):** Close call with reason "timeout"
- **Release event:** Close call with reason "release"

**ActiveCall** accumulates PCM as a list of byte chunks. On close, chunks are joined into a single `audio_bytes` buffer → `CompletedCall`.

### WAV Writer

Writes each `CompletedCall` as a mono int16 WAV file.

**Filename:** `{ISO8601_start}_{tgid}_{srcaddr}_{uuid}.wav`

**Parameters:** 1 channel, 2 bytes/sample, 8000 Hz sample rate.

### Packet Builder

Constructs a `TransmissionPacket` from each `CompletedCall`:

```json
{
    "packet_id": "uuid",
    "packet_type": "transmission",
    "timestamp_start": "ISO8601",
    "timestamp_end": "ISO8601",
    "source": {
        "talkgroup_id": 6096,
        "source_radio_id": "1070172",
        "frequency": 856312500
    },
    "metadata": {
        "talkgroup_id": 6096,
        "source_radio_id": "1070172",
        "frequency": 856312500,
        "system": "p25_phase1",
        "lane_id": 2,
        "end_reason": "timeout"
    },
    "payload": {
        "audio_path": "/path/to/file.wav",
        "duration_seconds": 4.2,
        "sample_rate": 8000
    },
    "status": "captured"
}
```

This conforms to the Albatross base `Packet` schema. `source_radio_id` is nullable — it's only present if the initial channel grant included a `srcaddr`.

### Event Loop

The backend polls two ZMQ sockets (PCM and control) with a 10ms timeout. Every 0.5s it sweeps for timed-out calls. On shutdown it drains all remaining calls.

---

## Target System (Confirmed)

| Parameter | Value |
|-----------|-------|
| County | DeKalb |
| Protocol | P25 Phase 1 |
| NAC | 0x01F0 |
| WACN | 0xBEE00 |
| SysID | 0x1F5 |
| RFSS | 80, Site 16 |
| Control channel | 854.6125 MHz |
| Freq table 0 | base=851.006250 MHz, step=6.250 kHz, offset=-45 MHz |
| Freq table 1 | base=762.006250 MHz, step=6.250 kHz, offset=+30 MHz |
| Freq table opcode | 0x3d (iden_up), not 0x34 |
| Voice channels observed | 856.0125, 856.3125, 856.3375, 856.9625, 857.3125 MHz |
| Active talkgroups | 6005, 6038, 6040, 6078, 6096, 6121, 6122, 6258, 6296 |

---

## External Dependencies

**Must be installed (compiled C++ GNU Radio blocks):**
- GNU Radio 3.10+
- gr-osmosdr (RTL-SDR source block)
- gr-op25 / gr-op25_repeater (boatbod fork) — P25 demodulator and frame assembler

**Python-level OP25 dependency:**
- `p25_demod_fb` hierblock from `p25_demodulator.py` in the OP25 apps directory. This is a Python hierarchical block that wraps the C4FM matched filter + symbol timing recovery. It requires `op25_c4fm_mod.py` (in the OP25 `apps/tx/` dir) for the filter tap generation. Currently referenced via `sys.path.insert`. Should be vendored or extracted.

**Standalone (already extracted):**
- `tsbk.py` — TSBK parser. No OP25 dependency. Only uses `ctypes` from stdlib. GPL v3, attributed to OP25 authors. Can be copied directly.

**Python packages:**
- pyzmq (ZMQ bindings)
- Standard library: wave, json, uuid, dataclasses, threading

---

## What This Spec Does NOT Cover

- ASR / transcription (downstream of capture)
- TRM routing (downstream of ASR)
- Database persistence (the main albatross repo handles this)
- Web UI
- Multi-SDR expansion
- Encrypted talkgroup handling
- P25 Phase 2 / TDMA (the TSBK parser has some TDMA support but voice decoding is Phase 1 only)

---

## Integration Notes

The main albatross repo already has `TransmissionPacket` in `contracts/models.py` with a `to_orm()` method. The capture layer's packet output should map to that contract. The `source`, `metadata`, and `payload` field structure above is designed to align with it.

The mock pipeline in the main repo (`capture/mock/run.py`) currently reads from `packets_radio.json`. The real capture layer replaces that with live packet emission. The handoff point is the `TransmissionPacket` — everything downstream (preprocessing, TRM, storage) is unchanged.

The capture layer runs as a separate set of processes from the API server. It writes packets to the database (or a queue) for the existing pipeline to consume. The exact handoff mechanism (direct DB write, message queue, filesystem watch) is a design decision for the build plan.
