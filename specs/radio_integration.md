# Radio Integration — Live RF Validation

*Status, findings, and next steps from the first live RF test session (2026-04-06).*

---

## Summary

The capture pipeline was tested against live P25 RF from DeKalb County for the first time. **Phase 1 (control channel decode) passed.** The flowgraph locks onto the control channel, decodes TSBKs, resolves frequencies, assigns lanes, and sweeps stale calls. Phases 2-4 (bridge, backend, endurance) have not been tested yet due to a CPU budget issue that must be resolved first.

---

## What Was Validated

### Control Channel Lock — PASS

- SDR: RTL-SDR Blog V4 (R828D tuner), system `python3`, GNU Radio 3.10.12
- Control channel at 854.6125 MHz locked within seconds
- 43 dB SNR confirmed via `rtl_power` scan
- TSBKs decoded continuously: grants, grant_updates, iden_up
- Frequency tables populated correctly (table 0 and table 1)
- Frequencies resolve to expected values (856.0125, 856.3125, 856.3375, 856.9625, 857.3125 MHz)
- Talkgroups match prototype observations (6002, 6005, 6006, 6007, 6009, 6121, 6122, 6241, 6256, 6296)
- Source unit IDs captured from initial grants (1011064, 1012635, 1013363, 1131115, 1239928, 6003047)
- Lane assignment and stale sweep working correctly

### Throughput (10-second window)

- 333 messages from msg_queue
- 333 TSBK frames (DUID 7)
- 73 decoded (grants + iden_up — remainder are unhandled opcodes like adjacency, RFSS status, etc.)

---

## Bugs Fixed During Session

### 1. `op25_repeater` import path
**Symptom:** `ModuleNotFoundError: No module named 'op25_repeater'`
**Root cause:** OP25 installs as `gnuradio.op25_repeater`, not bare `op25_repeater`.
**Fix:** `from gnuradio import op25_repeater`

### 2. `p25_demodulator` import chain
**Symptom:** `ModuleNotFoundError: No module named 'op25_c4fm_mod'`
**Root cause:** `p25_demodulator.py` imports `op25_c4fm_mod` from the `tx/` subdirectory of the OP25 apps dir, which wasn't on `sys.path`.
**Fix:** Add `os.path.join(config.OP25_APPS_DIR, "tx")` to `sys.path`.

### 3. `frame_assembler` API change
**Symptom:** `TypeError: __init__(): incompatible constructor arguments`
**Root cause:** The boatbod fork has two frame assembler classes: `frame_assembler` (new API: `options, debug, msgq_id, queue`) and `p25_frame_assembler` (old API: positional args for `do_imbe`, `do_output`, etc.). The spec used the wrong one.
**Fix:** Switch to `p25_frame_assembler` with explicit positional args.

### 4. TSBK parser bit layout
**Symptom:** No TSBKs decoded despite messages arriving.
**Root cause:** The parser assumed raw byte-level field offsets. OP25 packs TSBK bodies differently:
- `msg.type()` is `(protocol << 16 | DUID)`, not bare DUID — check was `!= 7` instead of `& 0xFFFF != 7`
- TSBK body is a 96-bit integer (10-byte body << 16 for missing CRC) — opcodes and fields are extracted via bit shifts, not byte offsets
- Opcode is bits 93-88 (6 bits after LB/protected flags), not `body[0]`
**Fix:** Complete rewrite of `tsbk.py` to use integer bit-shift extraction matching OP25's `tk_p25.py` convention.

### 5. `msg.to_string()` returns bytes
**Symptom:** `TypeError: ord() expected string of length 1, but int found`
**Root cause:** In Python 3 with these GR bindings, `msg.to_string()` returns `bytes`, not `str`.
**Fix:** Check `isinstance(s, bytes)` and skip `ord()` conversion.

### 6. Frequency offset sign inversion
**Symptom:** Demod running but only producing DUID 0xFFFF (no lock) messages.
**Root cause:** `p25_demod_cb.relative_freq` uses OP25's convention: `CENTER - CHANNEL` (positive when channel is below center). We were passing `CHANNEL - CENTER` (negative), which tuned to the mirror frequency on the wrong side of center.
**Fix:** Pass `-config.CONTROL_OFFSET` (i.e., `CENTER - CONTROL = +1137500 Hz`).

### 7. Control channel demod chain
**Symptom:** Even with correct offset, the original `freq_xlating_fir_filter → quadrature_demod_cf → p25_demod_fb` chain produced only no-lock messages.
**Root cause:** `p25_demod_fb` (float input) lacks AGC and FLL. Without automatic gain control and frequency tracking, the demod cannot lock onto the signal through typical RTL-SDR gain/frequency variations.
**Fix:** Switch control channel to `p25_demod_cb` (complex input), which includes AGC, FLL (frequency-locked loop), and the full OP25 demod chain internally.

---

## Current Blocker: CPU Budget

### Problem

