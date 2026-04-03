# Change Notes: Pipeline Observability

_Built 2026-04-03_

## What changed

Pipeline stage visibility added to the live UI. Each pipeline stage shows an incrementing packet count in real time, driven by pipeline-declared metadata — no hardcoded stage names in the frontend.

## New files

| File | What it is |
|------|-----------|
| `api/services/base_pipeline.py` | Abstract base class (`BasePipelineManager`) for pipeline managers. Owns lifecycle (start/stop), WebSocket subscriber fanout, message backlog, and stage metadata. Subclasses implement `pipeline_stages` property and `_run_pipeline` async method. Has a `_pre_run` hook (no-op by default) for setup like DB resets. |
| `web/src/components/PipelineStages.tsx` | Frontend component that renders a vertical strip of stage rows. Each row shows `[stage.id]` and a count, colored by index (blue/amber/purple). Returns `null` when stages array is empty. Positioned between TopBar and pipeline controls. |
| `docs/pipeline/new_pipelines.md` | Documentation for adding new pipelines using `BasePipelineManager`. |

## Modified files

### `contracts/ws.py`
- Added `PipelineStageDefinition` Pydantic model (`id`, `label`, `message_type`).
- `PipelineStarted`: replaced `total_packets: int` with `stages: list[PipelineStageDefinition] = []`.
- `PipelineComplete.total_packets` left unchanged.

### `api/services/live_pipeline.py`
- `LivePipelineManager` now inherits from `BasePipelineManager`.
- Removed: `__init__`, `status`, `start`, `stop`, `subscribe`, `unsubscribe`, `_broadcast` — all inherited from base.
- Added `pipeline_stages` property returning 3 `PipelineStageDefinition`s: capture, preprocessing, routing.
- Added `_pre_run` override that calls `reset_db()`.
- `pipeline_started` broadcast now sends `stages` instead of `total_packets`.
- Removed imports: `WebSocket`, `WebSocketState` from starlette (now in base class).
- Added imports: `BasePipelineManager`, `PipelineStageDefinition`.

### `api/routes/mock.py`
- `GET /api/mock/status` now returns `{"status": ..., "stages": [...]}` instead of just `{"status": ...}`.

### `web/src/types/websocket.ts`
- Added `PipelineStageDefinition` interface (`id`, `label`, `message_type`).
- `PipelineStartedMessage`: replaced `total_packets: number` with `stages: PipelineStageDefinition[]`.

### `web/src/hooks/useLiveData.ts`
- Added `StageState` exported type: `PipelineStageDefinition & { count: number }`.
- Replaced `pipelineTotal` / `setPipelineTotal` state with `stages` / `setStages` state (`useState<StageState[]>([])`).
- WS handler `pipeline_started` case: now calls `setStages(msg.stages.map(s => ({...s, count: 0})))` instead of `setPipelineTotal(msg.total_packets)`.
- Added WS handler cases for `packet_captured` and `packet_preprocessed`: increment matching stage count.
- Added stage count increment to existing `packet_routed` case (before the routing record handling).
- Added `stages` to the hook's return object.
- Note: originally used TanStack Query cache (`useQuery` with `enabled: false`) for stage state. Changed to plain `useState` because TanStack Query requires a `queryFn` even when disabled, and `invalidateQueries({ queryKey: ["live"] })` on pipeline_complete would trigger refetch errors. `useState` is simpler and avoids both problems.

### `web/src/app/live/[source]/page.tsx`
- Destructures `stages` from `useLiveData()`.
- Renders `<PipelineStages stages={stages} />` between TopBar and the pipeline controls section.
- Imports `PipelineStages` component.
- Status poll `useEffect` unchanged — no stage seeding needed since WebSocket backlog replay handles late-joining clients.

### `tests/test_live_pipeline.py`
- Added `MOCK_STAGES` constant with the 3 stage definitions as dicts.
- Updated 2 backlog test fixtures: `{"type": "pipeline_started", "total_packets": N}` → `{"type": "pipeline_started", "stages": MOCK_STAGES}`.
- Added 3 new tests:
  - `test_pipeline_started_contains_stages`: verifies `stages` present with correct structure, no `total_packets`.
  - `test_status_endpoint_returns_stages`: verifies GET `/api/mock/status` returns stages list.
  - `test_base_pipeline_manager_is_abstract`: verifies `BasePipelineManager()` raises `TypeError`.

### `tests/test_mock_api.py`
- `test_status_stopped_by_default` and `test_status_running`: changed from exact dict match (`== {"status": ...}`) to field check (`["status"] == ...`) since response now includes `stages`.

### `docs/pipeline/mock_pipeline.md`
- WebSocket message table: `pipeline_started` payload changed from `total_packets` to `stages (list of PipelineStageDefinition)`.

### `CLAUDE.md`
- Current State: mentions `BasePipelineManager`, `PipelineStageDefinition`, `PipelineStages` component, `PipelineStarted` carrying `stages`.
- Contracts description: mentions `PipelineStageDefinition`.
- API services: added `base_pipeline.py` entry, updated `live_pipeline.py` to note inheritance.
- `useLiveData` description: mentions stage tracking, updated return shape.
- Components list: added `PipelineStages`.
- Test count: 55 → 58 (live pipeline/WebSocket 6 → 9).
- Docs table: added `new_pipelines.md`.

## Design decisions

- **`useState` over TanStack Query cache for stages**: The build plan called for TanStack Query cache (`useQuery` with `enabled: false`). This hit two problems: (1) TanStack Query v5 requires a `queryFn` even when disabled and logs errors without one, (2) `invalidateQueries({ queryKey: ["live"] })` on `pipeline_complete` matches `["live", "stages"]` and triggers refetch attempts. Plain `useState` avoids both issues. Stage data comes exclusively from WebSocket messages (including backlog replay for late joiners), so there's no REST endpoint to fetch from anyway.
- **`_pre_run` hook instead of hardcoding `reset_db` in base**: The base class `start()` calls `_pre_run()` (no-op by default) before spawning the pipeline task. `LivePipelineManager` overrides it to call `reset_db()`. Future pipelines may not need DB resets.
- **No stage seeding from status poll**: Originally planned to seed stage cache from `GET /api/mock/status` response. Removed because WebSocket backlog replay already delivers `pipeline_started` → all increment messages on connect, producing correct counts. The status endpoint still returns `stages` (definitions only, no counts) for other consumers.
