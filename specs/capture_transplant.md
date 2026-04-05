# Capture Pipeline — Transplant Spec

*Extracted from `albatross1a` prototype, validated against live P25 RF on 2026-04-04.*

This spec describes the capture layer: the system that turns a live P25 trunked radio signal into `TransmissionPacket` objects. It is the first stage of the Albatross pipeline — everything upstream of ASR/preprocessing.

---

## Integration Contract

**Capture output must conform to the existing `TransmissionPacket` in `contracts/models.py` as-is.** The contract is domain-agnostic by design. P25-specific fields go in the `metadata` dict — the contract is not modified.

The existing `TransmissionPacket` fields:

```python
id: str                          # UUID, assigned by capture
timestamp: str                   # ISO8601, call start time
talkgroup_id: int                # P25 TGID
source_unit: Optional[int]       # Source radio ID (srcaddr), nullable
frequency: float                 # Hz
duration: float                  # Seconds
encryption_status: bool          # False for this system
audio_path: str                  # Path to WAV file
metadata: dict[str, Any] = {}   # Domain-specific fields go here
```

**`source_unit` is `int` throughout.** The TSBK parser outputs `srcaddr` as a raw 24-bit integer. The prototype converted it to a string in the bridge — that was a mistake. In Albatross, the value stays `int | None` from the TSBK parser onward. The TSBK parser output keeps the name `srcaddr` (that's its P25 domain term), but once the value enters the capture internal models (`ActiveCall`, `CompletedCall`, PCM headers, lane state), it becomes `source_unit` to match the Albatross contract. No name translation at the `TransmissionPacket` boundary — the field is already `source_unit` by that point.

P25-specific metadata (lives in `metadata` dict, not on the contract):
- `system`: `"p25_phase1"`
- `lane_id`: int (which voice lane captured this)
- `end_reason`: `"inactivity_timeout"` | `"lane_reassigned"`
- `sample_rate`: `8000`

**The mock live pipeline (`api/services/live_pipeline.py`, `docs/pipeline/mock_pipeline.md`) is the reference implementation for the data handoff pattern.** The real capture layer follows the same flow:

1. Build a `TransmissionPacket` from capture output
2. Call `to_orm()` → `Transmission` ORM object with `status="captured"`, `text=None`
3. Write to DB via async session
4. Everything downstream (preprocessing, TRM, persistence) is unchanged

The capture layer writes directly to the database using the same `db/session.py` async session factory. No new handoff mechanism is needed.

**Push-only data flow.** The Albatross pipeline uses push-based notification throughout — no polling. The capture backend, after writing a `TransmissionPacket` to the DB, pushes a notification over ZMQ so downstream stages (preprocessing, TRM) can consume immediately. This matches the in-process mock pipeline where async `PacketQueue`s connect stages; ZMQ bridges the process boundary instead of an asyncio queue. The standalone mock scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`) use DB polling — that pattern is legacy and is not carried forward into the real pipeline.

---

## What It Does

A single RTL-SDR dongle receives P25 Phase 1 trunked radio. The system:

1. Decodes the P25 control channel to learn which talkgroups are active on which frequencies
2. Dynamically tunes voice decoders to active voice channels
3. Captures decoded audio per talkgroup
4. Detects transmission boundaries (call start/end)
5. Writes each completed transmission as a WAV file
6. Emits a `TransmissionPacket` for each transmission

Output: WAV files + `TransmissionPacket` records conforming to the existing Albatross contract.

---

## Three-Process Architecture

The capture layer lives in `capture/trunked_radio/` — one implementation of the capture stage, alongside the existing `capture/mock/`. All shared modules (models, config, TSBK parser, buffer manager, etc.) are flat within the package. The three processes are entry points in that same package.

The capture layer runs as three cooperating processes connected by ZMQ:

```
[1] Flowgraph (capture/trunked_radio/flowgraph.py)
      ├── control lane → msg_queue → MetadataPoller → ZMQ PUSH :5557 (JSON)
      └── voice lanes (×8) → ZMQ PUSH :5560-:5567 (int16 PCM)

[2] Bridge (capture/trunked_radio/bridge.py)
      ├── pulls metadata from :5557, tracks lane→tgid mapping
      ├── pulls PCM from :5560-:5567, tags with tgid
      └── pushes to backend: :5580 (tagged PCM multipart), :5581 (metadata JSON)

[3] Backend (capture/trunked_radio/backend.py)
      ├── pulls from :5580 and :5581
      ├── accumulates PCM per talkgroup in memory
      ├── detects call boundaries (inactivity timeout)
      └── on call end: WAV file + TransmissionPacket → DB write
```

This is three OS processes, not three async tasks. ZMQ decouples them so the flowgraph (real-time RF) never blocks on downstream processing.

The backend process is the integration point with the main Albatross repo. It imports from `contracts/models.py` and `db/` to write packets to the database. Processes 1 and 2 have no Albatross dependencies.

Entry points: `python -m capture.trunked_radio.flowgraph`, `python -m capture.trunked_radio.bridge`, `python -m capture.trunked_radio.backend`.

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

### Event Type Canonicalization (Prototype Bug Fix)

The prototype has an event type naming mismatch across the three processes that must be fixed during transplant.

**The TSBK parser outputs:** `"type": "grant"`, `"type": "grant_update"`, `"type": "iden_up"`

**The bridge reads:** `msg.get("json_type")` — wrong key. Should be `msg.get("type")`. Because of this, the bridge's `LaneState` never updates from metadata events in the prototype. It still works because the flowgraph's `LaneManager` (Process 1) correctly assigns lanes using `event["type"]`, and the bridge forwards the raw JSON to the backend regardless.

**The backend's `BufferManager` expects:** `GRANT_EVENT_TYPES = {"channel_grant", "channel_update", "update", "call_start"}` — wrong values. The TSBK parser emits `"grant"` and `"grant_update"`, not `"channel_grant"` or `"channel_update"`. Similarly, `RELEASE_EVENT_TYPES = {"call_end", "release", "channel_release"}` — but the TSBK parser never emits any of these types. There is no explicit release event from the parser.

**Net effect in the prototype:** Metadata-driven grant handling and release handling in the backend never fire. All calls are created by `handle_pcm` (which opens an `ActiveCall` if none exists for the tgid) and all calls end via inactivity timeout (1.5s). This works but means `end_reason` is always `"inactivity_timeout"` and lane reassignment closures never happen at the backend level.

**Fix for Albatross:** Use the TSBK parser's event types as the canonical names throughout. The correct sets are:

```python
GRANT_EVENT_TYPES = {"grant", "grant_update"}
RELEASE_EVENT_TYPES = set()  # No explicit release from TSBK parser; calls end via timeout or lane reassignment
```

The bridge reads `msg.get("type")`, not `msg.get("json_type")`. The `MetadataEvent` model uses a `type` field (renamed from `json_type`). Lane reassignment detection at the backend level works via grant events that assign a new tgid to an already-occupied lane — this is already implemented in `BufferManager._grant_or_update()` and will now actually fire.

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

Thread-safe mapping of `lane_id → {tgid, freq, source_unit}`. Updated from metadata events (grants set tgid, lane reassignment clears prior). The bridge reads `msg.get("type")` (not `"json_type"` as in the prototype — see Event Type Canonicalization above).

### Metadata Subscriber

Pulls JSON from :5557. Parses grant events via the `"type"` field. Updates LaneState. Forwards to backend control socket (:5581).

### PCM Lane Subscribers

One thread per voice lane. Each pulls raw int16 PCM from `pcm_endpoint(lane_id)`. Looks up current tgid in LaneState. If no active tgid, drops the PCM. Otherwise wraps in a ZMQ multipart message and pushes to :5580:

```
Part 0: JSON header {"lane_id": int, "tgid": int, "freq": int|null, "source_unit": int|null, "ts": float}
Part 1: Raw int16 PCM bytes
```

Note: The bridge translates `srcaddr` from the TSBK parser output into `source_unit` when building the PCM header and updating lane state. This is where the P25 domain name crosses into the Albatross domain name.

---

## Process 3: Backend

Accumulates PCM per talkgroup, detects call boundaries, writes WAV files, emits packets.

### Buffer Manager

In-memory call state machine. Tracks active calls by tgid.

**State transitions:**
- **Grant event arrives:** Open new `ActiveCall` or update existing one. If the grant assigns a new tgid to a lane that already has a different tgid, close the prior call with reason `"lane_reassigned"`.
- **PCM arrives for existing call:** Append chunk, update `last_pcm_at`
- **PCM arrives with no existing call:** Open new `ActiveCall` from PCM header fields
- **Inactivity timeout (1.5s no PCM):** Close call with reason `"inactivity_timeout"`

There are no explicit release events from the TSBK parser. Call endings are detected by inactivity timeout or lane reassignment. The prototype's `RELEASE_EVENT_TYPES` were never matched and should be removed.

**ActiveCall** accumulates PCM as a list of byte chunks. On close, chunks are joined into a single `audio_bytes` buffer → `CompletedCall`.

### WAV Writer

Writes each `CompletedCall` as a mono int16 WAV file.

**Filename:** `{ISO8601_start}_{tgid}_{source_unit}_{uuid}.wav`

**Parameters:** 1 channel, 2 bytes/sample, 8000 Hz sample rate.

### Packet Builder

Constructs a `TransmissionPacket` from each `CompletedCall`, mapping to the existing contract fields:

```python
TransmissionPacket(
    id=str(uuid4()),
    timestamp=call.start_time.isoformat(),       # ISO8601 call start
    talkgroup_id=call.tgid,                       # int
    source_unit=call.source_unit,                 # int | None
    frequency=float(call.freq),                   # Hz as float
    duration=call.duration_seconds,               # float
    encryption_status=False,                      # not handling encrypted
    audio_path=str(wav_path),                     # absolute path to WAV
    metadata={
        "system": "p25_phase1",
        "lane_id": call.lane_id,
        "end_reason": call.end_reason,            # "inactivity_timeout" | "lane_reassigned"
        "sample_rate": 8000,
    },
)
```

After building the packet, the backend calls `packet.to_orm()` and writes the resulting `Transmission` row to the database with `status="captured"`. This is the same pattern used by the mock capture stage in `LivePipelineManager`.

### Packet Emission

The backend emits each completed `TransmissionPacket` via a `PacketSink`. The prototype defines a `PacketSink` protocol with `JsonlPacketSink` and `StdoutPacketSink` implementations. For Albatross integration, a `ZmqPacketSink` pushes the packet as JSON to a dedicated endpoint (`:5590`), notifying the API that a new packet is available for preprocessing.

The DB write and ZMQ push happen together in `_finalize_calls` — write to DB first, then push notification. The API subscribes to `:5590` and feeds incoming packets into the preprocessing stage. This is the push-based equivalent of the mock pipeline's `PacketQueue` between capture and preprocessing, bridging the OS process boundary via ZMQ.

```
Backend writes to DB  ──→  Backend pushes to :5590  ──→  API receives, starts preprocessing
```

### Event Loop

The backend is async — it uses `zmq.asyncio.Context` and `zmq.asyncio.Poller` throughout, not the synchronous ZMQ API. This is a change from the prototype's synchronous `zmq.Poller` loop, driven by the need for async DB writes via `AsyncSessionLocal`. The main loop polls two ZMQ sockets (PCM and control) with a 10ms timeout. Every 0.5s it sweeps for timed-out calls. On shutdown it drains all remaining calls. Entry point: `asyncio.run(backend.run())`.

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
- Database persistence beyond the initial `status="captured"` write (the main Albatross pipeline handles the rest)
- Web UI
- Multi-SDR expansion
- Encrypted talkgroup handling
- P25 Phase 2 / TDMA (the TSBK parser has some TDMA support but voice decoding is Phase 1 only)
- How the capture processes are started/supervised (systemd, shell script, etc.)

---

## Open Design Questions

1. **Where do WAV files live?** The prototype used `out/wav/`. The main repo needs a convention — probably configurable via `.env` or settings, with a default like `data/wav/` or `capture/wav/`.

2. **How are the three capture processes launched?** They're separate OS processes. The prototype launched them manually. For integration, options include a shell script, a supervisor process, or systemd units. This is an operational decision, not a code decision.