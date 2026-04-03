# Build Plan: Pipeline Observability

_Generated from spec — aligned with repo on 2026-04-03_

## Goal

Add pipeline stage visibility to the live UI so each stage shows packet progress in real time, driven entirely by pipeline-declared metadata — no hardcoded stage names in the frontend.

**Context:** See `specs/pipeline_observability_summaries.md` for current and target state.

## References

### Pre-build
| File | What it is | Why it's relevant |
|------|-----------|-------------------|
| `contracts/ws.py` | Pydantic WebSocket message types | Adding `PipelineStageDefinition` and `stages` field to `PipelineStarted` |
| `api/services/live_pipeline.py` | `LivePipelineManager` — in-process mock pipeline | Will inherit from new base class, declare stages, include stages in broadcast |
| `api/routes/mock.py` | Mock pipeline REST/WS routes | Status endpoint needs to return `stages` |
| `web/src/types/websocket.ts` | TypeScript WebSocket message types | Adding `PipelineStageDefinition` type and `stages` to `PipelineStartedMessage` |
| `web/src/hooks/useLiveData.ts` | Live data hook — WS + TanStack Query | Adding stage cache tracking and `stages` to return shape |
| `web/src/app/live/[source]/page.tsx` | Live page component | Seeding stage cache from status poll, dropping in `PipelineStages` component |
| `specs/mock.jsx` | UI mockup — design reference | Visual spec and state derivation logic for the `PipelineStages` component |
| `tests/test_live_pipeline.py` | Pipeline manager + WS tests | Existing test patterns to follow |
| `tests/test_mock_pipeline.py` | Mock pipeline DB tests | Existing test patterns to follow |

### Post-build
| File | What it will be | Why it's needed |
|------|----------------|-----------------|
| `api/services/base_pipeline.py` | Abstract base class for pipeline managers | Extracts lifecycle/fanout so future pipelines only implement stages + run logic |
| `web/src/components/PipelineStages.tsx` | Stage indicator strip component | Renders per-stage progress — the main UI deliverable |

## Plan

### Step 1: Add `PipelineStageDefinition` and update `PipelineStarted` in `contracts/ws.py`

**Files:** `contracts/ws.py`

Add a `PipelineStageDefinition` Pydantic model with fields `id: str`, `label: str`, `message_type: str`. Add a `stages: list[PipelineStageDefinition]` field to the existing `PipelineStarted` class with a default of `[]` so existing tests that construct `PipelineStarted` without stages don't break.

### Step 2: Create `BasePipelineManager` in `api/services/base_pipeline.py`

**Files:** `api/services/base_pipeline.py` (new)

Extract the lifecycle methods from `LivePipelineManager` into an abstract base class:
- `pipeline_stages` — abstract property returning `list[PipelineStageDefinition]`
- `status` — concrete property (derived from `self._task`)
- `start(session_factory)` — concrete (clears messages, resets DB, spawns task calling `_run_pipeline`)
- `stop()` — concrete (cancels task)
- `subscribe(ws)` / `unsubscribe(ws)` / `_broadcast(message)` — concrete
- `_run_pipeline(session_factory)` — abstract

The base class owns `_task`, `_subscribers`, and `_messages` attributes in `__init__`.

### Step 3: Retrofit `LivePipelineManager` to inherit from `BasePipelineManager`

**Files:** `api/services/live_pipeline.py`

- Change `LivePipelineManager` to inherit from `BasePipelineManager`.
- Remove `__init__`, `status`, `start`, `stop`, `subscribe`, `unsubscribe`, `_broadcast` — all inherited from base.
- Add the `pipeline_stages` property returning the three stage definitions (capture, preprocessing, routing) using `PipelineStageDefinition`.
- In `_run_pipeline`, update the `pipeline_started` broadcast dict to include `"stages": [s.model_dump() for s in self.pipeline_stages]`.
- Keep all stage methods (`_capture_stage`, `_preprocessing_stage`, `_routing_stage`) unchanged.

### Step 4: Extend `/api/mock/status` to return stages

**Files:** `api/routes/mock.py`

In `mock_status()`, return `stages` alongside `status`:

```python
return {
    "status": manager.status,
    "stages": [s.model_dump() for s in manager.pipeline_stages],
}
```

Always present regardless of pipeline status. No live counts — definition only.

### Step 5: Add `PipelineStageDefinition` type and `stages` to TypeScript types

**Files:** `web/src/types/websocket.ts`

Add a `PipelineStageDefinition` interface with `id: string`, `label: string`, `message_type: string`. Add `stages: PipelineStageDefinition[]` to `PipelineStartedMessage` (not `LivePipelineStarted` — the spec uses a wrong name; the actual type is `PipelineStartedMessage` at line 38).

