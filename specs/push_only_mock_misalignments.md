# Misalignments: Push-Only Mock Pipeline

_Spec: `specs/push_only_mock.md` — reviewed against repo on 2026-04-02_

## TanStack Query

- **Spec says:** TanStack Query is "the right tool here" for managing cache + WebSocket updates
- **Repo reality:** TanStack Query is not installed. `web/package.json` has no `@tanstack/react-query` dependency. The frontend currently uses native `fetch` + `useReducer` with no query/cache library.
- **Resolution:** Build plan includes installing `@tanstack/react-query` and `@tanstack/react-query-devtools`. The hook will use `useQuery` for initial REST hydration and manual `queryClient.setQueryData` for WebSocket-driven cache updates.

## Mock Pipeline Control API

- **Spec says:** Pipeline starts from the UI via the existing start button (`POST /api/mock/start`). No auto-start.
- **Repo reality:** `api/routes/mock.py` currently launches three subprocess scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) via `asyncio.create_subprocess_exec()` and stores handles in `app.state.mock_processes`. The start endpoint also calls `reset_db()`.
- **Resolution:** The mock control API keeps the same endpoints but replaces subprocess management with `LivePipelineManager`. `POST /api/mock/start` launches the in-process pipeline. `POST /api/mock/stop` cancels it. `GET /api/mock/status` checks manager state. The subprocess-based approach is fully replaced.

## WebSocket Endpoint Naming

- **Spec says:** No explicit endpoint path for the live WebSocket
- **Repo reality:** Scenario runs use `/ws/runs/{run_id}`. There is no live WebSocket endpoint.
- **Resolution:** Build plan adds `/ws/live/{source}` (e.g., `/ws/live/mock`) to parallel the existing `/ws/runs/{run_id}` pattern. The `{source}` parameter aligns with the existing `/live/{source}` page route.

## Message Types

- **Spec says:** Five message types: `pipeline_started`, `packet_captured`, `packet_preprocessed`, `packet_routed`, `pipeline_complete`
- **Repo reality:** Scenario runs use four types: `run_started`, `packet_routed`, `run_complete`, `run_error`. The `packet_routed` message carries full `context`, `routing_record`, and `incoming_packet`.
- **Resolution:** The live pipeline uses its own message types as specified. `packet_routed` reuses the same shape as the scenario `packet_routed` (with `context`, `routing_record`, `incoming_packet`). The earlier stage messages (`packet_captured`, `packet_preprocessed`) carry lighter payloads since they don't have routing results yet.

## Capture Timing

- **Spec says:** Mock capture sleeps 10s between packets
- **Repo reality:** `capture/mock/run.py` sleeps 10s between packets. `preprocessing/mock/run.py` then adds another 10s simulated ASR delay per packet. End-to-end latency is ~20s per packet.
- **Resolution:** The in-process pipeline preserves both delays (10s capture interval + 10s preprocessing delay) to match current behavior. These are configurable but default to the existing timing.
