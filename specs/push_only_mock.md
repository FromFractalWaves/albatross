# Push-Only Mock Pipeline

## What This Is

Rebuild the mock live pipeline so that data flows via push (WebSocket) instead of poll (DB + REST polling). Right now the live path has three polling boundaries: mock preprocessing polls the DB for captured rows, the TRM polls for processed rows, and the frontend polls REST endpoints every 3 seconds. The scenario path already pushes everything over WebSocket via `useRunSocket`. This spec brings the live path up to the same standard.

When this is done, the live pipeline and the scenario pipeline use the same push architecture. The only difference is what feeds the first stage.

## What Currently Exists

**Backend — three separate processes, DB as IPC:**
- `capture/mock/run.py` — reads `packets_radio.json`, writes to DB with `status = 'captured'`, sleeps 10s between packets
- `preprocessing/mock/run.py` — polls DB for `captured` rows, simulates ASR delay, updates to `status = 'processed'`
- `trm/main_live.py` — polls DB for `processed` rows, routes via `TRMRouter`, persists results, exits after idle cycles

**Frontend — REST polling:**
- `useLiveData.ts` — polls `GET /api/live/threads`, `/events`, `/transmissions` every 3 seconds
- `live/page.tsx` — renders dashboard from poll results, same components as scenario run view

**Scenario path (already push):**
- `POST /api/runs` starts a run, frontend opens WebSocket to `/ws/runs/{run_id}`
- `useRunSocket.ts` receives `run_started`, `packet_routed`, `run_complete` messages
- `RunManager` in `api/services/runner.py` orchestrates the pipeline and broadcasts messages

## What Changes

### Backend

The mock pipeline stages stop polling the DB independently and instead run as a coordinated pipeline inside the API process, pushing status over a WebSocket — similar to how `RunManager` already handles scenario runs.

**Mock capture** emits packets on a timer into an async queue (not the DB). **Mock preprocessing** consumes from that queue, simulates delay, and pushes to a second queue. **The TRM** consumes from the second queue, routes, persists to DB, and broadcasts results over WebSocket.

The DB remains the source of truth for persistence and page-refresh hydration. What changes is that the *live data path* is push — the frontend doesn't poll for updates, it receives them.

The WebSocket should carry stage-level messages so the frontend knows where packets are in the pipeline:

- `packet_captured` — a packet entered the pipeline
- `packet_preprocessed` — a packet finished preprocessing
- `packet_routed` — a packet was routed by the TRM (same shape as the existing scenario message)
- `pipeline_started` / `pipeline_complete` — bookend messages

This is the foundation for the pipeline observability described in vision.md — the UI can see each stage, not just the final routing result.

### Frontend

Replace `useLiveData` polling with a WebSocket connection to the live pipeline. The hook should return the same state shape so that `live/page.tsx` needs minimal changes.

TanStack Query is the right tool here — it manages the cache of pipeline state, and WebSocket messages update the cache reactively. This replaces the manual `useReducer` + `setInterval` pattern in `useLiveData`.

The REST endpoints (`/api/live/threads`, `/events`, `/transmissions`) stay. They become the hydration layer — TanStack Query fetches them on page load, then WebSocket messages keep the cache current. A page refresh still works because TanStack re-fetches from REST on mount.

### What Stays The Same

- Scenario tooling is untouched — `useRunSocket`, `RunManager`, `POST /api/runs` all stay as-is
- DB schema is unchanged — same tables, same persistence
- All existing dashboard components (`ThreadLane`, `EventCard`, `TimelineRow`, etc.) are unchanged

### What Gets Removed

- `live.sh` is deleted. The pipeline runs inside the API process and is started from the UI via the existing start button (`POST /api/mock/start`). `dev.sh` already launches the API and frontend — that's all you need. There is no auto-start; the user clicks the button, same as they would for a real live source.

## Done When

- `dev.sh` starts the API and frontend. The pipeline is not running yet.
- User clicks the start button on `/live/mock`, which calls `POST /api/mock/start`
- Opening `/live/mock` connects a WebSocket and receives stage-level messages as packets flow
- Thread lanes, events, and timeline update in real time via push — no polling
- Page refresh hydrates from DB via REST, then WebSocket picks up live updates
- A second browser tab connects and receives the same live stream
- Existing scenario runs (`/run/{runId}`) still work exactly as before
- `live.sh` is gone