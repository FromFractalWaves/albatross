# Misalignments: Capture Transplant Step 2 (Bridge)

_Spec: `specs/capture_transplant/step_two.md` — reviewed against repo on 2026-04-06_

## config.py Missing Bridge Constants

- **Spec says:** "Uses `config.py` from Step 1 for ZMQ endpoints and lane count." The master spec references `pcm_endpoint(lane_id)` and ports 5557, 5560-5567, plus 8 voice lanes.
- **Repo reality:** `config.py` only has backend-side ports (5580, 5581, 5590) and audio/timeout constants. No metadata input port (5557), no PCM lane ports (5560-5567), no `NUM_LANES`, no `pcm_endpoint()` helper.
- **Resolution:** Step 2 adds the bridge-side constants and helper functions to `config.py` before building bridge.py. These are upstream (Process 1 → Bridge) ports vs the existing downstream (Bridge → Backend) ports.

## MetadataEvent.source_unit Already Translated

- **Spec says:** "The bridge translates `srcaddr` from the TSBK parser output into `source_unit`." This implies the bridge receives `srcaddr` in metadata JSON and must rename it.
- **Repo reality:** `MetadataEvent` in `models.py` already uses the field name `source_unit`, not `srcaddr`. The TSBK parser outputs `srcaddr`, but the model expects `source_unit`. The translation is a key rename when constructing the `MetadataEvent` from raw JSON, not a type conversion.
- **Resolution:** The bridge parses `msg.get("srcaddr")` from the incoming JSON and maps it to the `source_unit` field when constructing `MetadataEvent`. This is a JSON key rename at the deserialization boundary, which is exactly what the spec intends.
