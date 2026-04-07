# Per-Transmission Audio Splitting

## Problem

The capture backend currently produces one WAV file per talkgroup activity window — from the first PCM on a tgid until the 1.5s inactivity timeout fires. On an active talkgroup, this means a single WAV file contains multiple back-to-back transmissions from different radio units (different people talking). There's no silence gap between them because the P25 channel is continuously active.

When this WAV file reaches ASR (Whisper), it's transcribed as one block of text with no speaker boundaries. The TRM receives a single `ProcessedPacket` containing an entire multi-speaker exchange instead of individual transmissions. This defeats per-transmission routing — the TRM can't attribute speech to speakers, can't route individual transmissions to threads, and loses the granularity the pipeline is designed around.

## What a Transmission Is

In P25, a transmission is one push-to-talk event from one radio unit. The control channel signals this: when a new unit keys up on a talkgroup, the system issues a new channel grant (opcode 0x00) with the new unit's `srcaddr`. This is the authoritative boundary marker.

The pipeline should produce one WAV file and one `TransmissionPacket` per push-to-talk event, not per talkgroup activity window.

## Solution

Split calls in `BufferManager` when the `source_unit` changes on the same tgid. A grant with a different `srcaddr` for an already-active tgid means a different radio keyed up — close the current call and open a new one.

### Change to `BufferManager.handle_metadata()`

Currently, when a grant arrives for a tgid that already has an active call, the buffer manager updates the call's metadata (frequency, source_unit, lane_id). The call stays open.

New behavior: if the grant's `source_unit` differs from the active call's `source_unit`, and the active call has PCM data, close the current call with `end_reason="source_changed"` and open a new `ActiveCall` with the new source_unit. If the source_unit is the same (same radio re-granting), just update metadata as before.

```
Grant arrives for tgid with active call:
  - source_unit unchanged → update metadata, keep call open
  - source_unit changed, call has PCM → close call ("source_changed"), open new call
  - source_unit changed, call has no PCM → update metadata (no audio to save)
  - source_unit is None → update metadata, keep call open (can't determine speaker change)
```

The "call has PCM" check prevents creating empty WAV files when grants arrive before any voice frames.

### New `end_reason` Value

Add `"source_changed"` to the set of end reasons. The full set becomes:
- `"inactivity_timeout"` — no PCM for 1.5 seconds
- `"lane_reassigned"` — a different tgid was granted the same lane
- `"source_changed"` — a different radio unit keyed up on the same tgid

Update the `TransmissionPacket.metadata.end_reason` documentation accordingly.

### Timing Considerations

The grant for the new speaker arrives via the control channel before the new speaker's voice frames arrive via the voice channel. The propagation path is:

```
Control channel TSBK → MetadataPoller → ZMQ :5557 → Bridge → ZMQ :5581 → Backend
Voice channel PCM    → ZMQ :5560+n    → Bridge → ZMQ :5580 → Backend
```

The metadata path is faster (small JSON vs continuous PCM stream). This means the split happens slightly before the new speaker's audio arrives, which is the correct behavior — the old call gets all of the old speaker's audio, and the new call starts accumulating the new speaker's audio.

The ~50-200ms of the new speaker's audio that arrives before the grant propagates will end up in the old call's buffer. This is the same timing limitation that exists at call start and is acceptable — it's a few frames, not a meaningful portion of the transmission.

### What About `grant_update` (opcode 0x02)?

Grant updates do NOT carry `srcaddr` — they only have tgid and frequency. They are periodic rebroadcasts confirming that a talkgroup is still active on a channel. They should NOT trigger a source_changed split.

The split only fires on events where `source_unit` is not None and differs from the current call. Since grant_updates always have `source_unit=None` (they carry no srcaddr), they are naturally excluded.

### What About Rapid Re-Grants?

If the same radio unit keys up, releases, and keys up again quickly (within the 1.5s timeout), the new grant will have the same `srcaddr`. The buffer manager won't split because `source_unit` hasn't changed. The two transmissions will be merged into one WAV file.

This is a minor edge case. In practice, the inactivity timeout usually fires between same-speaker transmissions because there's a natural pause. If it doesn't, the merged audio is still from the same speaker, so ASR quality isn't affected — only the transmission boundary is slightly off.

## Files Changed

| File | Change |
|------|--------|
| `capture/trunked_radio/buffer_manager.py` | Add source_unit comparison in grant handling, close call on change |
| `tests/test_buffer_manager.py` | Add tests: source_unit change triggers split, None source_unit doesn't split, grant_update doesn't split, no-PCM call not split |
| `specs/capture_transplant/overview.md` | Update `end_reason` values to include `"source_changed"` |

## What This Does NOT Change

- WAV writer, packet builder, packet sink — unchanged. They already handle whatever `CompletedCall` the buffer manager produces.
- Bridge — unchanged. It already passes `source_unit` through.
- Flowgraph — unchanged. Grant decoding already extracts `srcaddr`.
- `TransmissionPacket` contract — unchanged. `source_unit` is already `Optional[int]`.
- Backend event loop — unchanged. It already calls `handle_metadata()` and finalizes returned calls.

## Done When

1. A talkgroup with two speakers produces two separate WAV files (one per push-to-talk)
2. Each WAV file has `source_unit` set to the speaking radio's ID
3. `end_reason="source_changed"` appears on calls closed by speaker change
4. `grant_update` events (source_unit=None) do not trigger splits
5. Same-speaker re-grants do not trigger splits
6. Existing tests still pass