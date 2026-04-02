# Build Plan: Push-Only Mock Pipeline

_Generated from `specs/push_only_mock.md` — aligned with repo on 2026-04-02_

## Goal

Replace the poll-based mock pipeline (three subprocess scripts + DB-as-IPC + REST polling) with a push-based pipeline that runs inside the API process and streams stage-level messages over WebSocket, matching the architecture scenario runs already use.

## Context

The scenario path already has the push pattern: `RunManager` in `api/services/runner.py` orchestrates `PacketLoader → PacketQueue → TRMRouter` as async tasks and broadcasts messages over WebSocket via a subscriber list. `useRunSocket.ts` on the frontend receives these messages and updates state via `useReducer`.

The live mock pipeline currently runs as three separate scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) that use the DB as IPC. The frontend polls three REST endpoints every 3 seconds via `useLiveData.ts`.

This plan brings the live path up to the same push standard while keeping the REST endpoints as the hydration layer for page refreshes.

**Key files that already exist and will be modified:**
- `api/services/runner.py` — RunManager pattern to replicate
- `api/routes/mock.py` — mock control endpoints (start/stop/status)
- `api/routes/live.py` — REST hydration endpoints (unchanged, but gets a WebSocket endpoint)
- `api/main.py` — app wiring
- `web/src/hooks/useLiveData.ts` — replaced by new hook
- `web/src/app/live/[source]/page.tsx` — switches to new hook
- `live.sh` — deleted
- `tests/test_mock_api.py` — updated for new mock control
- `tests/test_live_api.py` — updated for WebSocket

**Key files that stay untouched:**
- `api/services/runner.py` — scenario RunManager is not modified
- `api/routes/runs.py` — scenario WebSocket stays as-is
- `web/src/hooks/useRunSocket.ts` — scenario hook stays as-is
- `trm/pipeline/router.py` — TRMRouter is used as-is
- `db/persist.py` — `persist_routing_result()` is called from the new pipeline
- `contracts/models.py` — boundary types unchanged
- `capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py` — kept for standalone use, but no longer launched by the API

## Plan

### Step 1: LivePipelineManager service

**Files:** `api/services/live_pipeline.py` (new)

Create `LivePipelineManager`, modeled after `RunManager` in `api/services/runner.py`. This class orchestrates the mock pipeline as coordinated async tasks inside the API process.

**Structure:**
- `LivePipelineManager` with `status`, `subscribers: list[WebSocket]`, `messages: list[dict]` (backlog for late-joining clients), and a `task` handle for the background pipeline.
- `start()` — resets DB via `reset_db()`, creates two `asyncio.Queue`s (captured → preprocessed, preprocessed → routed), spawns three async tasks (`_capture`, `_preprocess`, `_route`), broadcasts `pipeline_started`.
- `stop()` — cancels the pipeline task, broadcasts `pipeline_complete`, clears state.
- `subscribe(ws)` / `unsubscribe(ws)` — manages WebSocket subscribers. On subscribe, sends full message backlog (same pattern as `RunManager`).
- `_broadcast(message)` — appends to backlog, sends to all connected subscribers.

**Three internal async tasks:**

`_capture()`:
- Reads `packets_radio.json` (same source as `capture/mock/run.py`)
- For each packet: constructs `TransmissionPacket`, calls `to_orm()`, writes to DB with `status='captured'`, puts packet data on `captured_queue`, broadcasts `packet_captured` message, sleeps 10s.
- After all packets: puts `None` sentinel on queue.

`_preprocess(captured_queue, preprocessed_queue)`:
- Consumes from `captured_queue`.
- For each packet: updates DB row to `status='processing'`, sleeps 10s (simulated ASR), writes text + ASR metadata to DB, updates to `status='processed'`, puts packet data on `preprocessed_queue`, broadcasts `packet_preprocessed` message.
- On `None` sentinel: passes it through to `preprocessed_queue`.

