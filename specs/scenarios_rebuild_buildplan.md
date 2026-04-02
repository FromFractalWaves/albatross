# Build Plan: Scenarios Browser Rebuild

_Generated from `specs/scenarios_rebuild.md` — aligned with repo on 2026-04-01_

## Goal

Rewrite the scenarios browser and detail pages to match the post-restructure UI design: cleaner layout, proper name formatting, no tabs, consistent navigation.

## Context

Both page files exist and build successfully but have design/behavior drift. All dependencies are in place:

- **Types:** `web/src/types/scenarios.ts` — `TierGroup`, `ScenarioSummary`, `ScenarioDetail`, `ScenarioPacket`, `ExpectedOutput` — all correct, no changes needed
- **Components:** `HubTopBar`, `Badge`, `SectionHeader` — all working, signatures match spec needs
- **API:** `api/routes/scenarios.py` — `GET /api/scenarios` and `GET /api/scenarios/{tier}/{scenario}` — working, response shapes match the types
- **Lib:** `web/src/lib/api.ts` — `API_BASE` constant, used for all fetches
- **Reference pages:** `web/src/app/trm/page.tsx` (TRM hub), `web/src/app/page.tsx` (homepage) — working examples of hub-style layouts with `HubTopBar`

## Plan

### Step 1: Rewrite the scenarios browser page

**File:** `web/src/app/trm/scenarios/page.tsx`

Replace the entire file contents. Changes from current version:

1. **Remove** `TabBar` import and all tab state/rendering. Remove the `HubTab` type and `tabs` constant.
2. **Add** a page title heading "Scenarios" below `HubTopBar`.
3. **Add** a back link to `/trm` (same style as detail page's back link: `text-[11px] font-mono uppercase tracking-[0.06em] text-text-muted`).
4. **Change** `formatTier()` from `toUpperCase()` to title case: split on `_`, capitalize first letter of each word, join with space. `tier_one` → "Tier One".
5. **Add** `formatScenarioName(name: string)` helper: strip leading `scenario_NN_` prefix via regex (`/^scenario_\d+_/`), then replace remaining underscores with spaces, title-case the result.
6. **Update** scenario rows to show:
   - Formatted name as primary text (use `formatScenarioName`)
   - Raw `scenario.name` as secondary label below (`text-[11px] text-text-muted font-mono`)
   - Keep the `›` chevron on the right
7. **Add** empty state: if `tiers` is empty after loading, show "No scenarios found." in `text-text-muted text-sm`.
8. **Change** error message to: "Failed to load scenarios. Is the API running?"
9. Keep existing fetch logic, loading state, and `Link` routing — those are correct.

### Step 2: Rewrite the scenario detail page

**File:** `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`

Replace the entire file contents. The current version is close to spec but needs cleanup for consistency:

1. **Keep** the `use(params)` pattern for async route params (Next.js 16 / React 19 pattern).
2. **Keep** all sections: back link, title + tier badge, README, packets, expected output, run configuration, run button. These all match the spec.
3. **Verify** section headers use uppercase labels per spec: "README", "PACKETS", "EXPECTED OUTPUT", "RUN CONFIGURATION". Current file has mixed case ("Packets", "Expected Output", "Run Configuration") — change to all-caps.
4. **Keep** the packet rendering logic (speaker from metadata, timestamp parsing, 120-char truncation) — it matches the spec.
5. **Keep** the expected output collapsible with SHOW/HIDE toggle and max-height scroll — matches spec.
6. **Keep** the run configuration (speed factor default 20 min 1, buffer count default 5 min 1 max 10) — matches spec.
7. **Keep** the run button behavior (POST to `/api/runs`, navigate to `/run/{run_id}`, "Starting..." while in flight, inline error on failure) — matches spec.
8. **Add** `max-h-[400px] overflow-y-auto` to the expected output `<pre>` if not already present (it is present — confirm and keep).

### Step 3: Verify build

Run `cd web && npx next build` to confirm both pages compile and all routes are present. Check that `/trm/scenarios` is static and `/trm/scenarios/[tier]/[scenario]` is dynamic.

## Testing

No automated tests are specified or needed for these pages — they are client-side React components with no business logic beyond fetch + display. Manual verification:

1. Navigate to `/trm/scenarios` — verify tier groups render with formatted names, back link works
2. Click a scenario — verify detail page loads with all sections
3. Click "Run This Scenario" — verify navigation to `/run/{run_id}`
4. Stop the API and reload `/trm/scenarios` — verify error state renders inline
5. Test with empty `data/` directory — verify "No scenarios found." appears

## Doc Updates

None. The spec explicitly states no changes to docs, shared components, API, or other pages. `CLAUDE.md` already lists both routes in the Frontend section.
