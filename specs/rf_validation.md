# On-Air RF Validation — Capture Pipeline

This is a hands-on test session for validating the capture pipeline against live P25 RF. You are working with a developer who has an RTL-SDR dongle connected and the DeKalb County P25 system within range.

## What we're testing

The three-process capture pipeline in `capture/trunked_radio/` — built from the spec in `specs/capture_transplant/`. The code is transplanted from a working prototype (`albatross1a`) with bug fixes applied during build and initial on-air testing.

**Phase 1 (control channel lock) has already passed.** This session picks up at Phase 2 (bridge correlation).

## Target system

- DeKalb County, P25 Phase 1
- Control channel: 854.6125 MHz
- NAC: 0x01F0
- Freq table opcode: 0x3d (iden_up)
- Voice channels confirmed on-air: 856.0125, 856.3125, 856.3375, 856.9625, 857.3125 MHz
- Talkgroups confirmed on-air: 6002, 6005, 6006, 6007, 6009, 6121, 6122, 6241, 6256, 6296
- Source unit IDs observed: 1011064, 1012635, 1013363, 1131115, 1239928, 6003047

## Lessons from Phase 1 (already applied)

These issues were found and fixed during the initial on-air test. They are already in the code but documented here for context:

1. **OP25 imports** — `op25_repeater` lives under `gnuradio` namespace (`from gnuradio import op25_repeater`). The `p25_demodulator.py` hierblock needs both `config.OP25_APPS_DIR` and `os.path.join(config.OP25_APPS_DIR, "tx")` on `sys.path`.

2. **Frame assembler API** — The boatbod fork has two classes: `frame_assembler` (new API) and `p25_frame_assembler` (old positional-arg API). Use `p25_frame_assembler` with explicit positional args.

3. **Control channel demod** — `p25_demod_fb` (float input) lacks AGC and FLL, cannot lock reliably via RTL-SDR. Control channel uses `p25_demod_cb` (complex input), which includes AGC, FLL, and the full demod chain. Voice lanes may need the same — TBD in Phase 2.

4. **Frequency offset convention** — OP25 uses `CENTER - CHANNEL` (positive when channel is below center). Pass `-config.CONTROL_OFFSET` to the demod. The original spec had `CHANNEL - CENTER` which tunes to the mirror frequency.

5. **TSBK parser bit layout** — Was completely rewritten. `msg.type()` is `(protocol << 16 | DUID)`, check `& 0xFFFF == 7`. TSBK body is a 96-bit integer with bit-shift extraction. `msg.to_string()` returns `bytes` in Python 3 (no `ord()` needed).

6. **CPU budget** — 8 voice lanes at 3.2 Msps overwhelms laptop hardware. Currently reduced to 3 lanes. The polyphase channelizer is the proper long-term fix (see master spec / ideas.md).

## Prerequisites

Before starting, verify:
1. RTL-SDR dongle is connected (`rtl_test` should find the device)
2. GNU Radio 3.10+ is installed (`python3 -c "from gnuradio import gr; print(gr.version())"`)
3. gr-osmosdr is installed (`python3 -c "import osmosdr"`)
4. gr-op25 / gr-op25_repeater (boatbod fork) is installed (`python3 -c "from gnuradio import op25, op25_repeater"`)
5. OP25 apps dir is set in config (`OP25_APPS_DIR` — verify `p25_demodulator.py` exists there)
6. The Albatross venv is activated and `pyzmq` is installed
7. The database is migrated (`alembic upgrade head`)

## Startup order

**Start processes in this order: backend → bridge → flowgraph.**

The flowgraph's ZMQ push sinks drop PCM if no subscriber is connected (100ms timeout). Starting the bridge before the flowgraph ensures PCM subscribers are ready. Starting the backend before the bridge ensures tagged PCM and metadata have somewhere to go.

Early audio from the first few hundred milliseconds of each call will still be lost — PCM arrives before grant metadata propagates through the MetadataPoller → ZMQ → bridge → LaneState path. This is inherent to the architecture and was true in the prototype.

## Test progression

Phase 1 is complete. Continue from Phase 2.

### Phase 2: Bridge correlation

Terminal 1 — start the backend first:
```bash
source trm/.venv/bin/activate
python -m capture.trunked_radio.backend
```

Terminal 2 — start the bridge:
```bash
python3 -m capture.trunked_radio.bridge
```

Terminal 3 — start the flowgraph:
```bash
python3 -m capture.trunked_radio.flowgraph
```

**What to look for:**
- Flowgraph locks onto control channel (grants decoded, lanes assigned — same as Phase 1)
- Bridge connects to metadata on :5557 and PCM on :5560-5562 (3 lanes)
- Bridge log lines showing metadata flowing through and LaneState updating
- PCM being tagged with tgid and forwarded to :5580 (not dropped)

