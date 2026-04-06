# Misalignments: Capture Transplant — Step 3 (Flowgraph)

_Spec: `specs/capture_transplant/step_three.md` — reviewed against repo on 2026-04-06_

## process_qmsg uses wrong method name for gr.message

- **Spec says:** MetadataPoller calls `TSBKParser.process_qmsg()` which "extracts bytes" from a `gr.msg_queue` message.
- **Repo reality:** `tsbk.py:142` calls `msg.to_bytes()`, but GNU Radio's `gr.message` objects expose `.to_string()` (which returns `bytes` in Python 3). There is no `.to_bytes()` method on `gr.message`.
- **Resolution:** The build plan fixes `process_qmsg` to call `msg.to_string()` instead of `msg.to_bytes()`. This is a one-line fix in the existing `tsbk.py`.

## config.py has no SDR or flowgraph constants

- **Spec says:** SDR parameters are center_freq=855.75 MHz, sample_rate=3.2 Msps, gain=30 dB, IF gain=20 dB, BB gain=20 dB. Control channel offset is -1,137,500 Hz. Channel filter: 6250 Hz cutoff, 1500 Hz transition. Voice channel count uses `NUM_LANES = 8` (already exists). Stale sweep interval for LaneManager is ~2 seconds with max_age=5 seconds.
- **Repo reality:** `config.py` has backend/bridge ZMQ ports, timeouts, audio constants, and bridge lane config. No SDR-related constants (center freq, sample rate, gains, control offset, filter params) or flowgraph timing constants (stale sweep interval, max stale age).
- **Resolution:** Step 3 adds flowgraph constants to `config.py`: SDR center freq, sample rate, gains, control channel offset, channel filter params, FM demod gain formula inputs, stale sweep interval (2s), and max stale age (5s).

## p25_demod_fb import path is unresolved

- **Spec says:** `p25_demod_fb` is imported from OP25 apps via `sys.path`. "Should be vendored or extracted."
- **Repo reality:** No OP25 code exists in the repo. The import path for `p25_demod_fb` and `op25_c4fm_mod` (needed for matched filter taps) is not established.
- **Resolution:** The flowgraph uses a configurable `OP25_APPS_DIR` env var (default: `/usr/local/lib/op25/apps`) added to `sys.path` at import time. This keeps the dependency external and avoids vendoring GPL code into the repo. The build plan documents this as a runtime requirement.

## MetadataPoller output must include lane_id for bridge consumption

- **Spec says:** MetadataPoller "annotates event with lane_id" and pushes to :5557. The bridge reads `msg.get("lane_id")` from the JSON.
- **Repo reality:** The TSBK parser outputs grants with no `lane_id` field — it has no concept of lanes. The bridge's `parse_grant()` reads `msg.get("lane_id")` and the `MetadataSubscriber` checks `if lane_id is not None` before updating LaneState.
- **Resolution:** The MetadataPoller calls `LaneManager.on_grant()` which returns a `lane_id`. The poller injects `lane_id` into the parsed event dict before pushing to ZMQ. This is exactly what the spec describes — just flagging that the `lane_id` field is synthesized by the poller, not parsed from the TSBK.
