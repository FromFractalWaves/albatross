# Scenarios System — End-to-End Reference

How scenarios work from data files through the API to the Web UI.

---

## 1. Data Layer

### Folder Structure

```
data/
└── tier_one/
    ├── scenario_01_simple_two_party/
    │   ├── packets.json
    │   ├── expected_output.json
    │   └── README.md
    ├── scenario_02_interleaved/
    │   ├── packets.json
    │   ├── packets_radio.json      ← augmented for mock pipeline (Phase 3)
    │   ├── expected_output.json
    │   └── README.md
    ├── scenario_03_event_opens_mid_thread/
    │   ├── packets.json
    │   ├── expected_output.json
    │   └── README.md
    └── scenario_04_three_way_split/
        ├── packets.json
        ├── expected_output.json
        └── README.md
```

Tiers are top-level directories (`tier_one/`, future `tier_two/`, etc.). Each scenario folder must contain `packets.json`. `expected_output.json` and `README.md` are optional.

### packets.json Schema

Array of packet objects ordered by timestamp:

```json
[
  {
    "id": "pkt_001",
    "timestamp": "2024-01-15T10:00:00Z",
    "text": "Hey Marcus, build's broken again",
    "metadata": {
      "speaker": "li"
    }
  }
]
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string | yes | Unique packet ID (e.g. `pkt_001`) |
| `timestamp` | ISO 8601 string | yes | Used by loader for time-gap replay |
| `text` | string | yes | Packet content |
| `metadata` | object | no | Arbitrary; typically `{ "speaker": "name" }` |

### expected_output.json Schema

Ground truth for scoring. Three sections:

```json
{
  "threads": [
    {
      "thread_id": "thread_A",
      "label": "Build failure discussion",
      "status": "open",
      "packet_ids": ["pkt_001", "pkt_002", "pkt_003"]
    }
  ],
  "events": [
    {
      "event_id": "event_A",
      "label": "CI build failure",
      "status": "open",
      "thread_ids": ["thread_A"]
    }
  ],
  "routing": [
    {
      "packet_id": "pkt_001",
      "thread_decision": "new",
      "thread_id": "thread_A",
      "event_decision": "new",
      "event_id": "event_A"
    }
  ]
}
```

**threads[]**: Each thread lists its `packet_ids` in order. Status is `"open"` or `"closed"`.

**events[]**: Each event lists linked `thread_ids`. An event can span multiple threads.

**routing[]**: One entry per packet. `thread_decision` is `new|existing|buffer|unknown`. `event_decision` is `new|existing|none|unknown`. IDs are null when decision is `buffer`, `unknown`, or `none`.

---

## 2. API Layer

### Scenario Endpoints

**File**: `api/routes/scenarios.py`

#### `GET /api/scenarios` — List all scenarios

Response:
```json
[
  {
    "tier": "tier_one",
    "scenarios": [
      { "name": "scenario_01_simple_two_party", "path": "tier_one/scenario_01_simple_two_party" },
      { "name": "scenario_02_interleaved", "path": "tier_one/scenario_02_interleaved" }
    ]
  }
]
```

Walks the `data/` directory. Each subdirectory of a tier that contains `packets.json` is a scenario.

#### `GET /api/scenarios/{tier}/{scenario}` — Scenario detail

Response:
```json
{
  "tier": "tier_one",
  "name": "scenario_01_simple_two_party",
  "readme": "# Scenario 1\n...",
  "packets": [ /* full packets.json array */ ],
  "expected_output": { /* full expected_output.json object, or null */ }
}
```

Returns 404 if the scenario directory or `packets.json` is missing. `readme` and `expected_output` are null if their files don't exist.

### Run Endpoints

**File**: `api/routes/runs.py`

#### `POST /api/runs` — Start a run

Request:
```json
{
  "source": "scenario",
  "tier": "tier_one",
  "scenario": "scenario_01_simple_two_party",
  "speed_factor": 20.0,
  "buffer_count": 5
}
```

Response:
```json
{ "run_id": "a1b2c3d4e5f6" }
```

Creates a `Run` object and immediately spawns `_execute_run()` as an async background task. Returns the 12-char hex run ID synchronously. Returns 404 if the scenario doesn't exist.

#### `WS /ws/runs/{run_id}` — Live run stream

Connection flow:
1. Client connects
2. Server accepts; if run_id unknown, closes with code 4004
3. Server sends full message backlog (all messages sent so far)
4. Server holds connection open; client can send pings
5. Closes on disconnect or run completion

### WebSocket Message Protocol

Four message types flow over the WebSocket:

**`run_started`** — Sent once when the run begins.
```json
{
  "type": "run_started",
  "run_id": "a1b2c3d4e5f6",
  "scenario": { "tier": "tier_one", "name": "scenario_01_simple_two_party" }
}
```

**`packet_routed`** — Sent after each packet is routed by the LLM.
```json
{
  "type": "packet_routed",
  "packet_id": "pkt_001",
  "routing_record": {
    "packet_id": "pkt_001",
    "thread_decision": "new",
    "thread_id": "thread_A",
    "event_decision": "new",
    "event_id": "event_A"
  },
  "context": {
    "active_threads": [ /* Thread objects with packets */ ],
    "active_events": [ /* Event objects */ ],
    "packets_to_resolve": [],
    "buffers_remaining": 5
  },
  "incoming_packet": {
    "id": "pkt_001",
    "timestamp": "2024-01-15T10:00:00Z",
    "text": "Hey Marcus, build's broken again",
    "metadata": { "speaker": "li" }
  }
}
```

The `context` field is the full `TRMContext` snapshot *after* the routing decision was applied, with `incoming_packet` popped out and sent as a sibling field.

**`run_complete`** — Sent once when all packets are processed.
```json
{
  "type": "run_complete",
  "run_id": "a1b2c3d4e5f6",
  "total_packets": 10,
  "routing_records": [ /* full array of all RoutingRecord objects */ ]
}
```

**`run_error`** — Sent if the run fails.
```json
{
  "type": "run_error",
  "run_id": "a1b2c3d4e5f6",
  "error": "exception message"
}
```

---

## 3. Service Layer

### RunManager (`api/services/runner.py`)

Singleton stored in `app.state.run_manager`. Holds all runs in memory (no persistence).

**Run dataclass fields**: `run_id`, `status` (pending → running → complete/error), `scenario_tier`, `scenario_name`, `speed_factor`, `buffer_count`, `messages` (backlog list), `subscribers` (WebSocket list), `router` (TRMRouter reference).

**`create_run()`**: Generates run ID, creates Run with status=pending, spawns `_execute_run()` as async task.

**`_execute_run()`** — the core loop:
1. Set status = running
2. Create `PacketQueue`, `PacketLoader`, `TRMRouter`
3. Broadcast `run_started`
4. Spawn loader task (feeds packets to queue with time gaps)
5. Loop: pull packet from queue → `router.route(packet)` → broadcast `packet_routed`
6. When queue sends None sentinel: broadcast `run_complete`, set status = complete
7. On exception: broadcast `run_error`, set status = error

**`_broadcast()`**: Appends message to `run.messages`, sends JSON to all subscribers, removes dead connections.

**`subscribe()`/`unsubscribe()`**: Add/remove WebSocket from subscriber list. `subscribe` returns the Run object so the caller can send the backlog.

### TRM Pipeline

#### PacketLoader (`trm/pipeline/loader.py`)

Reads `packets.json`, calculates time deltas between consecutive packet timestamps, sleeps `delta / speed_factor` between each packet, then pushes the packet to the queue. Sends `None` sentinel when done.

At `speed_factor=20`, a 60-second real gap becomes a 3-second sleep.

#### PacketQueue (`trm/pipeline/queue.py`)

Thin wrapper around `asyncio.Queue[ReadyPacket | None]`. Supports `put`, `get`, `task_done`, `join`, `empty`.

#### TRMRouter (`trm/pipeline/router.py`)

The LLM routing engine:

1. Sets `context.incoming_packet = packet`
2. Serializes the entire `TRMContext` as JSON
3. Calls Claude Sonnet (`claude-sonnet-4-20250514`) with:
   - 84-line system prompt defining thread/event concepts and expected JSON output
   - Single user message containing the full context JSON
4. Parses the LLM's JSON response into a `RoutingRecord`
5. Calls `_apply()` to update internal state (create/update threads and events, manage buffer)
6. Returns the `RoutingRecord`

**State model** (`TRMContext`):
- `active_threads`: list of `Thread` objects (id, label, packets, event_ids, status)
- `active_events`: list of `Event` objects (id, label, opened_at, thread_ids, status)
- `packets_to_resolve`: buffered packets awaiting future resolution
- `buffers_remaining`: starts at `buffer_count`, decrements on each buffer decision
- `incoming_packet`: the packet currently being routed

---

## 4. Web UI Layer

### Navigation Flow

```
/                         Homepage (two cards: TRM Tools, Live Data)
├── /trm                  TRM Hub (card: Scenarios)
│   └── /trm/scenarios    Scenarios Browser (lists tiers + scenarios)
│       └── /trm/scenarios/[tier]/[scenario]   Scenario Detail
│           └── /run/[runId]                   Live Run Dashboard
└── /sources              Source Selection (card: Mock Pipeline)
    └── /live/[source]    Live Dashboard (DB-hydrated)
