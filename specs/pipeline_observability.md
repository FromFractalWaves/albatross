# Pipeline Observability

## What This Is

Add pipeline stage visibility to the live UI. When the mock pipeline (or any future pipeline) is running, the UI shows each stage — how many packets have passed through, and whether the stage is active or done. No hardcoded stage names. The pipeline describes its own shape; the UI renders it.

This is scoped to basic stage visibility only. Health/stall detection is out of scope.

---

## Design Principle

The frontend must not know what stages exist. A new pipeline registers its stages at the API layer and the UI adapts automatically. Adding a pipeline means implementing the manager interface and declaring stages — no frontend changes.

---

## Architecture Note

This spec assumes the push-only mock pipeline (`specs/push_only_mock.md`) is already built. Stage counts come from WebSocket push — `useLiveData` already receives `packet_captured`, `packet_preprocessed`, and `packet_routed` messages and updates TanStack Query caches reactively. Stage state is derived from those same messages. There is no polling for stage counts.

`/api/mock/status` is used only for the initial page-load hydration of the stage *definition* (which stages exist and in what order). It does not serve live counts.

---

## What Changes

### 1. `PipelineStageDefinition` — new type in `contracts/ws.py`

Add a stage definition type alongside the existing WebSocket message types:

```python
class PipelineStageDefinition(BaseModel):
    id: str           # machine-readable, matches the message type prefix e.g. "capture"
    label: str        # display name e.g. "Capture"
    message_type: str # the ws message type that signals a packet completed this stage
                      # e.g. "packet_captured", "packet_preprocessed", "packet_routed"
```

Add a `stages` field to the existing `PipelineStarted` message type:

```python
class PipelineStarted(BaseModel):
    type: Literal["pipeline_started"]
    total_packets: int
    stages: list[PipelineStageDefinition]
```

The `stages` list is ordered — first to last in pipeline execution order.

Add `stages` to the `LivePipelineStarted` TypeScript type in `web/src/types/websocket.ts`:

```typescript
type LivePipelineStarted = {
  type: "pipeline_started"
  total_packets: number
  stages: PipelineStageDefinition[]
}

type PipelineStageDefinition = {
  id: string
  label: string
  message_type: string
}
```

### 2. `BasePipelineManager` — new base class in `api/services/base_pipeline.py`

Extract the interface that `LivePipelineManager` already implements into an abstract base class. Any future pipeline manager inherits from this.

```python
from abc import ABC, abstractmethod

class BasePipelineManager(ABC):

    @property
    @abstractmethod
    def pipeline_stages(self) -> list[PipelineStageDefinition]:
        """Declare the stages this pipeline exposes, in order."""
        ...

    @property
    def status(self) -> str:
        # concrete — derived from self._task
        ...

    async def start(self, session_factory) -> None:
        # concrete — resets DB, spawns task, calls _run_pipeline
        ...

    async def stop(self) -> None:
        # concrete — cancels task
        ...

    def subscribe(self, ws) -> None: ...
    def unsubscribe(self, ws) -> None: ...
    async def _broadcast(self, message: dict) -> None: ...

    @abstractmethod
    async def _run_pipeline(self, session_factory) -> None:
        """Implement the actual pipeline logic."""
        ...
```

The only thing a new pipeline *must* implement is `pipeline_stages` and `_run_pipeline`. Everything else — lifecycle, WebSocket fanout, message backlog — is inherited.

### 3. Retrofit `LivePipelineManager`

`LivePipelineManager` inherits from `BasePipelineManager` and declares its stages:

```python
class LivePipelineManager(BasePipelineManager):

    @property
    def pipeline_stages(self) -> list[PipelineStageDefinition]:
        return [
            PipelineStageDefinition(id="capture", label="Capture", message_type="packet_captured"),
            PipelineStageDefinition(id="preprocessing", label="Preprocessing", message_type="packet_preprocessed"),
            PipelineStageDefinition(id="routing", label="TRM Routing", message_type="packet_routed"),
        ]
```

Update the `pipeline_started` broadcast to include `stages`:

```python
await self._broadcast({
    "type": "pipeline_started",
    "total_packets": total,
    "stages": [s.model_dump() for s in self.pipeline_stages],
})
```

No other changes to `LivePipelineManager`.

### 4. REST hydration — include stages in `/api/mock/status`

The status endpoint returns the stage *definition* so the UI can render the `PipelineStages` component on page load before a WebSocket connection is established or a run has started.

Current response: `{"status": "running" | "stopped"}`

New response:

```json
{
  "status": "running",
  "stages": [
    {"id": "capture", "label": "Capture", "message_type": "packet_captured"},
    {"id": "preprocessing", "label": "Preprocessing", "message_type": "packet_preprocessed"},
    {"id": "routing", "label": "TRM Routing", "message_type": "packet_routed"}
  ]
}
```

