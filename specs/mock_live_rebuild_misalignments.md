# Misalignments: Mock Live Pipeline UI Rebuild

_Spec: `specs/mock_live_rebuild.md` — reviewed against repo on 2026-04-01_

## Sources Page — Missing Back Link and Title

- **Spec says:** Back link to `/`, page title "Live Data Sources"
- **Repo reality:** `web/src/app/sources/page.tsx` has neither a back link nor a page title. The `HubTopBar` is rendered but no back-link or heading is provided below it.
- **Resolution:** Add a back link to `/` and a "Live Data Sources" heading. Match the pattern used by `/trm` hub pages.

## Sources Page — Card Description Text

- **Spec says:** Description: "Replays a scenario with full radio metadata through the full pipeline — capture, preprocessing, TRM routing — and streams results into the live dashboard."
- **Repo reality:** Current description is truncated: "Replays a scenario with full radio metadata, simulating live capture"
- **Resolution:** Update to match spec description.

## Live Page — Error Handling in useLiveData

- **Spec says:** On error: "silently ignore, retry next poll (do not crash or show error)." Status should revert to last known good state.
- **Repo reality:** `useLiveData.ts` dispatches `{ type: "error" }` on non-200 responses, which sets `status: "error"` and persists an error message. Only network-level errors (catch block) are silently ignored.
- **Resolution:** Remove the error dispatch for non-200 responses. All fetch failures should be silently ignored, keeping last known good state. Remove the `"error"` status entirely or keep it unused.

## Live Page — Global Empty State vs Per-Tab Empty States

- **Spec says:** Each tab has its own empty message: LIVE → "No data yet. Start the pipeline to begin.", EVENTS → "No events yet.", TIMELINE → "No transmissions yet."
- **Repo reality:** A single global empty-state block is shown above all tabs when `status === "empty"`, with text "No routed packets yet. Start the pipeline to see data here." The EVENTS and TIMELINE tabs do have per-tab empty states, but the LIVE tab shows nothing when empty.
- **Resolution:** Remove the global empty-state block. Add per-tab empty messages matching the spec text. LIVE tab needs its own empty state.

## Live Page — ContextInspector

- **Spec says:** No mention of ContextInspector on the live page.
- **Repo reality:** `ContextInspector` is rendered at the bottom of the page.
- **Resolution:** This is a useful debugging aid. Keep it — the spec's silence on it isn't a prohibition, and it matches the run page pattern.

## Live Page — TRMContext Missing incoming_packet

- **Spec says:** Context reconstruction should include `incoming_packet: null`.
- **Repo reality:** `useLiveData.ts` builds `TRMContext` without `incoming_packet`. The `TRMContext` type in `types/trm.ts` may or may not include this field.
- **Resolution:** Check if `TRMContext` type has `incoming_packet`. If so, set it to `null` in the hook. If not, this is fine — the spec was describing the conceptual shape.

## Spec Framing — "Clean Rebuild" vs Existing Implementation

- **Spec says:** "This spec treats the following as a clean rebuild" for `/sources`, `/live/[source]`, and `useLiveData`.
- **Repo reality:** All three files exist and are largely functional. The implementations are 80-90% aligned with the spec already.
- **Resolution:** Treat this as a targeted fix-up, not a delete-and-rewrite. The existing code is close — fix the specific misalignments documented above.
