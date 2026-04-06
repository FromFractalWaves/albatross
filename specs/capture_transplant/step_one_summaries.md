# Summaries: Capture Transplant — Step 1 (Backend + Shared Modules)

_Spec: `specs/capture_transplant/step_one.md` — reviewed against repo on 2026-04-06_

## Current State

The Albatross capture stage has one implementation: `capture/mock/`, a standalone script that reads canned JSON (`packets_radio.json`) and writes `Transmission` rows to the database. The in-process mock pipeline (`api/services/live_pipeline.py`) follows the same pattern but runs inside the API as three async stages connected by `PacketQueue`s.

The data handoff pattern is established: build a `TransmissionPacket` (Pydantic, from `contracts/models.py`), call `to_orm()` to get a `Transmission` ORM object with `status="captured"` and `text=None`, then write it via `AsyncSessionLocal` from `db/session.py`. The `Transmission` model has flat capture fields (talkgroup_id, source_unit, frequency, duration, encryption_status, audio_path) but no `metadata` column — P25-specific metadata lives on the `TransmissionPacket` Pydantic object and is pushed downstream via ZMQ, not stored in the DB.

The `capture/trunked_radio/` package does not exist. There is no TSBK parser, buffer manager, WAV writer, packet builder, or packet sink anywhere in the repo. No `data/wav/` directory exists.

Tests use `pytest` with `pytest-asyncio`. Async DB tests create in-memory SQLite engines via `create_async_engine("sqlite+aiosqlite://")`, build schema with `Base.metadata.create_all`, and use `async_sessionmaker` fixtures. All LLM calls are mocked. The test suite has 58 tests across 9 files in `tests/`.

## Target State

After this step, `capture/trunked_radio/` exists as a Python package with 9 modules (excluding the 3 deferred to Steps 2 and 3):

- **`config.py`** — Shared constants: ZMQ ports (5580 PCM, 5581 control, 5590 packet push), SDR params, timeouts (1.5s inactivity, 0.5s sweep interval, 10ms poll), WAV output dir (`CAPTURE_WAV_DIR` env var, default `data/wav/`).
- **`models.py`** — `@dataclass` internal types: `MetadataEvent`, `LaneAssignment`, `ActiveCall` (accumulates PCM byte chunks), `CompletedCall` (joined audio_bytes + metadata). Not Pydantic — hot path.
- **`tsbk.py`** — Standalone TSBK binary parser. Decodes 12-byte P25 TSBKs into structured dicts. Maintains a frequency table (populated from `iden_up` opcodes). Handles opcodes 0x00, 0x02, 0x03, 0x33, 0x34, 0x3d. Outputs `srcaddr` as int. GPL v3, attributed.
- **`buffer_manager.py`** — Call state machine keyed by tgid. Opens `ActiveCall` on grant or first PCM. Appends PCM chunks. Closes to `CompletedCall` on inactivity timeout (1.5s) or lane reassignment. `GRANT_EVENT_TYPES = {"grant", "grant_update"}`, `RELEASE_EVENT_TYPES = set()`.
- **`wav_writer.py`** — Writes `CompletedCall` audio as mono int16 WAV (8000 Hz). Filename: `{ISO8601}_{tgid}_{source_unit}_{uuid}.wav`. Creates output dir if needed.
- **`packet_builder.py`** — Maps `CompletedCall` to `TransmissionPacket` using the existing contract. Sets `metadata` dict with `system`, `lane_id`, `end_reason`, `sample_rate`.
- **`packet_sink.py`** — Async `PacketSink` protocol + three implementations: `ZmqPacketSink` (PUSH to :5590), `StdoutPacketSink`, `JsonlPacketSink`.
- **`backend.py`** — Async event loop using `zmq.asyncio`. Pulls from :5580 (PCM multipart) and :5581 (metadata JSON) via `zmq.asyncio.Poller` with 10ms timeout. Feeds events to `BufferManager`. Every 0.5s sweeps timed-out calls. `_finalize_calls` writes WAV via `WavWriter`, builds packet via `PacketBuilder`, writes `Transmission` row via `to_orm()` + `AsyncSessionLocal`, pushes via `PacketSink`. Drains on shutdown. Entry point: `python -m capture.trunked_radio.backend`.

Five new test files in `tests/` cover: TSBK binary decoding, buffer manager state transitions, WAV output format, packet field mapping, and backend finalization with mock ZMQ. All testable without GNU Radio, RTL-SDR, or live sockets. Feeding fake ZMQ messages to the backend produces real `Transmission` rows in the database and WAV files on disk.
