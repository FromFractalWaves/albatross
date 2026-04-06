# Capture Transplant — Step 3: Flowgraph

_Sub-spec of `specs/capture_transplant.md` (the master spec)._

_Depends on: Step 1 (config.py, models.py, tsbk.py must exist)._

## Scope

Build the flowgraph process (Process 1). This is the GNU Radio flowgraph that tunes an RTL-SDR, decodes the P25 control channel, and runs 8 pooled voice channelizers. It has hard external dependencies: GNU Radio 3.10+, gr-osmosdr, gr-op25 (boatbod fork), and a physical RTL-SDR dongle.

After this step, all three capture processes exist and can be run together against live RF.

## Files

| File | What it is |
|------|-----------|
| `capture/trunked_radio/lane_manager.py` | Thread-safe lane allocation — tracks voice lane → talkgroup assignments |
| `capture/trunked_radio/metadata_poller.py` | Daemon thread — drains `gr.msg_queue`, parses TSBKs, forwards via ZMQ |
| `capture/trunked_radio/flowgraph.py` | GNU Radio top_block — SDR source, control lane, voice lanes, ZMQ sinks |

Tests:

| File | What it covers |
|------|---------------|
| `tests/test_lane_manager.py` | Grant allocation, frequency preemption, pool exhaustion, stale sweep |

Note: `lane_manager.py` is pure logic with threading — fully testable without GNU Radio. The flowgraph and metadata poller are hardware-gated and are validated on-air, not in CI.

## What to Build

Refer to the master spec's **Process 1: Flowgraph** section. Key components:

### Lane Manager

Pure logic, no GNU Radio dependency. Thread-safe (locked).

- `on_grant(tgid, freq, srcaddr) → lane_id | None` — grant handling: existing tgid → update/retune, same freq → preempt, else allocate free, else drop.
- `sweep_stale(max_age) → list[released_tgids]` — release lanes not seen in grant stream for `max_age` seconds.
- `retune_callback(lane_id, freq)` — called when a lane needs retuning; the flowgraph wires this to `freq_xlating_fir_filter.set_center_freq()`.

### Metadata Poller

Daemon thread bridging `gr.msg_queue` → TSBK parser → lane manager → ZMQ.

- Drains `gr.msg_queue` (non-blocking, 5ms sleep on empty).
- Calls `TSBKParser.process_qmsg()` from Step 1's `tsbk.py`.
- For grants/grant_updates: calls `LaneManager.on_grant()`, annotates event with `lane_id`.
- Pushes parsed event JSON to ZMQ PUSH on `:5557`.
- Periodically calls `LaneManager.sweep_stale()` (~2s interval).

### Flowgraph

GNU Radio `gr.top_block` subclass. See master spec for full signal chain details:

- SDR source: `osmosdr.source()` centered at 855.75 MHz, 3.2 Msps.
- Control lane: channelizer → FM demod → `p25_demod_fb` → frame assembler → `gr.msg_queue`.
- Voice lanes (×8): channelizer → FM demod → `p25_demod_fb` → frame assembler → ZMQ push sink on `:5560+lane_id`.
- `p25_demod_fb` is imported from OP25 apps via `sys.path`. Should be vendored or extracted.

## What NOT to Build

- Anything in `capture/trunked_radio/` already built in Steps 1-2
- Any API-side integration

## Done When

1. `python -m pytest tests/test_lane_manager.py -v` — all pass
2. Lane manager correctly handles: assign, retune on freq change, preempt on same freq, pool exhaustion, stale sweep
3. `python -m capture.trunked_radio.flowgraph` starts the GNU Radio flowgraph (requires hardware)
4. MetadataPoller decodes TSBKs and pushes JSON to `:5557`
5. Voice lanes output PCM to `:5560-5567`
6. All three processes can run together: flowgraph → bridge → backend → WAV files + DB rows