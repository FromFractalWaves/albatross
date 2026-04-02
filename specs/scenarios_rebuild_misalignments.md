# Misalignments: Scenarios Browser Rebuild

_Spec: `specs/scenarios_rebuild.md` — reviewed against repo on 2026-04-01_

## Pages are not "broken" — they build and render

- **Spec says:** Pages are broken following the UI restructure and should be deleted and rebuilt from scratch.
- **Repo reality:** Both `web/src/app/trm/scenarios/page.tsx` and `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx` compile, build successfully (Next.js 16.2.1), and render. All imports resolve. The issue is design/behavior drift from the intended post-restructure UX, not compilation failures.
- **Resolution:** Treat as a rewrite-in-place rather than delete-and-recreate. The existing files are the correct locations — their contents will be fully replaced to match the spec.

## TabBar usage on scenarios browser page

- **Spec says:** Page should have a title "Scenarios" and a back link to `/trm`. No mention of tabs.
- **Repo reality:** Current page uses `TabBar` with SCENARIOS / LIVE (disabled) / HISTORY (disabled) tabs. No page title, no back link.
- **Resolution:** Remove `TabBar` import and usage. Add page title and back link per spec. TabBar component itself stays — it may be used elsewhere.

## Tier name formatting

- **Spec says:** Tier names formatted as human-readable, e.g. `tier_one` → "Tier One" (title case).
- **Repo reality:** Current `formatTier()` does `replace(/_/g, " ").toUpperCase()` → "TIER ONE" (all caps).
- **Resolution:** Change formatting to title case per spec.

## Scenario name display

- **Spec says:** Each row shows formatted name (strip `scenario_NN_` prefix, replace underscores with spaces) plus the raw name as a secondary label.
- **Repo reality:** Current rows show raw name only (e.g. `scenario_01_simple_two_party`), no formatting, no secondary label.
- **Resolution:** Add name formatting and raw-name subtitle per spec.

## Empty state

- **Spec says:** Show "No scenarios found." when the API returns an empty array.
- **Repo reality:** No empty-state handling — renders nothing if array is empty.
- **Resolution:** Add empty state per spec.

## Error message wording

- **Spec says:** Error text should be "Failed to load scenarios. Is the API running?"
- **Repo reality:** Error text is generic `Error: {e.message}`.
- **Resolution:** Use spec wording.
