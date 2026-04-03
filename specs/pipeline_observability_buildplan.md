# Build Plan: Pipeline Observability

_Generated from spec — aligned with repo on 2026-04-03_

## Goal

Add pipeline stage visibility to the live UI so each stage shows an incrementing packet count in real time, driven entirely by pipeline-declared metadata — no hardcoded stage names in the frontend.

**Context:** See `specs/pipeline_observability_summaries.md` for current and target state.

## References

### Pre-build
| File | What it is | Why it's relevant |
|------|-----------|-------------------|
| `contracts/ws.py` | Pydantic WebSocket message types | Adding `PipelineStageDefinition`, adding `stages` to `PipelineStarted`, removing `total_packets` from `PipelineStarted` |
| `api/services/live_pipeline.py` | `LivePipelineManager` — in-process mock pipeline | Will inherit from new base class, declare stages, update `pipeline_started` broadcast |
| `api/routes/mock.py` | Mock pipeline REST/WS routes | Status endpoint needs to return `stages` |
| `web/src/types/websocket.ts` | TypeScript WebSocket message types | Adding `PipelineStageDefinition` type, updating `PipelineStartedMessage` |
| `web/src/hooks/useLiveData.ts` | Live data hook — WS + TanStack Query | Adding stage cache tracking, removing `pipelineTotal`, adding `stages` to return shape |
| `web/src/app/live/[source]/page.tsx` | Live page component | Seeding stage cache from status poll, dropping in `PipelineStages` component |
| `specs/mock.jsx` | UI mockup — design reference | Visual spec for the `PipelineStages` component (vertical rows, index-based colors, count-only) |
| `tests/test_live_pipeline.py` | Pipeline manager + WS tests | Existing test patterns; backlog fixture needs `pipeline_started` shape updated |

### Post-build
| File | What it will be | Why it's needed |
|------|----------------|-----------------|
| `api/services/base_pipeline.py` | Abstract base class for pipeline managers | Extracts lifecycle/fanout so future pipelines only implement stages + run logic |
| `web/src/components/PipelineStages.tsx` | Stage indicator strip component | Renders per-stage counts — the main UI deliverable |

## Plan

### Step 1: Add `PipelineStageDefinition` and update `PipelineStarted` in `contracts/ws.py`

**Files:** `contracts/ws.py`

Add a `PipelineStageDefinition` Pydantic model with fields `id: str`, `label: str`, `message_type: str`.

Update `PipelineStarted`: remove `total_packets: int`, add `stages: list[PipelineStageDefinition]` with default `[]`. Leave `PipelineComplete.total_packets` unchanged — it still reports how many packets were processed at the end.

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
- In `_run_pipeline`, update the `pipeline_started` broadcast: remove `total_packets`, add `"stages": [s.model_dump() for s in self.pipeline_stages]`.
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

Always present regardless of pipeline status. Definition only — no live counts.

### Step 5: Update TypeScript types

**Files:** `web/src/types/websocket.ts`

Add a `PipelineStageDefinition` interface with `id: string`, `label: string`, `message_type: string`.

Update `PipelineStartedMessage` (the spec calls this `LivePipelineStarted` but the actual type name is `PipelineStartedMessage`): remove `total_packets: number`, add `stages: PipelineStageDefinition[]`.

### Step 6: Track per-stage counts in `useLiveData` via TanStack Query cache

**Files:** `web/src/hooks/useLiveData.ts`

Add a `StageState` type: `{ id: string; label: string; message_type: string; count: number }`.

Remove the `pipelineTotal` state variable and its `setPipelineTotal` setter — totals are no longer tracked.

Add a TanStack Query for `["live", "stages"]` — no fetcher needed, this is a cache-only key seeded from the page and updated from WebSocket messages.

Extend the WebSocket message handler switch statement:

- `pipeline_started`: remove `setPipelineTotal(msg.total_packets)`. Reset stage counts to 0 and update stages definition in cache from `msg.stages` via `queryClient.setQueryData(["live", "stages"], msg.stages.map(s => ({ ...s, count: 0 })))`. Read only `msg.stages` — do not read `total_packets` even if present in the message. During a transition, stale backlog messages may still carry the old field; ignore it entirely.
- Add new cases for `packet_captured` and `packet_preprocessed`: find the stage whose `message_type` matches the incoming message type, increment its `count` via `queryClient.setQueryData`.
- `packet_routed` (existing case): add the same count-increment logic before the existing routing record handling.

Read `stages` from `useQuery({ queryKey: ["live", "stages"] })`. Add `stages` (defaulting to `[]`) to the hook's return object.

### Step 7: Seed stage cache from status poll in the live page

**Files:** `web/src/app/live/[source]/page.tsx`

In the existing `useEffect` that polls `GET /api/mock/status`, extend the response handling: when `data.stages` is present and the `["live", "stages"]` cache is empty, seed it with zero counts via `queryClient.setQueryData(["live", "stages"], data.stages.map(s => ({ ...s, count: 0 })))`. This requires importing `useQueryClient` and accessing the query client in the page component.

### Step 8: Build `PipelineStages` component

**Files:** `web/src/components/PipelineStages.tsx` (new)

Build the component following the design in `specs/mock.jsx` (`PipelineStrip`). Props:

```typescript
interface PipelineStagesProps {
  stages: StageState[]
}
```

No `pipelineStatus` prop — the component is state-agnostic. It renders counts, period.

Layout: vertical column of stage rows. Each row shows:
- `[stage.id]` in a fixed color assigned by index (blue, amber, purple, with muted as fallback for additional stages)
- `stage.count` in the same color (muted gray `#3a3a55` when count is 0)

Styling: JetBrains Mono, 11px font, 12px/700 for counts, `#060610` background, `1px solid` border-bottom matching top bar border color. Stage ID column is 110px fixed width.

Returns `null` if `stages` is empty.

### Step 9: Drop `PipelineStages` into the live page

**Files:** `web/src/app/live/[source]/page.tsx`

- Destructure `stages` from `useLiveData()`.
- Render `<PipelineStages stages={stages} />` between the `TopBar` and the pipeline controls section (the `{source === "mock" && ...}` block).
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

Existing tests in `test_live_pipeline.py` need updates and additions:

- **Update backlog test fixture** (line 139): change `{"type": "pipeline_started", "total_packets": 2}` to `{"type": "pipeline_started", "stages": [...]}` with the three stage definitions.
- **Add test**: `pipeline_started` message contains `stages` with 3 entries whose `id`/`label`/`message_type` match the declared stage definitions and no `total_packets` field.
- **Add test**: Status endpoint response includes `stages` list with correct definitions.
- **Add test**: `BasePipelineManager` cannot be instantiated directly (abstract methods enforced).

Follow existing patterns: in-memory SQLite via `pipeline_session_factory` fixture, patched `CAPTURE_INTERVAL`/`ASR_DELAY`/`TRMRouter`/`reset_db` for fast tests.

## Doc Updates

- `docs/pipeline/new_pipelines.md` — written in Step 10.
- `CLAUDE.md` — update Current State to mention `BasePipelineManager` and pipeline observability. Update `contracts/ws.py` description to mention `PipelineStageDefinition`. Update `useLiveData.ts` description to mention stage tracking. Add `PipelineStages` to the components list. Add `base_pipeline.py` to the API services description. Note `PipelineStarted` no longer carries `total_packets`.
- `docs/pipeline/mock_pipeline.md` — update the WebSocket message table (line 82): change `pipeline_started` payload from `total_packets` to `stages` (list of `PipelineStageDefinition`).
