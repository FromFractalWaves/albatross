# Build Plan: Capture Transplant — Step 1 (Backend + Shared Modules)

_Generated from spec — aligned with repo on 2026-04-06_

## Goal

Build the capture backend process and all shared modules it depends on, so that fake ZMQ messages fed to the backend produce real `Transmission` rows in the database and WAV files on disk — all testable without GNU Radio or radio hardware.

**Context:** See `specs/capture_transplant/step_one_summaries.md` for current and target state.

## References

### Pre-build

| File | What it is | Why it's relevant |
|------|-----------|-------------------|
| `contracts/models.py` | `TransmissionPacket` with `to_orm()` | The contract the packet builder must conform to |
| `db/models.py` | `Transmission` ORM model | Target of `to_orm()` — confirms available columns |
| `db/session.py` | `AsyncSessionLocal` factory | Backend imports this for DB writes |
| `db/base.py` | `DeclarativeBase` | Needed for test schema creation |
| `capture/mock/run.py` | Mock capture script | Reference for `to_orm()` + async session write pattern |
| `api/services/live_pipeline.py` | In-process mock pipeline | Reference for `_capture_stage` DB write pattern |
| `tests/test_mock_pipeline.py` | Mock pipeline tests | Reference for async DB test fixture pattern |
| `tests/test_contracts.py` | Contract tests | Reference for `TransmissionPacket` construction assertions |
| `specs/capture_transplant/overview.md` | Master spec | Full behavioral description of all modules |
| `specs/capture_transplant/step_one.md` | This step's spec | Exact scope, files, done criteria |

### Post-build

| File | What it will be | Why it's needed |
|------|----------------|-----------------|
| `capture/trunked_radio/__init__.py` | Package init | Makes `capture.trunked_radio` importable |
| `capture/trunked_radio/config.py` | Shared configuration | ZMQ ports, timeouts, WAV dir, SDR params — single source of truth |
| `capture/trunked_radio/models.py` | Internal dataclasses | `MetadataEvent`, `LaneAssignment`, `ActiveCall`, `CompletedCall` |
| `capture/trunked_radio/tsbk.py` | TSBK binary parser | Standalone P25 decoder, GPL v3 |
| `capture/trunked_radio/buffer_manager.py` | Call state machine | PCM accumulation, timeout detection, lane reassignment |
| `capture/trunked_radio/wav_writer.py` | WAV file writer | Mono int16 8000 Hz output |
| `capture/trunked_radio/packet_builder.py` | CompletedCall → TransmissionPacket | Maps internal model to contract |
| `capture/trunked_radio/packet_sink.py` | Async packet emission | ZmqPacketSink, StdoutPacketSink, JsonlPacketSink |
| `capture/trunked_radio/backend.py` | Backend async event loop | Process 3 entry point — ZMQ pull, buffer management, WAV + DB + push |
| `tests/test_tsbk.py` | TSBK parser tests | Binary decoding, frequency resolution, all opcodes |
| `tests/test_buffer_manager.py` | Buffer manager tests | Grant handling, PCM accumulation, timeout, lane reassignment, drain |
| `tests/test_wav_writer.py` | WAV writer tests | Output format and filename convention |
| `tests/test_packet_builder.py` | Packet builder tests | Field mapping, `to_orm()` output |
| `tests/test_capture_backend.py` | Backend integration tests | `_finalize_calls` with mock ZMQ — verify DB rows + WAV files |

## Plan

### Step 1: Package init + config

**Files:** `capture/trunked_radio/__init__.py`, `capture/trunked_radio/config.py`

Create the package directory. `__init__.py` is empty.

`config.py` defines module-level constants:
- ZMQ ports: `PCM_PORT = 5580`, `CONTROL_PORT = 5581`, `PACKET_PUSH_PORT = 5590` (backend-side only; ports 5557, 5560-5567 are Process 1/2, built later)
- Timeouts: `INACTIVITY_TIMEOUT = 1.5` (seconds), `SWEEP_INTERVAL = 0.5` (seconds), `POLL_TIMEOUT = 10` (ms)
- WAV dir: `CAPTURE_WAV_DIR = os.environ.get("CAPTURE_WAV_DIR", "data/wav")`
- Sample rate: `SAMPLE_RATE = 8000`
- Read from `os.environ` where noted, with hardcoded defaults