```

### Pages

#### Homepage (`web/src/app/page.tsx`)

Two-column grid with cards:
- **TRM Tools** → links to `/trm`
- **Live Data** → links to `/sources`

Uses `HubTopBar` component.

#### TRM Hub (`web/src/app/trm/page.tsx`)

Single card linking to `/trm/scenarios` with label "Scenarios — Run scenarios, visualize thread decisions, view scoring."

#### Scenarios Browser (`web/src/app/trm/scenarios/page.tsx`)

- Back link to `/trm`
- Page title: "Scenarios"
- Fetches `GET /api/scenarios` on mount
- Displays tiers as sections with title-case headers (e.g. "Tier One") and scenario counts
- Each scenario is a clickable row showing:
  - Formatted name as primary label (prefix stripped, title-cased)
  - Raw scenario name as secondary subtitle
  - Chevron indicating clickability
- Links to `/trm/scenarios/{tier}/{scenario}`
- States: loading ("Loading scenarios..."), error ("Failed to load scenarios. Is the API running?"), empty ("No scenarios found.")

#### Scenario Detail (`web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`)

- Fetches `GET /api/scenarios/{tier}/{scenario}` on mount
- Displays:
  - Back link to `/trm/scenarios`
  - Scenario name (h1) + tier badge (purple)
  - **README** section — preformatted markdown text
  - **PACKETS** section — list with packet ID, speaker (cyan), timestamp, text (truncated to 120 chars)
  - **EXPECTED OUTPUT** section — collapsible JSON view (max-height 400px, scrollable)
  - **RUN CONFIGURATION** — speed factor input (default 20, min 1) + buffer count input (default 5, min 1, max 10)
  - **Run button** — "Run This Scenario" (shows "Starting..." while in flight)
- On run: POST `/api/runs` → receives `run_id` → navigates to `/run/{runId}`

#### Run Page (`web/src/app/run/[runId]/page.tsx`)

The live dashboard. Uses `useRunSocket` hook for WebSocket state.

**TopBar** (sticky): Albatross logo | scenario name | status badge | packets routed count | buffers remaining | speed factor | theme toggle.

**Status badges**: idle (gray), connecting (purple), running (green), complete (blue), error (red).

**IncomingBanner**: Shown when a packet is being routed. Purple-cyan gradient, pulsing dot, "awaiting LLM" label.

**BufferZone**: Shown when `packets_to_resolve` is non-empty. Amber gradient, lists buffered packets.

**Three tabs**:

| Tab | Content |
|-----|---------|
| **LIVE** | `ThreadLane` for each active thread. Each lane shows: colored dot, thread ID, status badge, packet count, label, then `PacketCard` for each packet in the thread. |
| **EVENTS** | `EventCard` for each active event. Shows: event ID, status, opened_at, label, linked thread IDs as colored badges. |
| **TIMELINE** | `TimelineRow` for every packet across all threads, sorted by packet ID. Shows: packet ID, colored dot, speaker, time, text, decision badges. |

**ContextInspector** (always visible below tabs): Expandable JSON view of the full `TRMContext` + `incoming_packet`.

### Key Hook: `useRunSocket` (`web/src/hooks/useRunSocket.ts`)

Manages WebSocket connection and state via `useReducer`.

**State shape**:
```typescript
{
  status: "idle" | "connecting" | "running" | "complete" | "error",
  context: TRMContext | null,
  routingRecords: RoutingRecord[],
  latestPacketId: string | null,
  incomingPacket: ReadyPacket | null,
  error: string | null,
  scenario: { tier: string; name: string } | null
}
```

**Reducer actions**:
- `connect` → status=connecting, reset state
- `run_started` → status=running, set scenario
- `packet_routed` → append routing record, update context, set incoming packet and latest packet ID
- `run_complete` → status=complete, set all records, clear incoming/latest
- `run_error` → status=error, set error message
- `ws_error` → status=error, generic message

Connects to `ws://localhost:8000/ws/runs/{runId}` (WS_BASE derived from API_BASE). Cleans up on unmount.

