# Spec: Scenarios Browser Rebuild

**Status:** Draft  
**Scope:** Rebuild `/trm/scenarios` and `/trm/scenarios/[tier]/[scenario]` from scratch in the context of the current UI structure  
**Reference:** `specs/scenarios_fix_info.md` — full end-to-end documentation of how scenarios works

---

## Context

The scenarios browser and detail pages are broken following the UI restructure. Rather than debugging the current state, this spec treats both pages as a clean rebuild. The existing files at these routes should be deleted and replaced.

The rest of the UI is intact:
- Homepage (`/`) — working
- TRM Hub (`/trm`) — working, has a card linking to `/trm/scenarios`
- Run page (`/run/[runId]`) — working, WebSocket dashboard
- All shared components (`TopBar`, `HubTopBar`, `TabBar`, `ThreadLane`, etc.) — working
- API endpoints (`GET /api/scenarios`, `GET /api/scenarios/{tier}/{scenario}`, `POST /api/runs`) — working
- `web/src/lib/api.ts` — `API_BASE` already defined, use it for all fetches

---

## Route: `/trm/scenarios`

**File:** `web/src/app/trm/scenarios/page.tsx`

### Behavior

- Fetch `GET /api/scenarios` on mount
- Display loading state while fetching
- Display error state if fetch fails (show message, do not crash)
- On success, render the tier/scenario list

### Data Shape

The API returns an array of tier groups. See `specs/scenarios_fix_info.md` section 2 for the full response schema.

```
[
  {
    tier: string,
    scenarios: [{ name: string, path: string }]
  }
]
```

### Layout

- Uses `HubTopBar` at the top (consistent with other hub pages)
- Page title: "Scenarios"
- For each tier group:
  - Section header showing the tier name formatted as human-readable (e.g. `tier_one` → "Tier One") and scenario count
  - List of scenario rows, each linking to `/trm/scenarios/{tier}/{scenario.name}`
- Each scenario row shows:
  - Scenario name (formatted — replace underscores with spaces, strip leading `scenario_NN_`)
  - Full raw name as a secondary label or subtitle
  - Arrow or chevron indicating it is clickable
- Back link to `/trm`

### Empty / Error States

- Loading: simple spinner or "Loading scenarios..." text
- Error: "Failed to load scenarios. Is the API running?" — do not throw, render inline
- Empty: "No scenarios found." if the API returns an empty array

---

## Route: `/trm/scenarios/[tier]/[scenario]`

**File:** `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`

### Behavior

- Read `tier` and `scenario` from route params
- Fetch `GET /api/scenarios/{tier}/{scenario}` on mount
- Display loading state while fetching
- Display error state if fetch fails or returns 404
- On success, render the scenario detail view

### Data Shape

See `specs/scenarios_fix_info.md` section 2 for the full response schema. Key fields:

- `name` — scenario name string
- `tier` — tier string
- `readme` — markdown string or null
- `packets` — array of packet objects
- `expected_output` — object or null

### Layout

Top section:
- Back link to `/trm/scenarios`
- Scenario name as page heading
- Tier badge

**README section** (if `readme` is not null):
- Section header: "README"
- Preformatted text block

**Packets section:**
- Section header: "PACKETS" with packet count
- List of packets, each showing:
  - Packet ID
  - Speaker from `metadata.speaker` (if present)
  - Timestamp
  - Text (truncated to 120 characters)

**Expected Output section** (if `expected_output` is not null):
- Section header: "EXPECTED OUTPUT"
- Collapsible JSON view, max-height scrollable
- Collapsed by default

**Run Configuration section:**
- Section header: "RUN CONFIGURATION"
- Speed factor input — number, default 20, min 1
- Buffer count input — number, default 5, min 1, max 10

**Run button:**
- Label: "Run This Scenario"
- Shows "Starting..." while POST is in flight
- On click: POST to `/api/runs` with `{ source: "scenario", tier, scenario, speed_factor, buffer_count }`
- On success: navigate to `/run/{run_id}`
- On error: show inline error message, re-enable button

---

## What This Spec Does NOT Include

- No changes to the API
- No changes to shared components
- No changes to the run page (`/run/[runId]`)
- No changes to the TRM hub (`/trm`)
- No new types — reuse existing types from `web/src/types/scenarios.ts` and `web/src/types/trm.ts`
- No styling system changes — follow existing design tokens from `globals.css`