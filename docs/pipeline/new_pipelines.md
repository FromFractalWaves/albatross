# Adding a New Pipeline

This document describes how to add a new data pipeline that integrates with the existing UI and WebSocket infrastructure.

## Overview

All pipeline managers inherit from `BasePipelineManager` (`api/services/base_pipeline.py`), which provides lifecycle management (start/stop), WebSocket subscriber fanout, message backlog for late-joining clients, and stage metadata. Subclasses declare their stages and implement the pipeline logic.

## Steps

### 1. Create a Pipeline Manager

Create a new file in `api/services/` that subclasses `BasePipelineManager`:

```python
from api.services.base_pipeline import BasePipelineManager
from contracts.ws import PipelineStageDefinition

class MyPipelineManager(BasePipelineManager):

    @property
    def pipeline_stages(self) -> list[PipelineStageDefinition]:
        return [
            PipelineStageDefinition(id="ingest", label="Ingest", message_type="packet_ingested"),
            PipelineStageDefinition(id="process", label="Process", message_type="packet_processed"),
        ]

    async def _run_pipeline(self, session_factory):
        # Broadcast pipeline_started with stage definitions
        await self._broadcast({
            "type": "pipeline_started",
            "stages": [s.model_dump() for s in self.pipeline_stages],
        })

        # ... pipeline logic ...
        # Broadcast per-packet messages with types matching message_type above

        await self._broadcast({
            "type": "pipeline_complete",
            "total_packets": count,
            "routing_records": records,
        })
```

Override `_pre_run(session_factory)` if you need setup before the pipeline task starts (e.g., database resets).

### 2. Register on `app.state`

In `api/main.py`, instantiate and attach the manager:

```python
app.state.my_pipeline_manager = MyPipelineManager()
```

### 3. Add Routes

Create a route file in `api/routes/` following the pattern in `api/routes/mock.py`:
- `POST /api/<source>/start` — calls `manager.start(session_factory)`
- `POST /api/<source>/stop` — calls `manager.stop()`
- `GET /api/<source>/status` — returns `{"status": manager.status, "stages": [...]}`
- `WebSocket /ws/live/<source>` — subscribes clients, sends backlog, listens for disconnect

### 4. Frontend

No frontend changes are needed. The live page at `/live/<source>` reads stage definitions from the status endpoint and WebSocket messages. The `PipelineStages` component renders whatever stages the pipeline declares.

## Notes

- `RunManager` (`api/services/runner.py`) is intentionally not based on `BasePipelineManager`. It manages multiple concurrent scenario runs with per-run subscribers — a different lifecycle model.
- Each per-packet message `type` must match the `message_type` declared in the stage definition for the UI count tracking to work.
- The base class manages `_task`, `_subscribers`, and `_messages`. Do not override `__init__` without calling `super().__init__()`.
