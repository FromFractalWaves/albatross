# Build Plan: Mock Live Pipeline UI Rebuild

_Generated from `specs/mock_live_rebuild.md` — aligned with repo on 2026-04-01_

## Goal

Fix the specific drift between the spec and the existing `/sources`, `/live/[source]`, and `useLiveData` implementations. The existing code is ~85% aligned — this is a targeted fix-up, not a rewrite.

## Context

All three target files already exist and are largely functional:

- `web/src/app/sources/page.tsx` — source selection hub, missing nav and full description
- `web/src/app/live/[source]/page.tsx` — live dashboard with pipeline controls, empty states need rework
- `web/src/hooks/useLiveData.ts` — polling hook, error handling diverges from spec

Working and untouched: homepage (`web/src/app/page.tsx`), all shared components in `web/src/components/`, all types in `web/src/types/trm.ts`, all libs in `web/src/lib/`, all API endpoints, the TRM side of the UI.

See `specs/mock_live_rebuild_misalignments.md` for detailed misalignment analysis.

## Plan

### Step 1: Fix useLiveData error handling

**Files:** `web/src/hooks/useLiveData.ts`

The spec says all fetch errors should be silently ignored, retrying on the next poll and keeping last known good state. Currently, non-200 responses dispatch an error action that sets `status: "error"`.

Changes:
- Remove the `if (!threadsRes.ok || ...)` block that dispatches `{ type: "error" }`. Move all fetch failures into the catch block, which already silently ignores.
- Keep the `"error"` type in the Action union and reducer for safety, but it should never be dispatched. Alternatively, remove the error action type and `error` field from state entirely — the spec says errors are invisible to the UI.
- The `error` field in the return state can stay as `null` always, or be removed. If removed, update the destructuring in `live/[source]/page.tsx` to drop `error`.

### Step 2: Fix sources page

**Files:** `web/src/app/sources/page.tsx`

Changes:
- Add a back link to `/` below the `HubTopBar`. Use a `Link` component pointing to `/`, styled consistently with back links on other hub pages (e.g., `/trm/scenarios` has a back link to `/trm`).
- Add a page title: "Live Data Sources" — use the same heading style as other hub pages.
- Update the Mock Pipeline card description to match spec: "Replays a scenario with full radio metadata through the full pipeline — capture, preprocessing, TRM routing — and streams results into the live dashboard."

### Step 3: Fix live page empty states

**Files:** `web/src/app/live/[source]/page.tsx`

The spec requires per-tab empty states instead of the current global empty-state block.

Changes:
- Remove the global `{status === "empty" && ...}` block (lines ~163-167).
- In the LIVE tab: add an empty-state message "No data yet. Start the pipeline to begin." when `context?.active_threads.length` is falsy. Show this inside the LIVE tab div, not as a global block.
- EVENTS tab already has "No events yet." — verify the text matches spec exactly.
- TIMELINE tab currently says "No packets routed yet." — update to "No transmissions yet." per spec.
- Remove the `{error && ...}` block (lines ~153-155) since errors are now silently ignored by the hook. If keeping the error field, this block can stay but will never render.

### Step 4: Verify and smoke test

No code changes — manual verification:

1. Run `cd web && npm run dev`
2. Navigate `/` → `/sources` → verify back link, title, description
3. Navigate `/sources` → `/live/mock` → verify empty states per tab
4. Start mock pipeline → verify data flows into LIVE, EVENTS, TIMELINE tabs
5. Stop mock pipeline → verify controls reflect stopped state
6. Kill API server while live page is open → verify no error messages appear (silent retry)

## Testing

No new automated tests needed — the changes are cosmetic (text, layout) and behavioral (silent errors). The existing test suite (`tests/`) covers the API endpoints and mock pipeline. Frontend smoke testing covers the UI changes.

## Doc Updates

None needed. The spec itself documents the intended behavior. `CLAUDE.md` already describes the live page architecture accurately.
