# Build Plan: Web UI Restructure (Attempt 2)

_Generated from spec — aligned with repo on 2026-04-01_

## Goal

Complete the remaining UI restructure: add `/sources` and `/trm` hub pages, convert `/live` to dynamic `/live/[source]`, move scenario browser from `/trm` to `/trm/scenarios`, and update homepage links and card copy.

## Context

Most of the restructure was completed in attempt 1. The following already works:
- Homepage hub (`web/src/app/page.tsx`) — two-card layout
- Scenario browser (`web/src/app/trm/page.tsx`) — fetches and lists scenarios by tier
- Scenario detail (`web/src/app/scenarios/[tier]/[scenario]/page.tsx`) — README, packets, run config
- Live dashboard (`web/src/app/live/page.tsx`) — mock pipeline controls, thread lanes, events, timeline
- Theme system (`web/src/hooks/useTheme.ts`, `web/src/components/ThemeToggle.tsx`)
- Mock pipeline API (`api/routes/mock.py`) — start, stop, status endpoints
- All dashboard components (TopBar, HubTopBar, TabBar, ThreadLane, etc.)
- Header reads "Albatross", buffer counter hidden on live page

What remains is restructuring `/trm` into a hub + sub-route, adding `/sources`, and making `/live` dynamic.

## Plan

### Step 1: Move scenario browser from `/trm` to `/trm/scenarios`

**Files:** `web/src/app/trm/scenarios/page.tsx` (new), `web/src/app/trm/page.tsx` (will be replaced in Step 2)

Move the contents of `web/src/app/trm/page.tsx` into `web/src/app/trm/scenarios/page.tsx`. This is a straight move — the scenario browser logic (fetching `/api/scenarios`, listing tiers, linking to detail pages) stays identical. Update the scenario links to point to `/trm/scenarios/{tier}/{scenario}` instead of `/scenarios/{tier}/{scenario}`.

### Step 2: Move scenario detail pages under `/trm/scenarios`

**Files:** `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx` (new), `web/src/app/scenarios/[tier]/[scenario]/page.tsx` (delete)

Move the scenario detail page from `web/src/app/scenarios/[tier]/[scenario]/page.tsx` to `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`. Update the back-link from `/trm` to `/trm/scenarios`. Everything else stays the same.

Delete the now-empty `web/src/app/scenarios/` directory.

### Step 3: Convert `/trm` into a TRM Tools hub

**Files:** `web/src/app/trm/page.tsx` (rewrite)

Replace the current scenario browser with a hub page. Same structure as the homepage — uses `HubTopBar`, displays tool cards. One card for now:

- **Card: Scenarios**
  - Label: "Scenarios"
  - Description: "Run scenarios, visualize thread decisions, view scoring"
  - Links to `/trm/scenarios`
  - Use accent-blue color theming (consistent with TRM Tools card on homepage)

Layout mirrors the homepage card style (`bg-surface`, `rounded-lg`, `border-border`). Since there's only one card initially, use a single-column centered layout (not a grid) — or match the homepage grid so it looks natural when more tools are added later.

### Step 4: Create `/sources` page

**Files:** `web/src/app/sources/page.tsx` (new)

Source selection page. Uses `HubTopBar`. Displays one card:

- **Card: Mock Pipeline**
  - Label: "Mock Pipeline"
  - Description: "Replays a scenario with full radio metadata, simulating live capture"
  - Status indicator: "available" (static text — no API call needed)
  - Links to `/live/mock`

Use accent-green color theming (consistent with Live Data card on homepage). Same card layout pattern as the `/trm` hub from Step 3.

### Step 5: Convert `/live` to `/live/[source]`

**Files:** `web/src/app/live/[source]/page.tsx` (new), `web/src/app/live/page.tsx` (delete)

Move `web/src/app/live/page.tsx` to `web/src/app/live/[source]/page.tsx`. Changes:

1. Accept `params` prop to read the `source` route parameter
2. Use the source param in TopBar's `scenarioName` — e.g. "Live — Mock Pipeline" when source is `"mock"`
3. Guard mock pipeline controls with `if (source === "mock")` so future sources won't show irrelevant start/stop buttons
4. All existing functionality stays: `useLiveData`, `TabBar`, `ThreadLane`, `EventCard`, `TimelineRow`, `ContextInspector`

No changes to `useLiveData` hook or API endpoints — the data path is the same regardless of source routing.

### Step 6: Update homepage card copy and links

**Files:** `web/src/app/page.tsx`

Three changes:

1. **Live Data card link:** `href="/live"` → `href="/sources"`
2. **TRM Tools description:** "Scenario runner, scoring, prompt tuning, golden dataset management, domain adaptation. Everything needed to evaluate and improve the TRM."
3. **Live Data description:** "Real-time pipeline visualization. Thread lanes, event stream, packet timeline. Connects to live or mock radio data source."
4. **Live Data link text:** "Open Pipeline →" → "Select Source →"

## Testing

No new automated tests needed — these are static UI pages with no new API endpoints or backend changes. Existing mock pipeline API tests in `tests/` remain valid.

Manual verification:
- `/` → "TRM Tools" card → `/trm` (hub) → "Scenarios" card → `/trm/scenarios` (browser) → click scenario → `/trm/scenarios/{tier}/{scenario}` (detail)
- `/` → "Live Data" card → `/sources` → "Mock Pipeline" card → `/live/mock` (dashboard with controls)
- Start/stop pipeline on `/live/mock` works as before
- Theme toggle works on all pages
- Direct URL navigation works for all routes
- Old routes (`/scenarios/...`) no longer resolve (expected — moved)

## Doc Updates

After implementation, update `CLAUDE.md` frontend section:
- Route table: add `/sources`, change `/trm` to hub, add `/trm/scenarios`, change `/live` to `/live/[source]`
- File listing: `web/src/app/trm/page.tsx` is now a hub, add `web/src/app/trm/scenarios/page.tsx`, add `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`, add `web/src/app/sources/page.tsx`, `web/src/app/live/[source]/page.tsx` replaces `web/src/app/live/page.tsx`
- Remove `web/src/app/scenarios/[tier]/[scenario]/page.tsx` reference (moved)