### Key Components

| Component | Props | Purpose |
|-----------|-------|---------|
| `ThreadLane` | thread, color, latestPacketId, decisionMap | Card showing one thread's packets |
| `EventCard` | event, threadColorMap | Card showing one event with linked threads |
| `TimelineRow` | packet, threadColor, threadId, decisions, isLatest | Single row in chronological packet list |
| `PacketCard` | packet, threadColor, isLatest, decisions | Single packet within a ThreadLane |
| `IncomingBanner` | packet | Banner for packet currently being routed by LLM |
| `BufferZone` | packets | Banner listing buffered/deferred packets |
| `DecisionBadge` | decision, type ("thr"/"evt") | Colored badge showing routing decision |
| `TopBar` | scenarioName, status, packetsRouted, totalPackets, buffersRemaining, speedFactor | Sticky status bar |
| `TabBar` | tabs, activeTab, onTabChange | Tab switcher (LIVE/EVENTS/TIMELINE) |
| `ContextInspector` | context, incomingPacket | Expandable raw JSON view of TRMContext |
| `Badge` | children, color, variant | Generic styled badge |
| `SectionHeader` | title, count, action | Section header with optional count and action |
| `HubTopBar` | (none) | Simple top bar for hub pages |

### Utility Modules

- **`web/src/lib/api.ts`** — `API_BASE` (env or `http://localhost:8000`), `WS_BASE` (http→ws conversion)
- **`web/src/lib/threadColors.ts`** — Rotating color palette, `getThreadColorMap(threads)` returns `Map<threadId, color>`
- **`web/src/lib/packetDecisions.ts`** — `buildDecisionMap(records)` returns `Map<packetId, { threadDecision, eventDecision, threadId, eventId }>`

