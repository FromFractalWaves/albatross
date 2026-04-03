# Misalignments: Pipeline Observability

_Spec: `specs/pipeline_observability.md` — reviewed against repo on 2026-04-03_

## TypeScript type name mismatch
- **Spec says:** Add `stages` to the `LivePipelineStarted` TypeScript type
- **Repo reality:** The type is called `PipelineStartedMessage` in `web/src/types/websocket.ts` (line 38)
- **Resolution:** The build plan targets `PipelineStartedMessage` — the actual type name.

## `docs/pipeline/new_pipelines.md` listed as new but already exists
- **Spec says:** File is new — listed in the files affected table
- **Repo reality:** `docs/pipeline/new_pipelines.md` already exists (empty file)
- **Resolution:** Treat as an update rather than a creation.

## `total_packets` removal cascades beyond `PipelineStarted`
- **Spec says:** Remove `total_packets` from `PipelineStarted`
- **Repo reality:** `total_packets` is also used in `PipelineComplete` (line 35 of `contracts/ws.py`), in the `pipeline_complete` broadcast in `_run_pipeline` (line 112 of `live_pipeline.py`), in the `pipeline_started` backlog test fixture (line 139 of `test_live_pipeline.py`), and in `useLiveData.ts` where `setPipelineTotal(msg.total_packets)` is called on `pipeline_started` (line 101). The `pipelineTotal` state variable in the hook is only set from this field.
- **Resolution:** Remove `total_packets` from `PipelineStarted` (contracts + TS type). Remove `pipelineTotal` state from `useLiveData`. Leave `PipelineComplete.total_packets` and the `pipeline_complete` broadcast unchanged — they still report how many packets were processed. Update the backlog test fixture to match the new `pipeline_started` shape (stages instead of total_packets).

## Mockup file reference
- **Spec says:** "See `specs/pipeline_observability_mockup.jsx` for the reference visual"
- **Repo reality:** The mockup file is `specs/mock.jsx`, not `specs/pipeline_observability_mockup.jsx`
- **Resolution:** The build plan references `specs/mock.jsx`.
