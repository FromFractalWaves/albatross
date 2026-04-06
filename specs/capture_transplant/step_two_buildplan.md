# Build Plan: Capture Transplant Step 2 (Bridge)

_Generated from spec — aligned with repo on 2026-04-06_

## Goal

Build the bridge process (Process 2) that correlates metadata with PCM from the flowgraph and forwards tagged audio to the backend. After this step, the bridge can run alongside the backend from Step 1.

**Context:** See `specs/capture_transplant/step_two_summaries.md` for current and target state.

## References

### Pre-build

| File | What it is | Why it's relevant |
|------|-----------|-------------------|
| `capture/trunked_radio/config.py` | ZMQ ports, timeouts, audio constants | Must be extended with bridge-side ports and lane count |
| `capture/trunked_radio/models.py` | MetadataEvent, LaneAssignment dataclasses | Bridge constructs MetadataEvent from raw JSON; LaneState tracks LaneAssignment-shaped data |
| `capture/trunked_radio/backend.py` | Backend event loop | Defines the multipart PCM format and metadata JSON format the bridge must produce |
| `tests/test_buffer_manager.py` | BufferManager tests | Pattern for building MetadataEvent fixtures and grant event helpers |
| `specs/capture_transplant/overview.md` | Master spec | Authoritative Process 2 design, PCM multipart format, srcaddr→source_unit translation rules |

### Post-build

| File | What it will be | Why it's needed |
|------|----------------|-----------------|
| `capture/trunked_radio/bridge.py` | Bridge process — LaneState, MetadataSubscriber, PCMLaneSubscriber | Core deliverable of Step 2 |
| `tests/test_bridge.py` | Bridge unit tests | Validates LaneState logic, srcaddr translation, grant matching, PCM drop behavior |

## Plan

### Step 1: Extend config.py with bridge-side constants

**Files:** `capture/trunked_radio/config.py`

Add constants for the bridge's upstream ZMQ ports and lane configuration:

- `METADATA_PORT = 5557` — flowgraph pushes parsed TSBK JSON here
- `NUM_LANES = 8` — number of voice lanes
- `PCM_BASE_PORT = 5560` — first PCM lane port; lane N is at `PCM_BASE_PORT + N`

Add two helper functions:

- `pcm_endpoint(lane_id: int) -> str` — returns `"tcp://127.0.0.1:{PCM_BASE_PORT + lane_id}"`
- `metadata_endpoint() -> str` — returns `"tcp://127.0.0.1:{METADATA_PORT}"`

Also add helpers for the existing backend ports so the bridge can reference them consistently:

- `pcm_backend_endpoint() -> str` — returns `"tcp://127.0.0.1:{PCM_PORT}"` (push tagged PCM to :5580)
- `control_backend_endpoint() -> str` — returns `"tcp://127.0.0.1:{CONTROL_PORT}"` (forward metadata to :5581)

### Step 2: Build LaneState

**Files:** `capture/trunked_radio/bridge.py`

`LaneState` is a thread-safe class with a `threading.Lock` protecting a `dict[int, dict]` mapping `lane_id → {"tgid": int, "freq": int | None, "source_unit": int | None}`.

Methods:

- `update(lane_id: int, tgid: int, freq: int | None, source_unit: int | None)` — sets or overwrites the entry for a lane
- `get(lane_id: int) -> dict | None` — returns the current assignment or None if the lane is idle
- `clear(lane_id: int)` — removes a lane's assignment

Grant handling within `update`: if the grant assigns `lane_id` to a new tgid and a different tgid previously held that lane, the old entry is simply overwritten (the backend handles the call closure via its own grant/reassignment logic).

### Step 3: Build MetadataSubscriber

**Files:** `capture/trunked_radio/bridge.py`

`MetadataSubscriber(threading.Thread)` — daemon thread.

Constructor takes: `lane_state: LaneState`, `zmq_context: zmq.Context`.

In `run()`:

1. Create a PULL socket bound or connected to `metadata_endpoint()` (PULL, connect — flowgraph PUSHes)
2. Create a PUSH socket connected to `control_backend_endpoint()` (forward to backend :5581)
3. Loop forever:
   - `recv_json()` from metadata socket (blocking)
   - Forward the raw JSON bytes to the backend control socket immediately (the backend needs the original message)
   - Parse the message: check `msg.get("type")` — if `"grant"` or `"grant_update"`, extract tgid, frequency, lane_id, and translate `msg.get("srcaddr")` → `source_unit`
   - For `"grant"`: call `lane_state.update(lane_id, tgid, freq, source_unit)`
   - For `"grant_update"`: same, plus handle the second tgid/freq pair (`tgid2`, `frequency2`) if present and if a second lane_id is provided

The subscriber uses `GRANT_TYPES = {"grant", "grant_update"}` to match events — matching the TSBK parser's output types and the backend's `GRANT_EVENT_TYPES`.

### Step 4: Build PCMLaneSubscriber

**Files:** `capture/trunked_radio/bridge.py`

`PCMLaneSubscriber(threading.Thread)` — daemon thread, one instance per lane.

Constructor takes: `lane_id: int`, `lane_state: LaneState`, `zmq_context: zmq.Context`.

In `run()`:

1. Create a PULL socket connected to `pcm_endpoint(self.lane_id)` (flowgraph PUSHes PCM here)
2. Create a PUSH socket connected to `pcm_backend_endpoint()` (tagged multipart to backend :5580)
3. Loop forever:
   - `recv()` raw bytes from PCM socket (blocking)
   - Look up `lane_state.get(self.lane_id)`
   - If None (no active tgid): drop the PCM, continue
   - Otherwise build JSON header: `{"lane_id": self.lane_id, "tgid": info["tgid"], "freq": info["freq"], "source_unit": info["source_unit"], "ts": time.time()}`
   - Send as ZMQ multipart: `[json_header_bytes, pcm_bytes]`

### Step 5: Build bridge entry point

**Files:** `capture/trunked_radio/bridge.py`

Add a `main()` function and `if __name__ == "__main__"` / `__main__` support:

1. Create a single `zmq.Context()`
2. Create `LaneState()`
3. Start `MetadataSubscriber` as daemon thread
4. Start `NUM_LANES` `PCMLaneSubscriber` threads as daemon threads
5. Block on `threading.Event().wait()` (keeps main thread alive; daemon threads die on exit)
6. Handle `KeyboardInterrupt` for clean shutdown (context cleanup)

Entry point: `python -m capture.trunked_radio.bridge`

### Step 6: Write tests

**Files:** `tests/test_bridge.py`

Tests focus on LaneState logic and the srcaddr→source_unit translation — not on ZMQ wiring (that's integration testing).

Test cases:

1. **LaneState.update sets and retrieves lane info** — update lane 0 with tgid/freq/source_unit, verify `get(0)` returns it
2. **LaneState.get returns None for unassigned lane** — `get(5)` on fresh LaneState returns None
3. **LaneState.update overwrites on reassignment** — update lane 0 with tgid A, then with tgid B; verify get returns B
4. **LaneState.clear removes assignment** — update then clear, verify get returns None
5. **srcaddr→source_unit translation** — construct a raw grant JSON dict with `"srcaddr": 12345`, verify that the metadata subscriber logic (extract as a helper/classmethod for testability) maps it to `source_unit=12345` (int, not string)
6. **grant_update type is recognized** — verify `"grant_update"` is in the set of handled grant types
7. **PCM drop when no tgid** — verify the decision logic: when `lane_state.get(lane_id)` returns None, PCM should be dropped (test the conditional, not the ZMQ plumbing)

Follow the pattern from `tests/test_buffer_manager.py` for fixture construction. No ZMQ sockets needed in unit tests — test the pure logic classes directly.

## Testing

Run: `python -m pytest tests/test_bridge.py -v`

All 7 tests should pass. The bridge should also be startable via `python -m capture.trunked_radio.bridge` (will block waiting for ZMQ connections — manual smoke test, not automated).

## Doc Updates

Update `CLAUDE.md`:
- Add bridge-side port constants (5557, 5560-5567) to the `config.py` description
- Add `bridge.py` to the Capture Backend file listing with a one-line description
- Update the test count to include bridge tests