`_route(preprocessed_queue)`:
- Creates `TRMRouter(buffers=5)`.
- Consumes from `preprocessed_queue`.
- For each packet: builds `ReadyPacket`, updates DB to `status='routing'`, calls `await router.route(packet)`, calls `await persist_routing_result(session, packet_id, record, router.context)`, broadcasts `packet_routed` message (same shape as scenario: `routing_record`, `context`, `incoming_packet`).
- On `None` sentinel: broadcasts `pipeline_complete`.

**Message shapes:**
```
pipeline_started:  { type, source }
packet_captured:   { type, packet_id, timestamp }
packet_preprocessed: { type, packet_id, timestamp, text }
packet_routed:     { type, packet_id, routing_record, context, incoming_packet }
pipeline_complete: { type, total_packets }
```

### Step 2: WebSocket endpoint for live pipeline

**Files:** `api/routes/live.py` (modify)

Add a WebSocket endpoint to the existing live routes:

`ws://localhost:8000/ws/live/{source}`:
- Accept WebSocket connection.
- Look up `LivePipelineManager` from `app.state.live_pipeline`.
- Call `subscribe(ws)` — this sends the message backlog.
- Keep connection open (recv loop) until client disconnects or pipeline ends.
- On disconnect: call `unsubscribe(ws)`.

The existing REST endpoints (`GET /api/live/threads`, `/events`, `/transmissions`) stay unchanged — they remain the hydration layer.

### Step 3: Update mock control API

**Files:** `api/routes/mock.py` (modify)

Replace the subprocess-based control with `LivePipelineManager`:

`POST /api/mock/start`:
- Get `LivePipelineManager` from `app.state.live_pipeline`.
- If already running, return error.
- Call `await manager.start()`.
- Return `{"status": "started"}`.

`POST /api/mock/stop`:
- Call `await manager.stop()`.
- Return `{"status": "stopped"}`.

`GET /api/mock/status`:
- Return `{"status": manager.status}` (values: `"running"`, `"stopped"`, `"complete"`).

Remove all subprocess management code (`asyncio.create_subprocess_exec`, `app.state.mock_processes`, process termination logic).

### Step 4: Wire LivePipelineManager into the app

**Files:** `api/main.py` (modify)

- Import `LivePipelineManager` from `api.services.live_pipeline`.
- Replace `app.state.mock_processes = []` with `app.state.live_pipeline = LivePipelineManager()`.
- No new routers needed — the WebSocket endpoint is added to the existing `live_router`.

### Step 5: Install TanStack Query

**Files:** `web/package.json` (modify via npm)

```
cd web && npm install @tanstack/react-query
```

Add `QueryClientProvider` to `web/src/app/layout.tsx`:
- Create a client-side `QueryClient` instance.
- Wrap children in `QueryClientProvider`.

### Step 6: New frontend hook — useLivePipeline

**Files:** `web/src/hooks/useLivePipeline.ts` (new)

Create a hook that combines TanStack Query for REST hydration with WebSocket for live updates. It must return the same state shape as `useLiveData` so the live page needs minimal changes.

**Hydration (TanStack Query):**
- `useQuery` for `/api/live/threads`, `/api/live/events`, `/api/live/transmissions` — fetches on mount, provides initial data.
- These queries have a long `staleTime` — WebSocket updates keep the cache current, no polling needed.

**Live updates (WebSocket):**
- Opens WebSocket to `ws://localhost:8000/ws/live/{source}`.
- On `packet_routed` messages: calls `queryClient.setQueryData` to update the threads, events, and transmissions caches reactively.
- On `packet_captured` and `packet_preprocessed`: updates a local `pipelineStages` state so the UI can show where packets are in the pipeline.
- On `pipeline_started` / `pipeline_complete`: updates status.

**Return type** — same shape as current `useLiveData`:
```typescript
{
  status: "loading" | "ready" | "empty" | "error"
  context: TRMContext | null
  routingRecords: RoutingRecord[]
  latestPacketId: string | null
  error: string | null
  pipelineStages: PipelinePacket[]  // new: packets in-flight (captured, preprocessing)
}
```

The `pipelineStages` field is new — it tracks packets that have entered the pipeline but haven't been routed yet. The live page can use this for observability (showing packets moving through stages).

### Step 7: Add WebSocket message types for live pipeline