`stages` is always present regardless of pipeline status. Counts are not included — those come from WebSocket push only.

### 5. Frontend — `useLiveData` tracks per-stage state via TanStack cache

Stage state is maintained in a dedicated TanStack Query cache key: `["live", "stages"]`. This key holds the full stages array with live counts merged in — the same shape the `PipelineStages` component consumes.

**Hydration (page load):**

Fetch `/api/mock/status` (already called by the live page for pipeline status). Use the returned `stages` definition to seed the cache with zero counts:

```typescript
queryClient.setQueryData(["live", "stages"], stages.map(s => ({
  ...s,
  count: 0,
  total: 0,
})))
```

**WebSocket push (real-time):**

In the existing WebSocket message handler inside `useLiveData`, extend the `pipeline_started` and stage message cases:

- `pipeline_started` — reset stage counts to 0, store `total_packets`, update stages definition in cache from `msg.stages`
- `packet_captured` / `packet_preprocessed` / `packet_routed` — find the stage in the cache whose `message_type` matches the incoming message type, increment its count via `queryClient.setQueryData`

```typescript
case "packet_captured": {
  queryClient.setQueryData(["live", "stages"], (prev: StageState[] | undefined) =>
    prev?.map(s => s.message_type === "packet_captured"
      ? { ...s, count: s.count + 1 }
      : s
    ) ?? prev
  )
  break
}
```

Same pattern for `packet_preprocessed` and `packet_routed`.

**Add `stages` to the hook return shape:**

```typescript
stages: Array<{
  id: string
  label: string
  message_type: string
  count: number     // packets that have completed this stage
  total: number     // total_packets from pipeline_started (0 until known)
}>
```

Derived from `useQuery(["live", "stages"])`. Returns an empty array if the cache is not yet populated — the `PipelineStages` component renders nothing in that case.

### 6. Frontend — `PipelineStages` component

New component: `web/src/components/PipelineStages.tsx`

Renders a compact horizontal strip of stage indicators between the top bar and the pipeline controls. Each stage shows:
- A colored dot (green = done, purple pulsing = active, muted = idle)
- Stage label
- `count / total` packet progress (hidden when `total === 0`)

Visual state derivation:
- `done` — `count >= total && total > 0`
- `active` — pipeline is running AND this stage is not done AND the previous stage has `count > 0` (or it is the first stage)
- `idle` — everything else

Props:

```typescript
interface PipelineStagesProps {
  stages: StageState[]      // from useLiveData
  pipelineStatus: string    // "running" | "stopped"
}
```

If `stages` is empty, renders nothing. No domain knowledge — it renders whatever it receives.

Placement in `live/[source]/page.tsx`: between the `TopBar` and the existing pipeline controls block. The strip uses the same surface background and border-bottom as the top bar — it reads as part of the chrome, not as page content.

See `specs/pipeline_observability_mockup.jsx` for the full reference implementation including state derivation logic.

---

## Adding a New Pipeline

See `docs/pipeline/new_pipelines.md`.

---

## What Does Not Change

- `RunManager` (scenario path) — untouched. Scenarios don't use the pipeline observability component.
- `useRunSocket` — untouched.
- All existing WebSocket message shapes except `pipeline_started` (additive change only — `stages` field added).
- The live page tab content — thread lanes, events, timeline are unaffected.
- DB schema — no changes.
- The three existing REST hydration endpoints (`/api/live/threads`, `/events`, `/transmissions`) — unchanged.

---

## Files Affected

| File | Change |
|------|--------|
| `contracts/ws.py` | Add `PipelineStageDefinition`, add `stages` to `PipelineStarted` |
| `api/services/base_pipeline.py` | New — abstract base class |
| `api/services/live_pipeline.py` | Inherit from base, declare stages, add `stages` to `pipeline_started` broadcast |
| `api/routes/mock.py` | Extend `/api/mock/status` response to include `stages` definition |
| `web/src/types/websocket.ts` | Add `stages` to `LivePipelineStarted`, add `PipelineStageDefinition` type |
| `web/src/hooks/useLiveData.ts` | Seed stage cache on status fetch, handle `stages` in `pipeline_started`, increment counts on stage messages, add `stages` to return shape |
| `web/src/components/PipelineStages.tsx` | New — stage indicator strip component |
| `web/src/app/live/[source]/page.tsx` | Seed stage cache from status fetch on mount, pass `stages` + `pipelineStatus` to `PipelineStages`, place above pipeline controls |
| `docs/pipeline/new_pipelines.md` | New — adding a pipeline workflow doc |