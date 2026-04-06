# Summaries: Capture Transplant Step 2 (Bridge)

_Spec: `specs/capture_transplant/step_two.md` — reviewed against repo on 2026-04-06_

## Current State

The capture backend (Process 3) is fully built and tested. It pulls tagged PCM multipart from `:5580` and metadata JSON from `:5581`, accumulates PCM per talkgroup, detects call boundaries, writes WAV files, and emits `TransmissionPacket`s.

`config.py` defines backend-side ZMQ ports (5580, 5581, 5590), timeouts, and audio constants. `models.py` defines four dataclasses: `MetadataEvent`, `LaneAssignment`, `ActiveCall`, `CompletedCall`. The `MetadataEvent` model already uses `source_unit` (not `srcaddr`) — the P25→Albatross field rename happens at deserialization time.

There is no bridge process. Nothing currently produces the tagged multipart PCM on `:5580` or forwarded metadata on `:5581` that the backend expects. The flowgraph (Process 1) is also not built — it will produce raw metadata JSON on `:5557` and raw PCM on `:5560-5567`. The bridge is the missing link between these two.

`config.py` has no constants for the bridge's upstream ports (`:5557` metadata input, `:5560-5567` PCM lane inputs) or lane count.

## Target State

The bridge process (`capture/trunked_radio/bridge.py`) runs as a standalone process between the flowgraph and backend. It has three concurrent components, all running as daemon threads:

**LaneState** is a thread-safe mapping of `lane_id → {tgid, freq, source_unit}`. It is the bridge's core data structure — metadata events write to it, PCM subscribers read from it.

**MetadataSubscriber** pulls JSON from `:5557` (flowgraph output). For grant/grant_update events (matched via `msg.get("type")`), it updates LaneState — setting the tgid, frequency, and source_unit for the assigned lane. It translates `srcaddr` from the raw JSON into `source_unit` at this boundary. All messages are forwarded as-is to `:5581` for the backend.

**PCMLaneSubscriber** (one per lane, 8 total) pulls raw int16 PCM from `:5560+lane_id`. On each chunk, it looks up the lane's current tgid in LaneState. If no tgid is assigned, the PCM is dropped. Otherwise, it wraps the PCM in a ZMQ multipart message (Part 0: JSON header with `lane_id`, `tgid`, `freq`, `source_unit`, `ts`; Part 1: raw PCM bytes) and pushes to `:5580`.

`config.py` gains bridge-side constants: `METADATA_PORT = 5557`, `NUM_LANES = 8`, `PCM_BASE_PORT = 5560`, and helper functions `pcm_endpoint(lane_id)` and `metadata_endpoint()`.

The bridge has no Albatross dependencies — it does not import from `contracts/` or `db/`. It is pure coordination logic connecting Process 1 to Process 3.

Entry point: `python -m capture.trunked_radio.bridge` starts the bridge and blocks until interrupted.