**Files:** `web/src/types/websocket.ts` (modify)

Add new message types to the discriminated union:

```typescript
PipelineStartedMessage { type: "pipeline_started"; source: string }
PacketCapturedMessage  { type: "packet_captured"; packet_id: string; timestamp: string }
PacketPreprocessedMessage { type: "packet_preprocessed"; packet_id: string; timestamp: string; text: string }
PipelineCompleteMessage { type: "pipeline_complete"; total_packets: number }
```

`packet_routed` already exists and is reused with the same shape.

Create a separate `LiveWSMessage` union type (distinct from the scenario `WSMessage`) to keep the two paths cleanly separated.

### Step 8: Update the live page

**Files:** `web/src/app/live/[source]/page.tsx` (modify)

- Replace `useLiveData()` with `useLivePipeline(source)`.
- The page already destructures `{ status, context, routingRecords, latestPacketId }` — these keep working.
- Remove the manual `/api/mock/status` polling — the pipeline status is now delivered via WebSocket.
- The mock start/stop buttons stay but call the same `POST /api/mock/start` and `/stop` endpoints.
- Optionally show `pipelineStages` in a new section or badge to indicate packets in-flight (captured but not yet routed). This is additive — existing components are unchanged.

### Step 9: Delete live.sh

**Files:** `live.sh` (delete)

Delete `live.sh`. The pipeline now runs inside the API process and is started from the UI via the existing start button on `/live/mock` (`POST /api/mock/start`). `dev.sh` already launches the API and frontend — that's all you need. There is no auto-start.

### Step 10: Update tests

**Files:** `tests/test_mock_api.py` (modify), `tests/test_live_api.py` (modify), `tests/test_live_pipeline.py` (new)

**`tests/test_live_pipeline.py`** (new):
- Test `LivePipelineManager` directly — start, verify messages are broadcast in correct order (`pipeline_started` → `packet_captured` → `packet_preprocessed` → `packet_routed` → `pipeline_complete`), verify DB state after routing.
- Mock `TRMRouter` the same way `test_runs.py` does (patch `TRMRouter` class, return predictable routing records).
- Use in-memory SQLite and dependency override for `get_session`.

**`tests/test_mock_api.py`** (modify):
- Remove subprocess mocking (`asyncio.create_subprocess_exec` patches).
- Mock `LivePipelineManager.start()` / `stop()` instead.
- Test that `POST /api/mock/start` calls `manager.start()`, `POST /api/mock/stop` calls `manager.stop()`, `GET /api/mock/status` returns manager status.

**`tests/test_live_api.py`** (modify):
- Add WebSocket test: connect to `/ws/live/mock`, verify backlog delivery, verify message format.
- Existing REST endpoint tests (`/api/live/threads`, `/events`, `/transmissions`) stay unchanged.

## Testing

- Mock `TRMRouter` in pipeline tests (same pattern as `test_runs.py` — patch the class, return deterministic routing records) so tests don't need an API key.
- Use in-memory SQLite for DB tests (same pattern as `test_live_api.py` with `get_session` override).
- WebSocket tests use `TestClient` from starlette (same pattern as `test_runs.py`).
- Verify the full message sequence: `pipeline_started` → N × (`packet_captured` → `packet_preprocessed` → `packet_routed`) → `pipeline_complete`.
- Verify DB state after pipeline completes: transmissions have `status='routed'`, threads and events exist.
- Verify late-joining WebSocket clients receive the message backlog.

## Doc Updates

After implementation, update:
- `CLAUDE.md` — update "Current State" section (live pipeline is now push-based), update "Running" section (remove `live.sh`, pipeline starts from UI), update Architecture sections for `api/services/live_pipeline.py` and modified routes/hooks.
- `docs/pipeline/mock_pipeline.md` — rewrite to reflect in-process pipeline architecture instead of subprocess-based.
- `docs/web/api.md` — add `/ws/live/{source}` WebSocket endpoint, update mock control API docs, document new message types.
- `docs/web/ui_spec.md` — document pipeline stage observability if `pipelineStages` is surfaced in the UI.
