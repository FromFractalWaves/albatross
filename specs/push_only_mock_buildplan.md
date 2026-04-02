# Build Plan: Push-Only Mock Pipeline

_Generated from `specs/push_only_mock.md` — aligned with repo on 2026-04-02_

## Goal

Replace the subprocess + DB-polling mock pipeline with an in-process async pipeline that pushes stage-level messages over WebSocket, so the live dashboard updates in real time without polling.

## Context

The scenario path already has the push pattern: `RunManager` in `api/services/runner.py` orchestrates `PacketLoader` → `PacketQueue` → `TRMRouter`, broadcasting `packet_routed` messages over WebSocket via `api/routes/runs.py`. The live path currently polls: `useLiveData.ts` fetches `/api/live/threads`, `/events`, `/transmissions` every 3 seconds.

The new live pipeline reuses `PacketQueue` and `TRMRouter` from `trm/pipeline/` but adds capture and preprocessing as async queue stages instead of DB-polling subprocesses. The DB remains the persistence layer — packets are written to it at each stage for hydration — but the live data path is WebSocket push.

**Key files that already exist and will be reused:**
- `trm/pipeline/queue.py` — `PacketQueue` (async queue wrapper)
- `trm/pipeline/router.py` — `TRMRouter` (stateful LLM routing)
- `db/persist.py` — `persist_routing_result()` (atomic DB writes)
- `api/services/runner.py` — `RunManager` (pattern reference for broadcasting)
- `api/routes/mock.py` — mock control endpoints (will be rewritten)
- `api/routes/live.py` — REST hydration endpoints (unchanged)
- `web/src/hooks/useLiveData.ts` — polling hook (will be rewritten)
- `web/src/hooks/useRunSocket.ts` — WebSocket hook (pattern reference)
- `web/src/types/websocket.ts` — message types (will be extended)

## Plan

### Step 1: Add WebSocket message types for stage-level pipeline events

**Files:** `contracts/ws.py` (new)

Define Pydantic models for the live pipeline WebSocket messages. These are separate from the scenario `WSMessage` types — the scenario path is untouched.

Message types:
- `PipelineStarted` — `{"type": "pipeline_started", "total_packets": int}`
- `PacketCaptured` — `{"type": "packet_captured", "packet_id": str, "timestamp": str, "metadata": dict}`
- `PacketPreprocessed` — `{"type": "packet_preprocessed", "packet_id": str, "text": str}`
- `PacketRouted` — `{"type": "packet_routed", "packet_id": str, "routing_record": dict, "context": dict, "incoming_packet": dict | None}` (same shape as the existing scenario `packet_routed`)
- `PipelineComplete` — `{"type": "pipeline_complete", "total_packets": int, "routing_records": list}`
- `PipelineError` — `{"type": "pipeline_error", "error": str}`

Each model has a `.to_dict()` method (or use `model_dump()`) for JSON serialization over WebSocket.

### Step 2: Build the in-process mock pipeline manager

**Files:** `api/services/live_pipeline.py` (new)

Create `LivePipelineManager` — analogous to `RunManager` but for the live mock pipeline. It manages a single pipeline instance (not per-run like `RunManager`).

**State:**
- `_task: asyncio.Task | None` — the running pipeline task
- `_subscribers: list[WebSocket]` — connected WebSocket clients
- `_messages: list[dict]` — message backlog for late-joining clients (same pattern as `RunManager.Run.messages`)
- `_router: TRMRouter | None` — the live router instance (needed for context access)

**Methods:**
- `async start(session_factory)` — if not already running, reset DB, start the pipeline as an asyncio task. Return immediately.
- `async stop()` — cancel the task, clean up.
- `status() -> str` — `"running"` or `"stopped"`.
- `subscribe(ws: WebSocket)` — add to subscribers, send backlog.
- `unsubscribe(ws: WebSocket)` — remove from subscribers.
- `async _broadcast(message: dict)` — append to backlog, send to all subscribers, remove dead connections.

**Pipeline task (`_run_pipeline`):**