### TypeScript Types

**`web/src/types/trm.ts`**: `ReadyPacket`, `Thread`, `Event`, `RoutingRecord`, `TRMContext`, `ThreadDecision`, `EventDecision`

**`web/src/types/websocket.ts`**: `RunStartedMessage`, `PacketRoutedMessage`, `RunCompleteMessage`, `RunErrorMessage`, `WSMessage` (discriminated union)

**`web/src/types/scenarios.ts`**: `TierGroup`, `ScenarioSummary`, `ScenarioDetail`, `ScenarioPacket`, `ExpectedOutput`

---

## 5. End-to-End Flow

### User Journey

1. **Homepage** (`/`) → Click "TRM Tools" card
2. **TRM Hub** (`/trm`) → Click "Browse Scenarios" on Scenarios card
3. **Scenarios Browser** (`/trm/scenarios`) → Fetches tier/scenario list from API → Click a scenario
4. **Scenario Detail** (`/trm/scenarios/tier_one/scenario_01_simple_two_party`) → Read the README, review packets, check expected output → Set speed factor and buffer count → Click "Run This Scenario"
5. **Run starts** → Frontend POSTs to `/api/runs` → API creates `Run`, spawns async `_execute_run()` → Returns `run_id` → Frontend navigates to `/run/{runId}`
6. **Run page** (`/run/{runId}`) → `useRunSocket` opens WebSocket → Receives backlog (if connecting mid-run) → Receives `run_started`
7. **Packet-by-packet** → PacketLoader feeds packets (with time-gap replay) → TRMRouter calls Claude Sonnet for each packet → RunManager broadcasts `packet_routed` → Frontend updates thread lanes, timeline, events, buffer zone, incoming banner in real time
8. **Run completes** → `run_complete` message → Status turns blue → Final routing records array available → Total packet count shown in TopBar

### Data Flow Diagram

```
data/tier_one/scenario_01/packets.json
        │
        ▼
   PacketLoader ──(time-gap sleep)──▶ PacketQueue
                                          │
                                          ▼
                                     TRMRouter
                                      │     │
                          Claude API ◀┘     └▶ _apply() updates TRMContext
                                                    │
                                                    ▼
                                              RunManager._broadcast()
                                                    │
                                                    ▼
                                         WebSocket → Frontend
                                              │
                                    ┌─────────┼──────────┐
                                    ▼         ▼          ▼
                              ThreadLanes  EventCards  Timeline
```

### Key Invariants

- **Full context per LLM call**: Every `route()` call sends the entire `TRMContext` (all threads, events, buffer, incoming packet) to Claude. The LLM is stateful across the session via this growing context.
- **Backlog delivery**: Clients connecting to a WebSocket mid-run receive all prior messages in order, so they reconstruct the full state.
- **No DB involvement**: Scenario runs are entirely in-memory. The database path (`trm/main_live.py`, `/live` page) is separate.
- **Speed factor**: Controls replay timing only, not LLM behavior. At `speed_factor=20`, a 60s real gap → 3s sleep.
- **Buffer capacity**: `buffer_count` (default 5) limits how many packets the LLM can defer. Each `buffer` decision decrements `buffers_remaining`. When exhausted, the LLM must decide or fall back to `unknown`.
