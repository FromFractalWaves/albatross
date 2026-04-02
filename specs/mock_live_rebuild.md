# Spec: Mock Live Pipeline UI Rebuild

**Status:** Draft  
**Scope:** Rebuild `/sources`, `/live/[source]`, and mock pipeline API controls end-to-end  
**Reference:** `docs/pipeline/mock_pipeline.md` — full end-to-end documentation of how the mock pipeline works

---

## Context

The live data side of the UI is broken or drifted following the restructure. This spec treats the following as a clean rebuild:

- `/sources` — source selection page
- `/live/[source]` — dynamic live dashboard (first implementation: `/live/mock`)
- Mock pipeline controls (Start/Stop) on the live page
- The `useLiveData` hook behavior

The following are working and should not be touched:

- Homepage (`/`) — two cards linking to `/trm` and `/sources`
- TRM side (`/trm`, `/trm/scenarios`, `/trm/scenarios/[tier]/[scenario]`, `/run/[runId]`)
- All shared components (`TopBar`, `HubTopBar`, `TabBar`, `ThreadLane`, `EventCard`, `TimelineRow`, `PacketCard`, `DecisionBadge`, etc.)
- API endpoints for live data (`GET /api/live/threads`, `/events`, `/transmissions`)
- Mock pipeline API (`POST /api/mock/start`, `/stop`, `GET /api/mock/status`)
- Database, ORM, contracts layer
- `web/src/lib/api.ts` — use `API_BASE` for all fetches
- All types in `web/src/types/`

---

## Full User Flow

```
Homepage (/)
  └── "Live Data" card → /sources
        └── "Mock Pipeline" card → /live/mock
              └── Start button → pipeline runs → data appears in dashboard
              └── Stop button → pipeline stops
```

---

## Route: `/sources`

**File:** `web/src/app/sources/page.tsx`

### Behavior

- Static page, no data fetching
- Uses `HubTopBar`
- Back link to `/`
- Page title: "Live Data Sources"

### Layout

One source card (same card pattern as TRM hub and homepage):

**Mock Pipeline card:**
- Label: "Mock Pipeline"
- Description: "Replays a scenario with full radio metadata through the full pipeline — capture, preprocessing, TRM routing — and streams results into the live dashboard."
- Status badge: "Available" (static, green)
- Links to `/live/mock`

**Future source cards (not in scope):**
- Real Radio (RTL-SDR)
- Recorded Capture Replay

### Design notes

- Consistent card style with `/trm` hub and homepage
- Selecting a source only navigates — no pipeline starts here

---

## Route: `/live/[source]`

**File:** `web/src/app/live/[source]/page.tsx`

### Behavior

- Read `source` from route params
- On load: page renders in idle/empty state — no pipeline auto-starts, no data fetched yet
- User hits Start → pipeline starts → polling begins → data flows into dashboard
- User hits Stop → pipeline stops → polling continues showing last known state

### Layout

Top: `TopBar` with title reflecting source (e.g. "Live — Mock Pipeline" when `source === "mock"`)

Below TopBar: **Pipeline Controls bar** (shown only when `source === "mock"`):
- Status indicator: gray dot (stopped) / green pulsing dot (running)
- "Start" button — disabled while running
- "Stop" button — disabled while stopped
- Status text: "Pipeline stopped" / "Pipeline running"

Below controls: **TabBar** with three tabs: LIVE, EVENTS, TIMELINE

Tab content:

**LIVE tab:**
- If no data: "No data yet. Start the pipeline to begin." centered in the tab area
- If data: one `ThreadLane` per active thread, using `threadColorMap` for colors

**EVENTS tab:**
- If no data: "No events yet."
- If data: one `EventCard` per active event

**TIMELINE tab:**
- If no data: "No transmissions yet."
- If data: one `TimelineRow` per routed transmission, sorted by timestamp

### State

- `pipelineStatus`: `"running" | "stopped"` — polled from `GET /api/mock/status` every 3s when `source === "mock"`
- Live data: managed by `useLiveData` hook (see below)
- `threadColorMap`: computed from `context.active_threads` via `getThreadColorMap()`
- `decisionMap`: computed from `routingRecords` via `buildDecisionMap()`
- `latestPacketId`: from hook

### Mock pipeline controls behavior

- On mount: fetch `GET /api/mock/status` to initialize `pipelineStatus`
- Poll `GET /api/mock/status` every 3s regardless of state
- Start button:
  - Calls `POST /api/mock/start`
  - On success: set `pipelineStatus = "running"`
  - On error: show inline error message
- Stop button:
  - Calls `POST /api/mock/stop`
  - On success: set `pipelineStatus = "stopped"`
  - On error: show inline error message

**Important:** `useLiveData` polls independently of pipeline status. It always polls — when the pipeline is stopped it will just keep returning the last known state from the DB (or empty if DB was reset).

---

## Hook: `useLiveData`

**File:** `web/src/hooks/useLiveData.ts`

### Behavior

- Polls all three live endpoints in parallel every 3s via `Promise.all()`
- Endpoints: `GET /api/live/threads`, `GET /api/live/events`, `GET /api/live/transmissions`
- Use `API_BASE` from `web/src/lib/api.ts` for all fetch URLs
- On error: silently ignore, retry next poll (do not crash or show error)
- On unmount: stop polling (use `activeRef` pattern)

### Return shape

```typescript
{
  context: TRMContext | null,        // reconstructed from threads + events
  routingRecords: RoutingRecord[],   // built from transmissions with thread_decision set
  latestPacketId: string | null,     // id of last transmission by timestamp
  status: "loading" | "empty" | "ready" | "error"
}
```

### Context reconstruction

Build `TRMContext` from API responses:

```typescript
{
  active_threads: threads,       // from /api/live/threads
  active_events: events,         // from /api/live/events
  packets_to_resolve: [],        // always empty
  buffers_remaining: 5,          // hardcoded for now
  incoming_packet: null
}
```

### Status logic

- `"loading"` — first fetch not yet complete
- `"empty"` — fetch succeeded but all arrays are empty
- `"ready"` — fetch succeeded and at least one thread or transmission exists
- `"error"` — fetch failed (revert to last known good state, retry next poll)

### RoutingRecord construction

Build from transmissions that have `thread_decision` set. See `specs/mock_live_fix_info.md` section 8 for transmission response shape and `web/src/types/trm.ts` for `RoutingRecord` type.

---

## What This Spec Does NOT Include

- No changes to the API endpoints or mock pipeline scripts
- No changes to shared components
- No changes to the TRM side of the UI
- No Connect button — mock pipeline has no connection step, Start/Stop is sufficient
- No WebSocket integration — polling is correct for the live page (DB-backed, not stream-backed)
- No new TypeScript types — reuse existing types from `web/src/types/`
- No changes to `web/src/lib/api.ts`, `threadColors.ts`, or `packetDecisions.ts`