Running 8 voice lane demod chains plus the control channel demod at 3.2 Msps exceeds the CPU budget on laptop hardware. GNU Radio prints `O` characters (buffer overflow indicators), samples are dropped, and the control channel demod loses lock within 10-30 seconds. The 10-second status window shows 333 msgs → 0 msgs as overflows cascade.

This happens with both approaches tried:
- **9× `p25_demod_cb`** — each processes 3.2 Msps through BPF + mixer + two-stage decim + AGC + FLL + FM demod + symbol recovery. Way too heavy.
- **1× `p25_demod_cb` + 8× channelizer chain** — the `freq_xlating_fir_filter` at 3.2 Msps with narrow cutoff (11 kHz at 3.2 MHz) produces ~4000+ taps per instance. 8 copies still overwhelm the CPU.

### Diagnosis

The core issue is that all voice lanes process the full 3.2 Msps input even when idle (tuned to offset 0). GNU Radio cannot conditionally skip processing — all connected blocks run at the source rate.

### Possible Solutions

These are ranked roughly by complexity:

**A. Reduce voice lane count.** Drop from 8 to 3-4 lanes. DeKalb County rarely has more than 3 simultaneous calls. This is the simplest fix but caps concurrent call capacity.

**B. Polyphase channelizer.** Use `gnuradio.filter.pfb.channelizer_ccf` to split the full band into N channels in one pass, instead of N independent `freq_xlating_fir_filter` instances. This is the standard GNU Radio approach for multi-channel receivers — O(N log N) via FFT instead of O(N × taps).

**C. Lower SDR sample rate.** The voice channels span 856.0-857.5 MHz, control is at 854.6 MHz. The required bandwidth is ~3 MHz. Dropping from 3.2 to 2.4 Msps would reduce per-block load by 25%, but won't fix the fundamental scaling issue.

**D. Idle lane gating.** Use `blocks.mute_cc` or `blocks.null_source` to stop processing on lanes with no active grant. Swap in a real connection when a grant arrives. This requires runtime graph modification (`lock()/unlock()`) which is fragile but possible.

**E. Separate SDR for control.** Use a second RTL-SDR at a lower sample rate (e.g., 256 ksps) dedicated to the control channel. The main SDR handles only voice. This eliminates the control channel as a CPU consumer and lets us optimize the voice pipeline independently.

### Recommended Path

Start with **(A)** — reduce to 3 lanes to unblock Phase 2/3/4 testing immediately. Then implement **(B)** as the proper fix. The polyphase channelizer is the right architecture for a multi-channel SDR receiver and is what production OP25 deployments use via `multi_rx.py`.

---

## Next Steps — Testing Phases 2-4

Once the CPU budget issue is resolved:

### Phase 2: Bridge Correlation

Start the bridge in a second terminal while the flowgraph is running.

```bash
python3 -m capture.trunked_radio.bridge
```

**Watch for:**
- Bridge connects to metadata on :5557 and PCM on :5560-5567
- Metadata flowing through (LaneState updating from grants)
- PCM being tagged with tgid and forwarded (not dropped)

**Key risk:** PCM may be dropped if LaneState hasn't seen a grant for that lane yet. This is expected for the first few seconds.

### Phase 3: Full Pipeline — WAV + DB

Start the backend in a third terminal.

```bash
source trm/.venv/bin/activate
python -m capture.trunked_radio.backend
```

**Watch for:**
- Calls being finalized (log lines with tgid, duration, end_reason)
- WAV files appearing in `data/wav/`
- `Transmission` rows in the database with `status="captured"`

**Verify:**
```bash
# Check WAV file properties
python -c "import wave; w = wave.open('data/wav/<file>.wav'); print(f'rate={w.getframerate()} frames={w.getnframes()} dur={w.getnframes()/w.getframerate():.1f}s')"

# Check database
source trm/.venv/bin/activate
python -c "
import asyncio
from db.session import AsyncSessionLocal
from db.models import Transmission
from sqlalchemy import select, func
async def check():
    async with AsyncSessionLocal() as s:
        count = await s.scalar(select(func.count()).select_from(Transmission).where(Transmission.status == 'captured'))
        print(f'{count} captured transmissions')
asyncio.run(check())
"
```

### Phase 4: Endurance (15-30 min)

Let all three processes run. Watch for memory growth, lane pool exhaustion, ZMQ backpressure, and WAV accumulation rate.

---

## Test Environment

| Item | Value |
|------|-------|
| Date | 2026-04-06 |
| Hardware | RTL-SDR Blog V4 (SN: 00000001), dipole antenna |
| OS | Linux 6.17.0-20-generic |
| GNU Radio | 3.10.12.0 |
| gr-osmosdr | 0.2.0.0 |
| gr-op25 | boatbod fork (built from /home/fractalwaves/clones/op25) |
| Python | 3.13 (system), pyzmq 26.4.0 |
| OP25 apps | /home/fractalwaves/clones/op25/op25/gr-op25_repeater/apps |
| Target | DeKalb County P25 Phase 1 |
