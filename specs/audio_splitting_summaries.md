# Summaries: Per-Transmission Audio Splitting

_Spec: `specs/audio_splitting.md` — reviewed against repo on 2026-04-06_

## Current State

`BufferManager` tracks active calls by tgid in a `dict[int, ActiveCall]`. When a grant or grant_update arrives via `handle_metadata()`, two things can happen: (1) if the grant's lane is occupied by a *different* tgid, the prior call is closed with `"lane_reassigned"`, and (2) the grant either opens a new `ActiveCall` or updates an existing one's metadata (frequency, source_unit, lane_id).

The metadata update path (lines 35-43 of `buffer_manager.py`) unconditionally overwrites fields on the existing call. It does not compare old vs new `source_unit` — a speaker change on the same tgid is silently absorbed into the ongoing call. This means a talkgroup with two speakers back-to-back produces one WAV file covering both speakers.

`handle_pcm()` appends PCM to an existing call or opens a new one if none exists. `sweep()` closes calls idle beyond the timeout with `"inactivity_timeout"`. `drain()` closes all calls on shutdown.

The backend event loop (`CaptureBackend`) calls `handle_metadata()` and `handle_pcm()`, then finalizes any `CompletedCall` list returned — writing WAV, building a `TransmissionPacket`, persisting to DB, and emitting via sink. No changes needed in the backend; it already handles whatever `CompletedCall` objects the buffer manager produces.

Current `end_reason` values: `"inactivity_timeout"`, `"lane_reassigned"`.

## Target State

`BufferManager._grant_or_update()` gains source_unit comparison logic. When a grant arrives for a tgid that already has an active call:

- If `source_unit` is the same or `None` on the grant: update metadata as before (no split).
- If `source_unit` differs and the call has PCM data: close the current call with `end_reason="source_changed"`, then open a new `ActiveCall` with the new source_unit.
- If `source_unit` differs but the call has no PCM: just update metadata (no empty WAV).

This produces one WAV file per push-to-talk event instead of per talkgroup activity window. The new `end_reason` value `"source_changed"` joins the existing two.

Everything downstream (WAV writer, packet builder, packet sink, backend event loop) is unchanged — they already handle arbitrary `CompletedCall` objects.
