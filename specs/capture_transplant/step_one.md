# Capture Transplant — Step 1: Backend + Shared Modules

_Sub-spec of `specs/capture_transplant.md` (the master spec)._

## Scope

Build the backend process (Process 3) and all shared modules it depends on. This is the Albatross integration point — the only capture process that imports from `contracts/` and `db/`. Everything in this step is testable without GNU Radio, an RTL-SDR, or live ZMQ sockets.

After this step, you can feed fake ZMQ messages to the backend and get real `TransmissionPacket` rows in the database + WAV files on disk.

## Files

All files live in `capture/trunked_radio/`. The `capture/mock/` directory is untouched.

| File | What it is |
|------|-----------|
| `__init__.py` | Package init |
| `config.py` | Shared configuration: ZMQ ports, SDR params, timeouts, WAV output dir |
| `models.py` | Internal dataclasses: `MetadataEvent`, `LaneAssignment`, `ActiveCall`, `CompletedCall` |
| `tsbk.py` | TSBK parser — decodes binary P25 TSBKs into structured dicts (GPL v3, standalone) |
| `buffer_manager.py` | Call state machine — accumulates PCM per tgid, detects boundaries |
| `wav_writer.py` | Writes `CompletedCall` audio to mono int16 WAV files |
| `packet_builder.py` | Maps `CompletedCall` → `TransmissionPacket` using the existing contract |
| `packet_sink.py` | Async `PacketSink` protocol + `ZmqPacketSink`, `StdoutPacketSink`, `JsonlPacketSink` |
| `backend.py` | Backend async event loop — pulls from ZMQ, manages buffers, writes WAV + DB + push |

Tests:

| File | What it covers |
|------|---------------|
| `tests/test_tsbk.py` | Binary TSBK decoding, frequency resolution, all opcodes |
| `tests/test_buffer_manager.py` | Grant handling, PCM accumulation, timeout, lane reassignment, drain |
| `tests/test_wav_writer.py` | WAV file output format and filename convention |
| `tests/test_packet_builder.py` | `CompletedCall` → `TransmissionPacket` field mapping, `to_orm()` |
| `tests/test_capture_backend.py` | Backend `_finalize_calls`: mock ZMQ, verify DB rows + WAV files |

## What to Build

Refer to the master spec (`specs/capture_transplant.md`) for the full behavioral description of each module. Key sections:

- **Integration Contract** — `TransmissionPacket` field mapping, `to_orm()` pattern, push-only data flow
- **Event Type Canonicalization** — `GRANT_EVENT_TYPES = {"grant", "grant_update"}`, `RELEASE_EVENT_TYPES = set()`
- **Process 3: Backend** — Buffer Manager, WAV Writer, Packet Builder, Packet Emission, Event Loop
- **TSBK Parser** (under Process 1, but is a standalone module with no GNU Radio dependency)

### Design decisions locked in the master spec

- `source_unit` is `int | None` throughout — never string. The TSBK parser outputs `srcaddr` (int); capture models use `source_unit`.
- Event types are canonical: `"grant"`, `"grant_update"`. No release event types.
- Backend is async: `zmq.asyncio.Context`, `zmq.asyncio.Poller`. Entry point: `asyncio.run()`.
- `PacketSink` protocol is async. Debug sinks are async wrappers around sync I/O.
- Internal models are `@dataclass`, not Pydantic — they're in the hot path.
- DB writes use `packet.to_orm()` + `AsyncSessionLocal` from `db/session.py`.
- WAV output dir is configurable via `CAPTURE_WAV_DIR` env var, default `data/wav/`.

## What NOT to Build

- `lane_manager.py` — used by Process 1 (flowgraph), built in Step 3
- `metadata_poller.py` — used by Process 1, built in Step 3
- `flowgraph.py` — Process 1, built in Step 3
- `bridge.py` — Process 2, built in Step 2
- Any API-side ZMQ subscriber or pipeline manager integration

## Done When

1. `python -m pytest tests/test_tsbk.py tests/test_buffer_manager.py tests/test_wav_writer.py tests/test_packet_builder.py tests/test_capture_backend.py -v` — all pass
2. The backend can be started with `python -m capture.trunked_radio.backend` (will block waiting for ZMQ connections, which is correct)
3. `_finalize_calls` writes a `Transmission` row with `status="captured"` and correct field values
4. WAV files are written with correct format (mono int16, 8000 Hz)
5. `TransmissionPacket.metadata` contains `system`, `lane_id`, `end_reason`, `sample_rate`