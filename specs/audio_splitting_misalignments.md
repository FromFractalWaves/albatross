# Misalignments: Per-Transmission Audio Splitting

_Spec: `specs/audio_splitting.md` — reviewed against repo on 2026-04-06_

## Doc update target doesn't exist

- **Spec says:** Update `specs/capture_transplant/overview.md` to include `"source_changed"` in the `end_reason` values.
- **Repo reality:** The directory `specs/capture_transplant/` does not exist. The `end_reason` field is documented in `docs/sources/trunked_radio/architecture.md` (line 114, mentions `end_reason` as a metadata field on `TransmissionPacket`).
- **Resolution:** Update `docs/sources/trunked_radio/architecture.md` instead. Add `"source_changed"` to the description of end reasons there.

## `ActiveCall` has no `has_pcm` helper

- **Spec says:** "call has PCM" check prevents creating empty WAV files.
- **Repo reality:** `ActiveCall` has `total_pcm_bytes()` which returns sum of chunk lengths. There's also `pcm_chunks` list directly accessible.
- **Resolution:** Use `call.pcm_chunks` (truthy when non-empty) or `call.total_pcm_bytes() > 0` for the check. No new method needed.
