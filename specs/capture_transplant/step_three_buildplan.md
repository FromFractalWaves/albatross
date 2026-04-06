# Build Plan: Capture Transplant — Step 3 (Flowgraph)

_Generated from spec — aligned with repo on 2026-04-06_

## Goal

Build the flowgraph process (Process 1): lane manager, metadata poller, and GNU Radio top_block. After this step, all three capture processes exist and can run together against live RF.

**Context:** See `specs/capture_transplant/step_three_summaries.md` for current and target state.

## References

### Pre-build

| File | What it is | Why it's relevant |
|------|-----------|-------------------|
| `capture/trunked_radio/config.py` | ZMQ ports, timeouts, lane count | Must be extended with SDR and flowgraph constants |
| `capture/trunked_radio/tsbk.py` | TSBK parser with `process_qmsg()` | MetadataPoller calls this; `process_qmsg` needs a fix (`to_bytes` → `to_string`) |
| `capture/trunked_radio/bridge.py` | Bridge process — LaneState, MetadataSubscriber | Consumes flowgraph output; confirms the JSON format the poller must produce |
| `capture/trunked_radio/models.py` | MetadataEvent, LaneAssignment dataclasses | LaneManager tracks assignments using similar shapes |
| `capture/trunked_radio/buffer_manager.py` | BufferManager with GRANT_EVENT_TYPES | Reference for grant type matching pattern |
| `tests/test_bridge.py` | Bridge unit tests | Pattern reference for threading-related tests |
| `tests/test_tsbk.py` | TSBK parser tests | Pattern reference for test fixtures |
| `specs/capture_transplant/overview.md` | Master spec | Full Process 1 design: SDR config, control lane, voice lanes, lane manager, metadata poller |

### Post-build

| File | What it will be | Why it's needed |
|------|----------------|-----------------|
| `capture/trunked_radio/lane_manager.py` | Thread-safe lane allocation logic | Pure logic — assigns voice lanes to talkgroups |
| `capture/trunked_radio/metadata_poller.py` | Daemon thread: msg_queue → TSBK parser → lane manager → ZMQ | Bridges GNU Radio to ZMQ; produces JSON the bridge consumes |
| `capture/trunked_radio/flowgraph.py` | GNU Radio top_block — SDR source, control + voice lanes | Process 1 entry point |
| `tests/test_lane_manager.py` | LaneManager unit tests | Grant allocation, preemption, pool exhaustion, stale sweep |

## Plan

### Step 1: Extend config.py with flowgraph constants

**Files:** `capture/trunked_radio/config.py`

Add a new section for SDR and flowgraph parameters:

- `CENTER_FREQ = 855_750_000` — SDR center frequency in Hz (855.75 MHz)
- `SDR_SAMPLE_RATE = 3_200_000` — 3.2 Msps
- `SDR_RF_GAIN = 30` — dB
- `SDR_IF_GAIN = 20` — dB
- `SDR_BB_GAIN = 20` — dB
- `CONTROL_FREQ = 854_612_500` — control channel frequency in Hz
- `CONTROL_OFFSET = CONTROL_FREQ - CENTER_FREQ` — offset from center (negative value: -1,137,500 Hz)
- `CHANNEL_DECIMATION = 50` — decimation factor for channelizers
- `CHANNEL_RATE = SDR_SAMPLE_RATE // CHANNEL_DECIMATION` — 64,000 Hz per channel
- `CHANNEL_FILTER_CUTOFF = 6250` — Hz, low-pass cutoff
- `CHANNEL_FILTER_TRANSITION = 1500` — Hz, transition width
- `FM_DEVIATION = 600` — Hz, P25 C4FM symbol deviation
- `STALE_SWEEP_INTERVAL = 2.0` — seconds, how often lane manager sweeps
- `STALE_MAX_AGE = 5.0` — seconds, release lane if tgid not seen for this long
- `OP25_APPS_DIR = os.environ.get("OP25_APPS_DIR", "/usr/local/lib/op25/apps")` — path to OP25 app directory for `p25_demod_fb` import
- `ZMQ_SINK_TIMEOUT = 100` — ms, ZMQ push sink timeout (voice lane PCM)

### Step 2: Fix process_qmsg in tsbk.py

**Files:** `capture/trunked_radio/tsbk.py`

Change `tsbk.py:142` from `msg.to_bytes()` to `msg.to_string()`. GNU Radio's `gr.message.to_string()` returns `bytes` in Python 3 — it's the correct API. The method name `to_bytes()` doesn't exist on `gr.message`.

### Step 3: Build LaneManager

**Files:** `capture/trunked_radio/lane_manager.py`

`LaneManager` is pure logic with a `threading.Lock`. No GNU Radio imports.