**Problems to watch for:**
- All PCM dropped → LaneState not updating. Check that metadata events have `lane_id` (annotated by MetadataPoller). Check that bridge reads `msg.get("type")`, not `"json_type"`.
- No metadata flowing → ZMQ connection issue between flowgraph :5557 and bridge.
- Voice demod not locking → if voice lanes use `p25_demod_fb` (float input) and signal quality is marginal, they may need `p25_demod_cb` (complex input) like the control channel. This would be a Phase 2 finding.
- GNU Radio `O` overflow characters → CPU budget exceeded. Reduce to 2 lanes or investigate polyphase channelizer.

**Success criteria:** Tagged PCM multipart messages flowing from bridge to backend on :5580, metadata forwarded on :5581.

### Phase 3: Full pipeline — WAV files + DB writes

With all three processes running from Phase 2, watch the backend terminal.

**What to look for:**
- Backend log lines showing calls being finalized (tgid, duration, end_reason)
- WAV files appearing in `data/wav/`
- Calls closing with `end_reason="inactivity_timeout"` (most common) or `"lane_reassigned"`
- Transmission rows in the database with `status="captured"`

**Verify WAV files:**
```bash
# List recent WAV files
ls -lt data/wav/ | head -20

# Check a WAV file's properties
python3 -c "import wave; w = wave.open('data/wav/<filename>.wav'); print(f'channels={w.getnchannels()} rate={w.getframerate()} frames={w.getnframes()} duration={w.getnframes()/w.getframerate():.1f}s')"

# Play a WAV file
aplay data/wav/<filename>.wav
```

**Verify database:**
```bash
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
        rows = (await s.execute(select(Transmission).where(Transmission.status == 'captured').order_by(Transmission.timestamp.desc()).limit(5))).scalars().all()
        for r in rows:
            print(f'  {r.id[:8]}... tgid={r.talkgroup_id} src={r.source_unit} freq={r.frequency} dur={r.duration:.1f}s')

asyncio.run(check())
"
```

**Problems to watch for:**
- WAV files are empty (0 bytes) → PCM not flowing through bridge. Go back to Phase 2.
- WAV files have audio but it's garbled → voice demod not locking, sample rate mismatch, or the voice lane is using `p25_demod_fb` when it needs `p25_demod_cb`. Check if the frame assembler is producing valid IMBE frames.
- All calls end via timeout, none via lane_reassigned → normal. Lane reassignment requires the backend to see a grant that reassigns an occupied lane.
- `source_unit` is always None → only initial channel grants (opcode 0x00) carry srcaddr. Grant updates (0x02) don't. Expected for talkgroups already active when the system started.
- Duration seems wrong → duration is calculated from PCM byte count at 8000 Hz, 2 bytes/sample. Verify the WAV frame count matches.
- Backend crash on WAV write → check disk space and permissions on `data/wav/`. The pre-flight audit added try/except around `_finalize_calls` — verify it's catching and logging, not crashing.

**Success criteria:** WAV files with audible dispatch audio, `Transmission` rows in the DB with correct metadata, calls opening and closing as radio traffic flows.

### Phase 4: Endurance (15-30 minutes)

Let all three processes run. Watch for:
- Memory growth in the backend (leaking `ActiveCall` objects that never close?)
- Lane pool exhaustion in the flowgraph (all 3 lanes occupied, grants being dropped — more likely with reduced lane count)
- ZMQ backpressure (bridge PUSH sockets should have `sndhwm` set — verify dropped frames are logged, not queued without bound)
- GNU Radio buffer overflows (`O` characters) — if they appear intermittently, the CPU is marginal
- WAV files accumulating at a reasonable rate (depends on radio traffic volume)
- Control channel demod maintaining lock throughout (check grant decode rate stays steady)

## Known behaviors (not bugs)

- **First ~50-200ms of each call is lost.** PCM arrives before grant metadata propagates through MetadataPoller → ZMQ → bridge → LaneState. Inherent to the architecture.
- **`source_unit` often None.** Only opcode 0x00 (initial grant) carries srcaddr. Grant updates (0x02) which are more frequent do not.
- **Most calls end via `inactivity_timeout`.** Lane reassignment closures require specific timing of overlapping grants on the same frequency.
- **Unhandled TSBK opcodes are silently skipped.** The parser handles grants, grant_updates, and iden_up. Adjacency broadcasts, RFSS status, registration responses, etc. are decoded as `"type": "other"` and passed through but not acted on.

## After the test

Once Phases 2-4 are confirmed:
1. Note any issues, parameter tweaks, or unexpected behaviors
2. Listen to WAV files across different talkgroups — is the audio quality acceptable?
3. Verify talkgroup IDs and frequencies match the confirmed on-air observations
4. Capture any new talkgroups or frequencies not previously observed
5. Note the CPU load and whether 3 lanes was sufficient or if grants were dropped
6. Update the master spec (`specs/capture_transplant/overview.md`) with findings
7. File the polyphase channelizer work as a follow-up spec if lane count needs to increase