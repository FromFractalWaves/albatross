# Misalignments: Push-Only Mock Pipeline

_Spec: `specs/push_only_mock.md` — reviewed against repo on 2026-04-02_

## TanStack Query

- **Spec says:** "TanStack Query is the right tool here — it manages the cache of pipeline state, and WebSocket messages update the cache reactively."
- **Repo reality:** TanStack Query is not installed. The frontend uses raw `useReducer` + `fetch` in both `useLiveData.ts` and `useRunSocket.ts`. There is no query caching layer.
- **Resolution:** TanStack Query (`@tanstack/react-query`) must be added as a dependency. A `QueryClientProvider` must wrap the app. The build plan includes the installation and provider setup as an explicit step before the hook rewrite.

## Hook Return Shape

- **Spec says:** "The hook should return the same state shape so that `live/page.tsx` needs minimal changes."
- **Repo reality:** `useLiveData` returns `{ status, context, routingRecords, latestPacketId, error }` with status values `"loading" | "ready" | "empty" | "error"`. `useRunSocket` returns a superset: adds `incomingPacket` and `scenario`, and uses different status values `"idle" | "connecting" | "running" | "complete" | "error"`. The live page doesn't use `incomingPacket` at all.
- **Resolution:** The new hook should return the same fields as the current `useLiveData` plus `incomingPacket` (now available from WebSocket messages). The status enum should expand to include `"connecting"` and `"running"` in addition to the existing values. The live page already ignores `incomingPacket`, so the shape expansion is backwards-compatible. The build plan adds `incomingPacket` to the live page for stage-level visibility (per the spec's observability goal).

## WebSocket Message Types

- **Spec says:** Messages should be `packet_captured`, `packet_preprocessed`, `packet_routed`, `pipeline_started`, `pipeline_complete`.
- **Repo reality:** The existing scenario WebSocket uses `run_started`, `packet_routed`, `run_complete`, `run_error`. The `packet_routed` message includes full `context`, `routing_record`, and `incoming_packet`. There are no stage-level messages for capture or preprocessing.
- **Resolution:** The new live WebSocket introduces the stage-level message types from the spec (`packet_captured`, `packet_preprocessed`, `pipeline_started`, `pipeline_complete`) while keeping `packet_routed` compatible with the existing shape. These are new types in a new discriminated union — the scenario WebSocket types are untouched.

## Mock API Behavior

- **Spec says:** `POST /api/mock/start` starts the pipeline. `live.sh` is deleted.
- **Repo reality:** `POST /api/mock/start` currently resets the DB and spawns three subprocesses (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`). `POST /api/mock/stop` terminates those processes. `GET /api/mock/status` checks `app.state.mock_processes` for liveness.
- **Resolution:** The mock routes are rewritten. `/start` launches an in-process async pipeline (no subprocesses). `/stop` cancels the async task. `/status` checks the task state. The subprocess-based scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) are preserved as standalone tools but are no longer called by the API. `live.sh` is deleted.

## WebSocket Endpoint Path

- **Spec says:** "Opening `/live/mock` connects a WebSocket" — implies a new WebSocket endpoint but doesn't name it.
- **Repo reality:** The only WebSocket endpoint is `/ws/runs/{run_id}` in `api/routes/runs.py`.
- **Resolution:** A new WebSocket endpoint `/ws/live/mock` is added in `api/routes/mock.py`. This is separate from the scenario WebSocket. The build plan specifies the exact path.