Three async stages connected by two `PacketQueue` instances:

1. **Capture stage** — reads `packets_radio.json`, for each entry: construct `TransmissionPacket`, call `to_orm()`, write to DB with `status='captured'`, put raw packet data onto `capture_queue`, broadcast `packet_captured`. Sleep 10s between packets. Send `None` sentinel when done.

2. **Preprocessing stage** — consumes from `capture_queue`. For each packet: update DB row to `status='processing'`, sleep to simulate ASR delay (shorter than 10s — use 3s for responsiveness), update DB row with text + ASR fields + `status='processed'`, put `ReadyPacket` onto `routing_queue`, broadcast `packet_preprocessed`. Forward `None` sentinel.

3. **Routing stage** — consumes from `routing_queue`. For each `ReadyPacket`: update DB row to `status='routing'`, call `router.route(packet)`, call `persist_routing_result()`, broadcast `packet_routed` (with full context and routing record). After all packets: broadcast `pipeline_complete`.

Wrap all three stages in a `asyncio.gather()` call, with `pipeline_started` broadcast before and error handling around it.

The DB session factory is passed in from the FastAPI dependency. Each stage creates its own session from the factory for its DB operations.

### Step 3: Add WebSocket endpoint and rewrite mock control routes

**Files:** `api/routes/mock.py`

Rewrite the existing mock routes:

- `POST /api/mock/start` — calls `live_pipeline_manager.start(session_factory)` instead of spawning subprocesses. The `session_factory` comes from `db.session` (the existing `async_sessionmaker`). Resets DB before starting (same as current behavior).
- `POST /api/mock/stop` — calls `live_pipeline_manager.stop()` instead of terminating processes.
- `GET /api/mock/status` — calls `live_pipeline_manager.status()` instead of checking process liveness.

Add new WebSocket endpoint:
- `ws://localhost:8000/ws/live/mock` — accepts WebSocket connection, calls `live_pipeline_manager.subscribe(ws)`, enters receive loop (to detect disconnects), calls `unsubscribe` on disconnect. Same pattern as the `/ws/runs/{run_id}` endpoint in `api/routes/runs.py`.

### Step 4: Register the pipeline manager on app state

**Files:** `api/main.py`

Add `app.state.live_pipeline_manager = LivePipelineManager()` alongside the existing `app.state.run_manager` and `app.state.mock_processes`.

Remove `app.state.mock_processes` — it's no longer used since the pipeline is in-process.

Pass the manager to the mock routes (either via `request.app.state` as currently done, or via FastAPI dependency injection).

### Step 5: Add frontend WebSocket message types

**Files:** `web/src/types/websocket.ts`

Add the live pipeline message types as a separate discriminated union (do not modify the existing `WSMessage` type):

```
LivePipelineStarted  — { type: "pipeline_started", total_packets: number }
LivePacketCaptured   — { type: "packet_captured", packet_id: string, timestamp: string, metadata: Record<string, unknown> }
LivePacketPreprocessed — { type: "packet_preprocessed", packet_id: string, text: string }
LivePacketRouted     — { type: "packet_routed", packet_id: string, routing_record: RoutingRecord, context: TRMContext, incoming_packet: ReadyPacket | null }
LivePipelineComplete — { type: "pipeline_complete", total_packets: number, routing_records: RoutingRecord[] }
LivePipelineError    — { type: "pipeline_error", error: string }
```

Union type: `LiveWSMessage`

### Step 6: Install TanStack Query and add provider

**Files:** `web/package.json`, `web/src/app/layout.tsx`, `web/src/app/providers.tsx` (new)

Install `@tanstack/react-query`. Create a `Providers` component with `QueryClientProvider` and wrap the app layout's children with it. Use `"use client"` directive on the providers file since `QueryClientProvider` needs client-side React context.

### Step 7: Rewrite useLiveData as WebSocket + TanStack Query hook

**Files:** `web/src/hooks/useLiveData.ts`

Rewrite the hook to:

1. **Hydration** — use TanStack Query's `useQuery` to fetch `/api/live/threads`, `/events`, `/transmissions` on mount. This replaces the manual `fetch` + `useEffect` pattern. The queries provide the initial state on page load or refresh.

2. **WebSocket** — open a connection to `${WS_BASE}/ws/live/mock` when the pipeline is running. Parse incoming `LiveWSMessage` messages and update the TanStack Query cache via `queryClient.setQueryData()`:
   - `packet_routed` — append to transmissions cache, update threads/events caches from the included `context`.
   - `packet_captured` / `packet_preprocessed` — update a local pipeline stage state (for observability UI, optional in v1).
   - `pipeline_complete` — invalidate all queries to re-fetch final state.

3. **Return shape** — same as current `useLiveData` plus `incomingPacket`:
   ```
   { status, context, routingRecords, latestPacketId, incomingPacket, error }
   ```
   Build `context` and `routingRecords` from the TanStack Query cache data, same reconstruction logic as the current hook. When a `packet_routed` message arrives with full `context`, use that directly instead of reconstructing.

4. **Connection lifecycle** — connect WebSocket after the pipeline is started (the live page already polls `/api/mock/status`). Reconnect on close with backoff. Disconnect on unmount.

### Step 8: Update the live page to use WebSocket-driven state

**Files:** `web/src/app/live/[source]/page.tsx`

Minimal changes:
- The hook return shape is compatible, so `threadColorMap`, `decisionMap`, `timelinePackets` derivations stay the same.
- Add `incomingPacket` to the `ContextInspector` props (currently hardcoded to `null`).
- Optionally add an `IncomingBanner` when `incomingPacket` is non-null (reuses the component from the run page).
- The mock pipeline controls (`Start` / `Stop` buttons) stay — they still call `/api/mock/start` and `/api/mock/stop`. The status polling can be replaced by deriving status from the WebSocket connection state.

### Step 9: Delete live.sh

**Files:** `live.sh` (delete)

Remove `live.sh`. The pipeline is now started from the UI via `POST /api/mock/start`. `dev.sh` is the only launch script needed.

### Step 10: Update CLAUDE.md running instructions

**Files:** `CLAUDE.md`

Remove the `live.sh` references from the Running section. Update the mock pipeline description to reflect that it runs in-process via the API. Remove the manual pipeline launch instructions (the `python capture/mock/run.py &` block) or mark them as standalone-only usage.

## Testing

**New tests in `tests/test_live_pipeline.py`:**
- Test `LivePipelineManager.start()` launches a pipeline task (mock the `TRMRouter` the same way `test_runs.py` does with `_make_mock_router()`).
- Test `LivePipelineManager.stop()` cancels the task.
- Test `LivePipelineManager.status()` returns correct state.
- Test WebSocket at `/ws/live/mock` receives `pipeline_started`, `packet_captured`, `packet_preprocessed`, `packet_routed`, `pipeline_complete` messages in order.
- Test late-joining WebSocket client receives backlog.
- Test two concurrent WebSocket clients both receive messages.

**Update `tests/test_mock_api.py`:**
- Rewrite to test the new in-process pipeline instead of subprocess management.
- Mock `TRMRouter` to avoid LLM calls (same pattern as `test_runs.py`).
- Test `/api/mock/start`, `/stop`, `/status` with the new `LivePipelineManager`.

**Existing tests that should still pass unchanged:**
- `test_live_api.py` — REST hydration endpoints are unchanged.
- `test_runs.py` — scenario WebSocket is untouched.
- `test_trm_persistence.py` — persistence logic is unchanged.
- All other test files.

## Doc Updates

After implementation, update:
- `docs/pipeline/mock_pipeline.md` — rewrite to describe the in-process async pipeline, WebSocket messages, and the new data flow. Remove subprocess/polling descriptions.
- `docs/web/api.md` — add the `/ws/live/mock` WebSocket endpoint and its message protocol. Update the mock control endpoints description.
- `CLAUDE.md` — update Current State, Running, and Architecture sections (covered in Step 10).
