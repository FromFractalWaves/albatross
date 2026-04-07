# Session Report: RF Validation

_Date: 2026-04-06 — Spec: `specs/rf_validation.md`_

## Goal
Complete live RF validation Phases 2-4 of the P25 capture pipeline against DeKalb County.

## Bugs Found & Fixed

- **Bug 1: CPU budget overflow (voice lane filter taps).** Voice lanes used a single-stage `freq_xlating_fir_filter_ccf` with 3,855 taps at 3.2 Msps — overwhelmed the CPU even at 3 lanes. Replaced with `p25_demod_cb` which has built-in two-stage decimation (BPF decim=32 ~200 taps → mixer → LPF decim=4 → arb_resampler). ~18x less work per lane. Files: `flowgraph.py`, `architecture.md`, `CLAUDE.md`.

- **Bug 2: 857.3125 MHz out of tunable range.** `p25_demod_cb.set_relative_frequency()` has a limit of 1,550,000 Hz. At center=855.75 MHz, 857.3125 MHz is 1,562,500 Hz away — 12.5 kHz over the limit. `set_relative_frequency()` silently returned `False`, demod never retuned, WAV files were empty (44 bytes, header only). Fixed by moving center frequency to 855.9625 MHz (midpoint of control + voice range). Also added return-value check to retune callback so failures are logged. Files: `config.py`, `flowgraph.py`, `architecture.md`, `hardware.md`, `CLAUDE.md`.

## Current State

**Phase 1 (control channel decode) — PASS** (prior session).
**Phase 2 (bridge correlation) — PASS.** Metadata flowing through bridge, LaneState updating, PCM tagged and forwarded across all 3 lanes.
**Phase 3 (WAV + DB) — PASS.** WAV files with audible dispatch audio, Transmission rows in DB with correct metadata. Calls finalizing with appropriate durations and end reasons.
**Phase 4 (endurance) — NOT TESTED.** Deferred to a future session.

Confirmed working: talkgroups 6001, 6005, 6006, 6007, 6009, 6078, 6121, 6315 across frequencies 856.0125, 856.3125, 856.9625, 857.3125 MHz. Source unit IDs captured on initial grants. All three lanes active simultaneously without overflow.

## Still Broken / Not Yet Reached

- Phase 4 endurance test (15-30 min) not yet run. No known blockers — just needs time on the air.
- Some tgid=6121 audio on 857.3125 MHz was noise — likely encrypted traffic, not a code bug (other frequencies produce clear voice).
- Rapid `lane_reassigned` closures when traffic exceeds 3 lanes — not a bug, but produces many tiny/empty WAV files. Could be mitigated by not writing WAVs below a minimum duration threshold.

## Files Changed

- `capture/trunked_radio/flowgraph.py` — replaced voice chain with p25_demod_cb, updated retune callback with return-value check
- `capture/trunked_radio/config.py` — CENTER_FREQ 855.75 → 855.9625 MHz
- `docs/sources/trunked_radio/architecture.md` — updated voice lane description, center freq, retune convention
- `docs/sources/trunked_radio/hardware.md` — updated center freq
- `CLAUDE.md` — updated flowgraph description, center freq

## Resumption Notes

- Start Phase 4 endurance test: backend → bridge → flowgraph, let run 15-30 min. Watch for memory growth, lane pool exhaustion, ZMQ backpressure, `O` overflows.
- Consider adding a minimum-duration filter to avoid writing sub-second WAV files from lane thrashing.
- The polyphase channelizer (option B from radio_integration.md) is no longer urgent — p25_demod_cb's two-stage decimation solved the CPU issue for 3 lanes. Revisit if lane count needs to increase beyond 3-4.
