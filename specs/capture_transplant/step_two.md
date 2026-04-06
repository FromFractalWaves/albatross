# Capture Transplant — Step 2: Bridge

_Sub-spec of `specs/capture_transplant.md` (the master spec)._

_Depends on: Step 1 (config.py, models.py must exist)._

## Scope

Build the bridge process (Process 2). This process correlates metadata (which tgid is on which lane) with PCM (which lane is producing audio) and forwards both to the backend. It has no Albatross dependencies — it doesn't import from `contracts/` or `db/`.

After this step, the bridge can run alongside the backend from Step 1. Feed it metadata JSON on `:5557` and PCM on `:5560-5567`, and it will produce tagged multipart messages on `:5580` and forward metadata to `:5581`.

## Files

| File | What it is |
|------|-----------|
| `capture/trunked_radio/bridge.py` | Bridge process — metadata subscriber, PCM lane subscribers, lane state |

Tests:

| File | What it covers |
|------|---------------|
| `tests/test_bridge.py` | LaneState update logic, srcaddr→source_unit translation, grant type matching |

## What to Build

Refer to the master spec's **Process 2: Bridge** section. Key components:

- **LaneState** — thread-safe mapping of `lane_id → {tgid, freq, source_unit}`. Updated from metadata events. Reads `msg.get("type")` (NOT `"json_type"`). Translates `srcaddr` from TSBK parser output into `source_unit` at this boundary.
- **MetadataSubscriber** — thread that pulls JSON from `:5557`, parses grant events, updates LaneState, forwards all messages to `:5581`.
- **PCMLaneSubscriber** — one thread per voice lane. Pulls int16 PCM from `pcm_endpoint(lane_id)`. Looks up current tgid in LaneState. Drops PCM if no active tgid. Otherwise wraps in ZMQ multipart and pushes to `:5580`.

### Design decisions from the master spec

- Bridge reads `msg.get("type")`, not `"json_type"` — this is the prototype bug fix.
- `srcaddr` → `source_unit` translation happens here. PCM header JSON uses `source_unit`.
- PCM multipart format: Part 0 = JSON header `{"lane_id", "tgid", "freq", "source_unit", "ts"}`, Part 1 = raw int16 PCM bytes.
- Uses `config.py` from Step 1 for ZMQ endpoints and lane count.
- All threads are daemon threads.

## What NOT to Build

- Anything in `capture/trunked_radio/` already built in Step 1
- `flowgraph.py`, `lane_manager.py`, `metadata_poller.py` — built in Step 3
- Any Albatross repo integration (DB, contracts)

## Done When

1. `python -m pytest tests/test_bridge.py -v` — all pass
2. `python -m capture.trunked_radio.bridge` starts and blocks waiting for ZMQ connections
3. LaneState correctly translates `srcaddr` to `source_unit`
4. MetadataSubscriber matches on `"type"` field, not `"json_type"`
5. PCMLaneSubscriber drops PCM when no tgid is assigned to the lane