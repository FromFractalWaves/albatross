# Pipeline Observability

## What This Is

Add pipeline stage visibility to the live UI. When the mock pipeline (or any future pipeline) is running, the UI shows each stage — how many packets have passed through, and whether the stage is active or done. No hardcoded stage names. The pipeline describes its own shape; the UI renders it.

This is scoped to basic stage visibility only. Health/stall detection is out of scope.

---

## Design Principle

The frontend must not know what stages exist. A new pipeline registers its stages at the API layer and the UI adapts automatically. Adding a pipeline means implementing the manager interface and declaring stages — no frontend changes.

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

The status endpoint needs to return the pipeline definition so the UI can build the observability component on page refresh without waiting for a WebSocket message.

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

`stages` is always present regardless of status. When stopped, it still describes what the pipeline looks like so the component can render before a run starts.

### 5. Frontend — `useLiveData` tracks per-stage counts

`useLiveData` already receives `packet_captured`, `packet_preprocessed`, `packet_routed` messages. Add stage count tracking:

- On `pipeline_started`: store the `stages` definition in hook state. Reset all stage counts to 0.
- On any stage message: find the stage whose `message_type` matches, increment its count.
- On page load: fetch `/api/mock/status` to get the stages definition (already polled for status — extend the response shape).

Add `stages` to the hook return shape:

```typescript
stages: Array<{
  id: string
  label: string
  count: number        // packets that have completed this stage
  total: number        // total_packets from pipeline_started (0 until known)
}>
```

### 6. Frontend — `PipelineStages` component

New component: `web/src/components/PipelineStages.tsx`

Renders a horizontal row of stage indicators. Each stage shows:
- Stage label
- `count / total` packet progress
- Visual state: idle (not started), active (count < total and pipeline running), done (count === total)

Drops in to `live/[source]/page.tsx` above the tab bar. Receives `stages` from `useLiveData`. If `stages` is empty, renders nothing — so pages without observability data are unaffected.

No domain knowledge in the component. It renders whatever it receives.

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

---

## Files Affected

| File | Change |
|------|--------|
| `contracts/ws.py` | Add `PipelineStageDefinition`, add `stages` to `PipelineStarted` |
| `api/services/base_pipeline.py` | New — abstract base class |
| `api/services/live_pipeline.py` | Inherit from base, declare stages, add `stages` to `pipeline_started` broadcast |
| `api/routes/mock.py` | Extend `/api/mock/status` response to include `stages` |
| `web/src/hooks/useLiveData.ts` | Track per-stage counts, add `stages` to return shape |
| `web/src/components/PipelineStages.tsx` | New — stage indicator component |
| `web/src/app/live/[source]/page.tsx` | Drop in `PipelineStages` above tab bar |
| `web/src/types/websocket.ts` | Add `stages` to `PipelineStarted` type |
| `docs/pipeline/new_pipelines.md` | New — adding a pipeline workflow doc |