Internal state: `self._lanes: dict[int, dict]` — maps `lane_id → {"tgid": int, "freq": int | None, "srcaddr": int | None, "last_seen": float}`. `self._tgid_to_lane: dict[int, int]` — reverse index for fast tgid lookup. `self._retune_callback: Callable[[int, int], None] | None` — set by the flowgraph.

Constructor: `__init__(num_lanes: int = config.NUM_LANES)`. Initializes empty lane and reverse-index dicts. Accepts optional `retune_callback`.

Methods:

- `on_grant(tgid: int, freq: int, srcaddr: int | None) -> int | None`:
  1. If tgid already has a lane (via `_tgid_to_lane`): update freq/srcaddr/last_seen. If freq changed, call `retune_callback(lane_id, freq)`. Return existing lane_id.
  2. If another tgid holds a lane on the same freq: preempt — remove the old tgid, assign this tgid to that lane_id (the system reused the frequency). Call retune_callback if needed. Return lane_id.
  3. Find a free lane (lane_id in `range(num_lanes)` not in `_lanes`). Assign tgid, freq, srcaddr, last_seen. Call `retune_callback(lane_id, freq)`. Return lane_id.
  4. No free lanes: return None (grant dropped).

- `sweep_stale(max_age: float = config.STALE_MAX_AGE) -> list[int]`:
  Iterate `_lanes`, release any where `time.time() - last_seen > max_age`. Remove from both `_lanes` and `_tgid_to_lane`. Return list of released tgids. Called from MetadataPoller on a timer.

- `set_retune_callback(callback: Callable[[int, int], None])`:
  Sets `_retune_callback`. The flowgraph calls this after constructing the voice lane blocks, passing a closure that calls `voice_channelizer[lane_id].set_center_freq(freq - center_freq)`.

All public methods acquire `self._lock` before modifying state.

### Step 4: Build MetadataPoller

**Files:** `capture/trunked_radio/metadata_poller.py`

`MetadataPoller(threading.Thread)` — daemon thread.

Constructor takes: `msg_queue` (a `gr.msg_queue`), `tsbk_parser: TSBKParser`, `lane_manager: LaneManager`, `zmq_context: zmq.Context`.

`run()`:
1. Create a ZMQ PUSH socket bound to `tcp://*:{config.METADATA_PORT}` (`:5557`).
2. Track `last_sweep = time.time()`.
3. Loop forever:
   - Try `msg = self.msg_queue.delete_head_nowait()`. If None, sleep 5ms and continue.
   - Call `event = self.tsbk_parser.process_qmsg(msg)`. If None, continue.
   - If `event["type"]` in `{"grant", "grant_update"}`:
     - Call `lane_id = self.lane_manager.on_grant(event["tgid"], event.get("frequency"), event.get("srcaddr"))`.
     - Inject `event["lane_id"] = lane_id` into the dict (this is what the bridge reads).
     - For `grant_update` with `tgid2`/`frequency2`: call `on_grant` again for the second pair, inject `lane_id2`.
   - Push `json.dumps(event).encode()` to ZMQ socket.
   - Check sweep timer: if `time.time() - last_sweep >= config.STALE_SWEEP_INTERVAL`, call `lane_manager.sweep_stale()`, reset timer.

The ZMQ socket binds (not connects) because the poller is the source — the bridge connects to it.

### Step 5: Build Flowgraph

**Files:** `capture/trunked_radio/flowgraph.py`

`P25Flowgraph(gr.top_block)` subclass. Has hard external dependencies: GNU Radio 3.10+, gr-osmosdr, gr-op25 (boatbod fork), RTL-SDR hardware.

Top-level imports: `gnuradio` core, `osmosdr`, `gr.filter`, `gr.analog`, `gr.zeromq`. Import `p25_demod_fb` from OP25 apps via `sys.path.insert(0, config.OP25_APPS_DIR)` and `from p25_demodulator import p25_demod_fb`.

`__init__()`:
1. `super().__init__()`.
2. Create `osmosdr.source(args="rtl=0")`. Set center freq, sample rate, gains from config.
3. Build channel filter taps: `gnuradio.filter.firdes.low_pass(1, config.SDR_SAMPLE_RATE, config.CHANNEL_FILTER_CUTOFF, config.CHANNEL_FILTER_TRANSITION, gnuradio.fft.window.WIN_HAMMING)`.
4. Calculate FM demod gain: `config.CHANNEL_RATE / (2 * math.pi * config.FM_DEVIATION)`.
5. **Control lane:**
   - `freq_xlating_fir_filter_ccf(config.CHANNEL_DECIMATION, taps, config.CONTROL_OFFSET, config.SDR_SAMPLE_RATE)`
   - `analog.quadrature_demod_cf(fm_gain)`
   - `p25_demod_fb(input_rate=config.CHANNEL_RATE)`
   - `op25_repeater.frame_assembler(do_imbe=True, do_output=False, do_msgq=True, do_audio_output=False, queue=self.msg_queue)`
   - `self.msg_queue = gr.msg_queue(50)` — sized buffer for TSBK messages
   - Connect: `source → channelizer → demod → p25_demod → assembler`
