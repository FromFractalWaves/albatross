# Build Plan: Per-Transmission Audio Splitting

_Generated from spec — aligned with repo on 2026-04-06_

## Goal

Split calls in `BufferManager` when a grant arrives with a different `source_unit` for an already-active tgid, so each push-to-talk event produces its own WAV file and `TransmissionPacket`.

**Context:** See `specs/audio_splitting_summaries.md` for current and target state.

## References

### Pre-build
| File | What it is | Why it's relevant |
|------|-----------|-------------------|
| `capture/trunked_radio/buffer_manager.py` | Call state machine | Primary file to modify — `_grant_or_update()` gets the split logic |
| `capture/trunked_radio/models.py` | `ActiveCall`, `CompletedCall`, `MetadataEvent` dataclasses | Need `pcm_chunks` check; no modifications needed |
| `capture/trunked_radio/backend.py` | Async event loop calling buffer manager | Verify no changes needed (confirmed) |
| `tests/test_buffer_manager.py` | 7 existing tests for buffer manager | Add new tests following existing patterns |
| `docs/sources/trunked_radio/architecture.md` | Capture pipeline architecture doc | Update `end_reason` documentation |

### Post-build
No new files created.

## Plan

### Step 1: Add source_unit split logic to `BufferManager._grant_or_update()`

**Files:** `capture/trunked_radio/buffer_manager.py`

In the `event.tgid in self.active_calls` branch (currently lines 35-43), before updating metadata, add a comparison: if `event.source_unit is not None` and `event.source_unit != call.source_unit` and `call.pcm_chunks` is non-empty, close the current call via `self._close_call(tgid, "source_changed")` and append to `closed`. Then fall through to open a new `ActiveCall` (reuse the existing new-call creation at lines 46-53, but now it also executes when the prior call was just closed).

The structure becomes:
1. Lane reassignment check (existing, unchanged)
2. If tgid has active call AND source_unit changed AND call has PCM: close call, remove from dict, fall through to "open new call"
3. If tgid has active call AND source_unit same/None: update metadata (existing behavior)
4. If tgid has no active call: open new call (existing behavior)

If `source_unit` changed but call has no PCM (`pcm_chunks` is empty), just update metadata — don't split.

### Step 2: Add tests for source_unit splitting

**Files:** `tests/test_buffer_manager.py`

Add four tests following the existing `_grant_event` helper pattern:

1. **`test_source_change_splits_call`** — Open a call for tgid with source_unit=10, add PCM, then send a grant with source_unit=20 for the same tgid. Assert: one `CompletedCall` returned with `end_reason="source_changed"` and `source_unit=10`. Assert: new active call exists for tgid with `source_unit=20`.

2. **`test_source_none_no_split`** — Open a call for tgid with source_unit=10, add PCM, then send a grant_update with `source_unit=None` for the same tgid. Assert: no calls closed. Active call still has `source_unit=10`.

3. **`test_grant_update_no_split`** — Open a call for tgid with source_unit=10, add PCM, then send an event with `type="grant_update"` and `source_unit=None`. Assert: no calls closed (grant_updates naturally excluded since source_unit is None).

4. **`test_source_change_no_pcm_no_split`** — Open a call for tgid via grant (source_unit=10), do NOT add PCM, then send a grant with source_unit=20. Assert: no calls closed. Active call metadata updated to source_unit=20.

5. **`test_same_source_no_split`** — Open a call for tgid with source_unit=10, add PCM, then send a grant with source_unit=10 for the same tgid. Assert: no calls closed. Call remains active.

## Testing

Run `python -m pytest tests/test_buffer_manager.py -v` after each step. All 7 existing tests plus 5 new tests should pass. The source_unit split should not affect any existing test because no existing test sends a second grant with a different source_unit for the same tgid.

## Doc Updates

Update `docs/sources/trunked_radio/architecture.md` — in the Packet Builder description (around line 114), add `"source_changed"` to the documented set of `end_reason` values so it reads: `end_reason` values are `"inactivity_timeout"`, `"lane_reassigned"`, or `"source_changed"`.
