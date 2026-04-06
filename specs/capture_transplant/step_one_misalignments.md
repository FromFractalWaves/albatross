# Misalignments: Capture Transplant — Step 1

_Spec: `specs/capture_transplant/step_one.md` — reviewed against repo on 2026-04-06_

## TransmissionPacket metadata not persisted to DB

- **Spec says:** `TransmissionPacket.metadata` contains `system`, `lane_id`, `end_reason`, `sample_rate`. The backend writes a `Transmission` row with `status="captured"`.
- **Repo reality:** The `Transmission` ORM model has no `metadata` column. `TransmissionPacket.to_orm()` maps flat fields (talkgroup_id, source_unit, frequency, etc.) but drops the `metadata` dict entirely.
- **Resolution:** This is by design — the spec confirms metadata is P25-specific and lives on the Pydantic object, not the DB. The metadata travels downstream via the ZMQ push to :5590 (as part of the JSON-serialized `TransmissionPacket`). No schema change needed. The build plan follows this pattern as-is. Flagging only so the builder doesn't try to persist metadata to the DB.

## Test file paths in spec vs repo convention

- **Spec says:** Test files listed as `tests/test_tsbk.py`, `tests/test_buffer_manager.py`, etc. — flat in the `tests/` directory.
- **Repo reality:** All existing tests are flat in `tests/` (e.g., `tests/test_contracts.py`, `tests/test_mock_pipeline.py`). This is consistent.
- **Resolution:** No issue. New test files follow the existing flat convention. Flagging only to confirm no `tests/capture/` subdirectory is needed.