### Step 2: Internal dataclass models

**Files:** `capture/trunked_radio/models.py`

Define `@dataclass` types (not Pydantic — hot path):

- `MetadataEvent`: `type: str`, `tgid: int | None`, `frequency: int | None`, `source_unit: int | None`, `lane_id: int | None`, `timestamp: float`
- `LaneAssignment`: `lane_id: int`, `tgid: int`, `frequency: int | None`, `source_unit: int | None`
- `ActiveCall`: `tgid: int`, `lane_id: int`, `frequency: int | None`, `source_unit: int | None`, `start_time: datetime`, `last_pcm_at: float`, `pcm_chunks: list[bytes]` (field with `default_factory=list`). Method `total_pcm_bytes() -> int` for convenience.
- `CompletedCall`: `tgid: int`, `lane_id: int`, `frequency: int | None`, `source_unit: int | None`, `start_time: datetime`, `end_time: datetime`, `end_reason: str`, `audio_bytes: bytes`, `call_id: str` (UUID, assigned on creation). Property `duration_seconds -> float`.

`source_unit` is `int | None` on all models. Never string.

### Step 3: TSBK parser

**Files:** `capture/trunked_radio/tsbk.py`

Standalone module. No Albatross imports. GPL v3 attribution header.

`TSBKParser` class with:
- `__init__()`: initializes `self.freq_table: dict[int, dict]` (keyed by table ID 0-15)
- `decode(data: bytes) -> dict | None`: takes 12-byte raw TSBK (2-byte NAC + 10-byte body), returns structured dict or None for unhandled opcodes
- Internal methods per opcode:
  - `_decode_grant(body)` → opcode 0x00: extracts tgid, channel_id, srcaddr. Returns `{"type": "grant", "opcode": 0x00, "nac": ..., "tgid": ..., "frequency": ..., "srcaddr": ..., "channel_id": ..., "tdma_slot": None}`
  - `_decode_grant_update(body)` → opcode 0x02: two tgid/freq pairs, no srcaddr. Returns `{"type": "grant_update", ...}` with `tgid`, `frequency`, `tgid2`, `frequency2`
  - `_decode_grant_update_explicit(body)` → opcode 0x03
  - `_decode_iden_up(body)` → opcodes 0x33, 0x34, 0x3d: populates `self.freq_table[table_id]` with `base_freq`, `step`, `offset`
- `_resolve_frequency(channel_id: int) -> int | None`: bits 15-12 select table entry, bits 11-0 are channel number. Returns `base + (step * channel_number)` in Hz, or None if table entry missing.
- `process_qmsg(msg) -> dict | None`: convenience wrapper that checks `msg.type() == 7`, extracts bytes, calls `decode()`. This method is for Process 1 integration (Step 3) but define it now for completeness — it just delegates to `decode()`.

Key: `srcaddr` is the output field name (P25 domain). It is always `int | None`, never string.

### Step 4: Buffer manager

**Files:** `capture/trunked_radio/buffer_manager.py`

`BufferManager` class:
- `__init__()`: `self.active_calls: dict[int, ActiveCall]` keyed by tgid
- Constants: `GRANT_EVENT_TYPES = {"grant", "grant_update"}`, `RELEASE_EVENT_TYPES = set()`
- `handle_metadata(event: MetadataEvent) -> list[CompletedCall]`: if event type in `GRANT_EVENT_TYPES`, delegate to `_grant_or_update()`. Returns list of calls closed by lane reassignment (0 or 1).
- `_grant_or_update(event: MetadataEvent) -> list[CompletedCall]`:
  - If event has a `lane_id` and another tgid already occupies that lane, close the prior call with `end_reason="lane_reassigned"`, return it
  - If tgid already has an active call, update its metadata (frequency, source_unit, lane_id)
  - Otherwise open a new `ActiveCall`
- `handle_pcm(tgid: int, pcm_data: bytes, lane_id: int, frequency: int | None, source_unit: int | None, timestamp: float) -> None`:
  - If tgid has an active call, append pcm_data, update `last_pcm_at`
  - Otherwise open a new `ActiveCall` from the PCM header fields, append pcm_data