6. **Voice lanes (x8):**
   - For each `lane_id` in `range(config.NUM_LANES)`:
     - `freq_xlating_fir_filter_ccf(config.CHANNEL_DECIMATION, taps, 0, config.SDR_SAMPLE_RATE)` — offset 0 (idle)
     - `analog.quadrature_demod_cf(fm_gain)`
     - `p25_demod_fb(input_rate=config.CHANNEL_RATE)`
     - `op25_repeater.frame_assembler(do_imbe=True, do_output=True, do_msgq=False, do_audio_output=True)`
     - `zeromq.push_sink(gr.sizeof_short, 1, f"tcp://*:{config.PCM_BASE_PORT + lane_id}", config.ZMQ_SINK_TIMEOUT)`
     - Connect the chain. Store channelizer reference in `self.voice_channelizers[lane_id]` for retuning.
7. Create `LaneManager()`, set retune callback to a closure that computes offset and calls `self.voice_channelizers[lane_id].set_center_freq(freq - config.CENTER_FREQ)`.
8. Create `TSBKParser()`.
9. Create `zmq.Context()` for the metadata poller.
10. Create `MetadataPoller(self.msg_queue, tsbk_parser, lane_manager, zmq_ctx)`.

`start()` override: start the `MetadataPoller` thread, then call `super().start()`.

`if __name__ == "__main__"` block: instantiate `P25Flowgraph`, call `start()`, `wait()` (GNU Radio's blocking wait). Handle `KeyboardInterrupt` for clean `stop()`.

### Step 6: Write tests for LaneManager

**Files:** `tests/test_lane_manager.py`

Follow existing test patterns (`tests/test_bridge.py`, `tests/test_tsbk.py`). No GNU Radio or ZMQ needed — LaneManager is pure logic.

Test cases:

1. **test_grant_assigns_lane** — `on_grant(6005, 856012500, 100)` returns a valid lane_id (0-7). Verify the lane is occupied.
2. **test_existing_tgid_returns_same_lane** — Grant tgid 6005 twice. Both calls return the same lane_id.
3. **test_freq_change_triggers_retune** — Grant tgid 6005 on freq A, then on freq B. Verify retune_callback was called with `(lane_id, freq_B)`. Use a mock/list to capture callback calls.
4. **test_same_freq_preempts** — Grant tgid A on freq F (gets lane 0). Grant tgid B on freq F. Verify tgid B gets lane 0 (preemption) and tgid A is evicted from `_tgid_to_lane`.
5. **test_pool_exhaustion** — Grant 8 different tgids on 8 different freqs. The 9th grant returns None.
6. **test_sweep_stale_releases** — Grant tgid 6005. Manually set `last_seen` to 10 seconds ago. Call `sweep_stale(max_age=5.0)`. Verify tgid 6005 is in the returned list and the lane is free.
7. **test_sweep_stale_keeps_fresh** — Grant tgid 6005 (just now). Call `sweep_stale(max_age=5.0)`. Returns empty list. Lane is still assigned.
8. **test_free_lane_after_stale_sweep** — Grant 8 tgids (full pool). Stale one. Sweep. Grant a 9th — should succeed (gets the freed lane).

## Testing

Run:
```bash
python -m pytest tests/test_lane_manager.py -v
```

All 8 tests should pass. Existing tests must still pass: `python -m pytest tests/ -v`.

Manual smoke test (requires hardware + GNU Radio + OP25):
```bash
python -m capture.trunked_radio.flowgraph
```
Should lock to the control channel and begin decoding TSBKs.

Full system test (all three processes):
```bash
# Terminal 1 — backend
python -m capture.trunked_radio.backend
# Terminal 2 — bridge
python -m capture.trunked_radio.bridge
# Terminal 3 — flowgraph
python -m capture.trunked_radio.flowgraph
```

## Doc Updates

Update `CLAUDE.md`:
- Add `lane_manager.py`, `metadata_poller.py`, `flowgraph.py` to the Capture Backend file listing
- Add SDR and flowgraph constants to the `config.py` description
- Note the `process_qmsg` fix in `tsbk.py`
- Update test count to include lane manager tests
- Document the `OP25_APPS_DIR` env var and hardware dependencies
