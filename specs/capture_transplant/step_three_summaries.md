# Summaries: Capture Transplant — Step 3 (Flowgraph)

_Spec: `specs/capture_transplant/step_three.md` — reviewed against repo on 2026-04-06_

## Current State

The `capture/trunked_radio/` package has two of three processes built:

**Process 3 (Backend)** is complete: `backend.py` runs an async ZMQ event loop pulling tagged PCM from :5580 and metadata from :5581. `BufferManager` accumulates PCM per talkgroup, detects call boundaries via inactivity timeout (1.5s) or lane reassignment, and closes calls to `CompletedCall`. `_finalize_calls` writes WAV files via `WavWriter`, builds `TransmissionPacket` via `packet_builder.build_packet()`, writes `Transmission` rows to the DB, and emits packets via `PacketSink`.

**Process 2 (Bridge)** is complete: `bridge.py` runs three types of daemon threads. `MetadataSubscriber` pulls JSON from :5557, updates `LaneState` for grant events, translates `srcaddr` → `source_unit`, and forwards metadata to :5581. Eight `PCMLaneSubscriber` threads pull raw PCM from :5560-5567, look up the lane's tgid in `LaneState`, and push tagged multipart PCM to :5580.

**Process 1 (Flowgraph)** does not exist. Nothing currently produces metadata JSON on :5557 or PCM on :5560-5567. The `TSBKParser` in `tsbk.py` can decode raw binary TSBKs and has a `process_qmsg()` method for `gr.msg_queue` integration, but there is no flowgraph to feed it. There is no lane manager to assign voice channels to talkgroups, no metadata poller to bridge the `gr.msg_queue` to ZMQ, and no GNU Radio `top_block`.

`config.py` has backend ports (5580, 5581, 5590), bridge ports (5557, 5560-5567), lane count (8), timeouts, and audio constants. It has no SDR parameters or flowgraph-specific constants.

## Target State

After this step, all three capture processes exist. `capture/trunked_radio/` gains three new modules:

**`lane_manager.py`** — Pure logic, no GNU Radio dependency. `LaneManager` tracks which of 8 voice lanes are assigned to which talkgroups. Thread-safe (all methods locked). `on_grant(tgid, freq, srcaddr)` handles grant allocation: if the tgid already has a lane, update it (retune if freq changed); if another tgid holds a lane on the same frequency, preempt it; otherwise allocate a free lane; if no free lanes, return None. `sweep_stale(max_age)` releases lanes whose tgid hasn't been seen in the grant stream for `max_age` seconds (default 5s), returning the list of released tgids. A `retune_callback` is set by the flowgraph — called with `(lane_id, freq)` when a lane needs retuning. Internally, each lane tracks `tgid`, `freq`, `srcaddr`, and `last_seen` timestamp.

**`metadata_poller.py`** — Daemon thread bridging `gr.msg_queue` → TSBK parser → lane manager → ZMQ. Drains the message queue in a non-blocking loop (5ms sleep on empty). Calls `TSBKParser.process_qmsg()` on each message. For grants/grant_updates, calls `LaneManager.on_grant()`, annotates the parsed event dict with the returned `lane_id`, and pushes the JSON to ZMQ PUSH on :5557. Periodically (every ~2s) calls `LaneManager.sweep_stale()`. The poller is the component that produces the metadata JSON the bridge consumes.

**`flowgraph.py`** — GNU Radio `gr.top_block` subclass. SDR source via `osmosdr.source()` centered at 855.75 MHz, 3.2 Msps. One control lane: channelizer (decim=50, offset to control channel) → FM demod → `p25_demod_fb` → frame assembler → `gr.msg_queue`. Eight voice lanes: channelizer → FM demod → `p25_demod_fb` → frame assembler → ZMQ push sink on :5560+lane_id. The flowgraph instantiates `LaneManager` and `MetadataPoller`, wiring the retune callback to each voice lane's `freq_xlating_fir_filter.set_center_freq()`. `p25_demod_fb` is imported from OP25's app directory via `sys.path` (configurable via `OP25_APPS_DIR` env var). Entry point: `python -m capture.trunked_radio.flowgraph`.

`config.py` gains SDR and flowgraph constants: center frequency, sample rate, gains, control channel offset, channel filter parameters, and stale sweep timing.

`tsbk.py` gets a one-line fix: `process_qmsg` calls `msg.to_string()` instead of `msg.to_bytes()` to match GNU Radio's actual `gr.message` API.

One new test file: `tests/test_lane_manager.py` covers grant allocation, frequency preemption, pool exhaustion, stale sweep, and retune callback invocation. `LaneManager` is pure logic — fully testable without GNU Radio.
