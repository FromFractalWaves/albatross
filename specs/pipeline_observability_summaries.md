# Summaries: Pipeline Observability

_Spec: `specs/pipeline_observability.md` — reviewed against repo on 2026-04-03_

## Current State

The live mock pipeline runs as a single class, `LivePipelineManager`, in `api/services/live_pipeline.py`. It has no base class. It runs three async stages (capture, preprocessing, routing) connected by `PacketQueue`s, broadcasting WebSocket messages at each stage: `pipeline_started`, `packet_captured`, `packet_preprocessed`, `packet_routed`, `pipeline_complete`. These message types are defined as Pydantic models in `contracts/ws.py` and mirrored as TypeScript interfaces in `web/src/types/websocket.ts`.

The `pipeline_started` message currently carries only `total_packets` — no stage metadata. The REST status endpoint (`GET /api/mock/status`) returns only `{"status": "running"|"stopped"}`.

On the frontend, `useLiveData.ts` connects to the WebSocket and handles messages via a switch statement. It processes `pipeline_started` (stores total), `packet_routed` (updates TanStack Query caches for threads/events/transmissions), `pipeline_complete` (invalidates queries), and `pipeline_error` (stores error). It does **not** handle `packet_captured` or `packet_preprocessed` — those messages arrive but are ignored. The hook returns `status`, `context`, `routingRecords`, `latestPacketId`, `incomingPacket`, and `error` — no stage-level data.

The live page (`web/src/app/live/[source]/page.tsx`) polls `GET /api/mock/status` every 3 seconds for pipeline status via its own `useEffect` + `setInterval`, storing the result in local state (`pipelineStatus`). It renders pipeline controls (start/stop buttons) above the tab bar. There is no pipeline stage visibility component.

## Target State

`LivePipelineManager` inherits from a new abstract base class `BasePipelineManager` in `api/services/base_pipeline.py`. The base class extracts the lifecycle methods (`start`, `stop`, `status`, `subscribe`, `unsubscribe`, `_broadcast`) and declares two abstract members: `pipeline_stages` (returns ordered stage definitions) and `_run_pipeline`. Any future pipeline inherits from this base class and only implements those two.

A new `PipelineStageDefinition` type in `contracts/ws.py` defines each stage with `id`, `label`, and `message_type`. `PipelineStarted` gains a `stages` field carrying a list of these definitions. `LivePipelineManager` declares its three stages (capture, preprocessing, routing) via the `pipeline_stages` property and includes them in the `pipeline_started` broadcast.

The REST status endpoint returns `stages` alongside `status` — always present, regardless of running state. It serves stage *definitions* only, not live counts.

On the frontend, `PipelineStartedMessage` in `websocket.ts` gains a `stages` field and a new `PipelineStageDefinition` type is added. `useLiveData` maintains stage state in a dedicated TanStack Query cache key `["live", "stages"]`. On `pipeline_started`, it resets counts to 0, stores `total_packets`, and updates the stages definition from the message. On `packet_captured`, `packet_preprocessed`, and `packet_routed`, it finds the matching stage by `message_type` and increments its count via `queryClient.setQueryData`. The hook returns a new `stages` array with `{ id, label, message_type, count, total }` per stage.

The live page seeds the `["live", "stages"]` cache from its existing status poll response (which now includes `stages`). A new `PipelineStages` component renders a compact horizontal strip of stage indicators (idle/active/done) between the top bar and pipeline controls. It receives `stages` from `useLiveData` and `pipelineStatus` from the page. Returns null when stages is empty.
