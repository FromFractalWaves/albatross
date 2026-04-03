# Misalignments: Pipeline Observability

_Spec: `specs/pipeline_observability.md` — reviewed against repo on 2026-04-03_

## TypeScript type name mismatch
- **Spec says:** Add `stages` to the `LivePipelineStarted` TypeScript type
- **Repo reality:** The type is called `PipelineStartedMessage` in `web/src/types/websocket.ts` (line 38)
- **Resolution:** The build plan targets `PipelineStartedMessage` — the actual type name. The spec's `LivePipelineStarted` is treated as a reference error.

## `docs/pipeline/new_pipelines.md` listed as new but already exists
- **Spec says:** File is new — listed in the files affected table
- **Repo reality:** `docs/pipeline/new_pipelines.md` already exists (empty file)
- **Resolution:** Treat as an update rather than a creation. Write the new-pipeline workflow content into the existing file.