### Step 6: Track per-stage counts in `useLiveData` via TanStack Query cache

**Files:** `web/src/hooks/useLiveData.ts`

Add a `StageState` type: `{ id: string; label: string; message_type: string; count: number; total: number }`.

Add a TanStack Query for `["live", "stages"]` — no fetcher needed, this is a cache-only key seeded from the page and updated from WebSocket messages.

Extend the existing WebSocket message handler switch statement:

- `pipeline_started`: reset stage counts to 0, set total from `msg.total_packets`, update stage definitions from `msg.stages` via `queryClient.setQueryData(["live", "stages"], ...)`.
- Add new cases for `packet_captured` and `packet_preprocessed`: find the stage whose `message_type` matches the incoming message type, increment its `count` via `queryClient.setQueryData`.
- `packet_routed` (existing case): add the same count-increment logic before the existing routing record handling.

Read `stages` from `useQuery({ queryKey: ["live", "stages"] })`. Add `stages` (defaulting to `[]`) to the hook's return object.

### Step 7: Seed stage cache from status poll in the live page

**Files:** `web/src/app/live/[source]/page.tsx`

In the existing `useEffect` that polls `GET /api/mock/status`, extend the response handling: when `data.stages` is present and the `["live", "stages"]` cache is empty, seed it with zero counts via `queryClient.setQueryData`. This requires importing `useQueryClient` and accessing the query client in the page component.

This ensures the stage strip renders immediately on page load — before any WebSocket message arrives or a pipeline run starts.

### Step 8: Build `PipelineStages` component

**Files:** `web/src/components/PipelineStages.tsx` (new)

Build the component following the design in `specs/mock.jsx` (`PipelineStrip`). Props:

```typescript
interface PipelineStagesProps {
  stages: StageState[]
  pipelineStatus: string
}
```

Per-stage visual state derivation (from the mockup):
- **done**: `count >= total && total > 0`
- **active**: pipeline is running, stage is not done, and (first stage OR previous stage has `count > 0`)
- **idle**: everything else

Renders a horizontal strip with: "Pipeline" label, chevron separators between stages, and per-stage: colored dot (green=done, purple with pulse animation=active, muted=idle), label, and `count/total` text (hidden when `total === 0`). Uses Tailwind classes matching the project's design tokens (surface background, border-bottom, JetBrains Mono font, accent colors).

Returns `null` if `stages` is empty — safe to render unconditionally.

### Step 9: Drop `PipelineStages` into the live page

**Files:** `web/src/app/live/[source]/page.tsx`

- Destructure `stages` from `useLiveData()`.
- Render `<PipelineStages stages={stages} pipelineStatus={pipelineStatus} />` between the `TopBar` and the pipeline controls section (the `{source === "mock" && ...}` block).
- Import `PipelineStages` from `@/components/PipelineStages`.

### Step 10: Write `docs/pipeline/new_pipelines.md`

**Files:** `docs/pipeline/new_pipelines.md` (exists, currently empty)

Document the workflow for adding a new pipeline:
1. Create a new manager class inheriting from `BasePipelineManager`.
2. Implement `pipeline_stages` (declare stages in order) and `_run_pipeline` (the actual pipeline logic).
3. Register the manager on `app.state` in `api/main.py`.
4. Add routes (start/stop/status/websocket) following the pattern in `api/routes/mock.py`.
5. The UI adapts automatically — no frontend changes needed.

## Testing

Existing tests in `test_live_pipeline.py` construct `LivePipelineManager` directly and test lifecycle + message collection. After the refactor:

- **Update existing tests**: `LivePipelineManager` import path stays the same. Tests that check `manager._messages` should still pass. The `pipeline_started` message in the backlog test (line 139) needs a `stages` field added.
- **Add test**: `pipeline_started` message contains `stages` with 3 entries whose `id`/`label`/`message_type` match the declared stage definitions.
- **Add test**: Status endpoint response includes `stages` list with correct definitions.
- **Add test**: `BasePipelineManager` cannot be instantiated directly (abstract methods enforced).

Follow existing patterns: in-memory SQLite via `pipeline_session_factory` fixture, patched `CAPTURE_INTERVAL`/`ASR_DELAY`/`TRMRouter`/`reset_db` for fast tests.

## Doc Updates

- `docs/pipeline/new_pipelines.md` — written in Step 10.
- `CLAUDE.md` — after build, update the "Current State" section to mention `BasePipelineManager` and pipeline observability. Update the `contracts/ws.py` description to mention `PipelineStageDefinition`. Update the `useLiveData.ts` description to mention stage tracking. Add `PipelineStages` to the components list. Add `base_pipeline.py` to the API services description.