- `sweep(now: float, timeout: float) -> list[CompletedCall]`: iterate active calls, close any where `now - last_pcm_at > timeout` with `end_reason="inactivity_timeout"`
- `drain() -> list[CompletedCall]`: close all remaining active calls with `end_reason="inactivity_timeout"`
- `_close_call(tgid: int, reason: str) -> CompletedCall`: remove from `active_calls`, join `pcm_chunks` into `audio_bytes`, return `CompletedCall`

### Step 5: WAV writer

**Files:** `capture/trunked_radio/wav_writer.py`

`WavWriter` class:
- `__init__(output_dir: str | Path)`: stores output dir, creates it (`mkdir(parents=True, exist_ok=True)`) on init
- `write(call: CompletedCall) -> Path`: writes WAV using stdlib `wave` module. Parameters: 1 channel, 2 bytes/sample (`sampwidth=2`), 8000 Hz. Filename: `{call.start_time.strftime("%Y%m%dT%H%M%S")}_{call.tgid}_{call.source_unit or "unknown"}_{call.call_id}.wav`. Returns absolute path to written file.

### Step 6: Packet builder

**Files:** `capture/trunked_radio/packet_builder.py`

`build_packet(call: CompletedCall, wav_path: Path) -> TransmissionPacket`:

A single function (not a class — there's no state). Imports `TransmissionPacket` from `contracts.models`. Maps fields per the spec:

- `id`: `str(uuid4())`
- `timestamp`: `call.start_time.isoformat()`
- `talkgroup_id`: `call.tgid`
- `source_unit`: `call.source_unit` (int | None)
- `frequency`: `float(call.frequency)` if not None, else `0.0`
- `duration`: `call.duration_seconds`
- `encryption_status`: `False`
- `audio_path`: `str(wav_path)`
- `metadata`: `{"system": "p25_phase1", "lane_id": call.lane_id, "end_reason": call.end_reason, "sample_rate": 8000}`

### Step 7: Packet sink

**Files:** `capture/trunked_radio/packet_sink.py`

Define an async `PacketSink` protocol (using `typing.Protocol` or `abc.ABC`):

```
class PacketSink(Protocol):
    async def emit(self, packet: TransmissionPacket) -> None: ...
    async def close(self) -> None: ...
```

Three implementations:

- `ZmqPacketSink`: `__init__(port: int = 5590)`, creates `zmq.asyncio.Context` + PUSH socket bound to `tcp://*:{port}`. `emit()` serializes packet via `packet.model_dump_json()` and sends. `close()` closes socket + context.
- `StdoutPacketSink`: `emit()` prints `packet.model_dump_json()` to stdout. `close()` is a no-op.
- `JsonlPacketSink`: `__init__(path: Path)`, opens file on first `emit()`. `emit()` writes one JSON line. `close()` closes file.

All three are async wrappers — `StdoutPacketSink` and `JsonlPacketSink` wrap sync I/O in async methods (no thread offload needed for these debug sinks).

### Step 8: Backend event loop

**Files:** `capture/trunked_radio/backend.py`

`CaptureBackend` class:

- `__init__(sink: PacketSink | None = None)`: creates `BufferManager`, `WavWriter(config.CAPTURE_WAV_DIR)`, stores sink (defaults to `StdoutPacketSink` if None)
- `async run()`: main loop
  1. Create `zmq.asyncio.Context`
  2. Create PULL sockets on `tcp://*:5580` (PCM) and `tcp://*:5581` (control/metadata)
  3. Create `zmq.asyncio.Poller`, register both sockets
  4. Loop: `poll(timeout=10)`, dispatch PCM frames to `_handle_pcm()`, metadata frames to `_handle_metadata()`
  5. Every 0.5s: `_sweep_timeouts()`
  6. On `KeyboardInterrupt` or `asyncio.CancelledError`: `_drain_and_finalize()`
  7. Close sockets, context, sink
- `_handle_pcm(frames: list)`: parse multipart — `frames[0]` is JSON header (`lane_id`, `tgid`, `freq`, `source_unit`, `ts`), `frames[1]` is raw PCM bytes. Call `buffer_manager.handle_pcm(...)`.
- `_handle_metadata(data: bytes)`: parse JSON into `MetadataEvent`. Call `buffer_manager.handle_metadata(event)`. Finalize any returned completed calls.
- `_sweep_timeouts()`: call `buffer_manager.sweep(time.time(), config.INACTIVITY_TIMEOUT)`. Finalize returned calls.
- `_drain_and_finalize()`: call `buffer_manager.drain()`. Finalize all returned calls.
- `async _finalize_calls(calls: list[CompletedCall])`: for each call:
  1. `wav_path = self.wav_writer.write(call)`
  2. `packet = build_packet(call, wav_path)`
  3. `orm_obj = packet.to_orm()`
  4. Write to DB: `async with AsyncSessionLocal() as session: async with session.begin(): session.add(orm_obj)`
  5. `await self.sink.emit(packet)`

`if __name__ == "__main__"` block: `asyncio.run(CaptureBackend().run())`

### Step 9: Tests

**Files:** `tests/test_tsbk.py`, `tests/test_buffer_manager.py`, `tests/test_wav_writer.py`, `tests/test_packet_builder.py`, `tests/test_capture_backend.py`

Follow existing patterns: `pytest`, `pytest-asyncio`, in-memory SQLite for DB tests.

**`tests/test_tsbk.py`:**
- Test grant decode (opcode 0x00): construct 12-byte message, verify tgid, srcaddr, channel_id fields
- Test grant update decode (opcode 0x02): two tgid/freq pairs
- Test iden_up decode (opcode 0x3d): verify freq table populated
- Test frequency resolution: seed freq table, decode a grant, verify frequency = base + step * channel_number
- Test unknown opcode returns None
- Test NAC extraction

**`tests/test_buffer_manager.py`:**
- Test PCM opens new call: `handle_pcm()` with unknown tgid creates ActiveCall
- Test PCM appends to existing call: second `handle_pcm()` appends chunk
- Test inactivity timeout: `sweep()` closes call after 1.5s gap
- Test grant opens new call: `handle_metadata()` with grant event
- Test lane reassignment: grant assigns new tgid to occupied lane, prior call returned as CompletedCall with `end_reason="lane_reassigned"`
- Test drain: `drain()` returns all active calls
- Test sweep with no timeouts returns empty list

**`tests/test_wav_writer.py`:**
- Write a CompletedCall, read back WAV with `wave.open()`, verify: nchannels=1, sampwidth=2, framerate=8000, nframes matches audio_bytes length
- Verify filename contains tgid and ISO timestamp
- Verify output directory created if missing (use `tmp_path` fixture)

**`tests/test_packet_builder.py`:**
- Build packet from CompletedCall, verify all TransmissionPacket fields match
- Verify `metadata` dict contains system, lane_id, end_reason, sample_rate
- Call `to_orm()` on result, verify `status="captured"`, `text is None`, talkgroup_id matches
- Verify source_unit=None handled correctly

**`tests/test_capture_backend.py`:**
- Test `_finalize_calls` end-to-end: construct a `CompletedCall`, call `_finalize_calls`, verify:
  - WAV file exists on disk (use `tmp_path` for WAV dir)
  - `Transmission` row in DB with `status="captured"` and correct field values
  - Sink received the packet
- Use in-memory SQLite + mock sink (record sent packets)
- Mock ZMQ context/sockets for backend instantiation (or test `_finalize_calls` directly without the event loop)

## Testing

Run all new tests with:
```bash
python -m pytest tests/test_tsbk.py tests/test_buffer_manager.py tests/test_wav_writer.py tests/test_packet_builder.py tests/test_capture_backend.py -v
```

Verify backend starts:
```bash
python -m capture.trunked_radio.backend
```
(Should block waiting for ZMQ connections — this is correct behavior.)

Existing tests must continue to pass: `python -m pytest tests/ -v`

## Doc Updates

After this step is built, update:
- `CLAUDE.md` — Add `capture/trunked_radio/` to the Architecture section, document the new test files, update test count
