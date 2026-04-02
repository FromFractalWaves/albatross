# Build Plan: Web UI Restructure (Attempt 2)

_Generated from spec — aligned with repo on 2026-04-01_

## Goal

Complete the remaining UI restructure work: add the `/sources` source selection page, convert `/live` to a dynamic `/live/[source]` route, and update homepage links and card copy to match spec.

## Context

Most of the restructure was completed in attempt 1:
- Homepage hub (`web/src/app/page.tsx`) — two-card layout, working
- `/trm` route (`web/src/app/trm/page.tsx`) — scenario browser, working
- `/live` page (`web/src/app/live/page.tsx`) — live dashboard with mock pipeline controls, working
- Theme system (`web/src/hooks/useTheme.ts`, `web/src/components/ThemeToggle.tsx`) — working
- Mock pipeline API (`api/routes/mock.py`) — `start`, `stop`, `status` endpoints, working
- All components (`TopBar`, `HubTopBar`, `TabBar`, etc.) — working
- Header already reads "Albatross", buffer counter already hidden on live page

What remains is the `/sources` intermediate page and dynamic `/live/[source]` routing.

## Plan

### Step 1: Create `/sources` page

**Files:** `web/src/app/sources/page.tsx` (new)

Create the source selection page at `/sources`. Uses `HubTopBar` (same as homepage and `/trm`). Displays a single card for the mock pipeline source:

- **Card: Mock Pipeline**
  - Label: "Mock Pipeline"
  - Description: "Replays a scenario with full radio metadata, simulating live capture"
  - Status indicator: show "available" (static for now — no API call needed since mock is always available)
  - Links to `/live/mock`

Layout should match the homepage card style (same `bg-surface`, `rounded-lg`, `border-border` pattern used in `web/src/app/page.tsx`). Use accent-green color theming consistent with the "Live Data" card on the homepage.

### Step 2: Convert `/live` to `/live/[source]`

**Files:** `web/src/app/live/page.tsx` (delete), `web/src/app/live/[source]/page.tsx` (new, moved from `live/page.tsx`)

Move the current `live/page.tsx` to `live/[source]/page.tsx`. Changes:

1. Accept `params` prop to read the `source` route parameter
2. Use the `source` param in the TopBar's `scenarioName` (e.g. "Live — Mock Pipeline" when source is "mock")
3. The mock pipeline controls (start/stop/status) are currently hardcoded — this is fine for now since mock is the only source. Guard them with `if (source === "mock")` so future sources don't show irrelevant controls
4. All existing functionality (useLiveData, TabBar, ThreadLane, EventCard, TimelineRow, ContextInspector) stays exactly the same

No changes to `useLiveData` hook or API endpoints — the data path is the same regardless of source routing.

### Step 3: Update homepage card copy and link

**Files:** `web/src/app/page.tsx`

Two changes:

1. **Live Data card link:** Change `href="/live"` to `href="/sources"`
2. **Card descriptions:** Update to match spec:
   - TRM Tools description: "Scenario runner, scoring, prompt tuning, golden dataset management, domain adaptation. Everything needed to evaluate and improve the TRM."
   - Live Data description: "Real-time pipeline visualization. Thread lanes, event stream, packet timeline. Connects to live or mock radio data source."
   - Live Data link text: "Select Source →" (was "Open Pipeline →")

## Testing

No new automated tests needed — these are static UI pages with no new API endpoints. The existing mock pipeline API tests in `tests/` cover the backend.

Manual verification:
- Navigate `/` → click "Live Data" → lands on `/sources`
- Navigate `/sources` → click "Mock Pipeline" → lands on `/live/mock`
- `/live/mock` renders the full live dashboard with pipeline controls
- `/live/mock` start/stop pipeline works as before
- Theme toggle works on all new/modified pages
- Direct navigation to `/live/mock` works (no need to go through `/sources`)

## Doc Updates

After implementation, update `CLAUDE.md` frontend section:
- Route table: add `/sources` and change `/live` to `/live/[source]`
- `web/src/app/sources/page.tsx` entry
- `web/src/app/live/[source]/page.tsx` replaces `web/src/app/live/page.tsx`
