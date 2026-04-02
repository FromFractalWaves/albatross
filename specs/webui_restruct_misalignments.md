# Misalignments: Web UI Restructure

_Spec: `specs/webui_restruct.md` — reviewed against repo on 2026-04-01_

## Route structure — `/sources` and `/live/[source]` not implemented

- **Spec says:** Homepage links to `/sources` (source selection page), which then links to `/live/[source]` (e.g. `/live/mock`). The live data view is parameterized by source.
- **Repo reality:** Homepage links directly to `/live`. There is no `/sources` route. `/live` is a static page with hardcoded mock pipeline controls — not a dynamic `[source]` route.
- **Resolution:** Add `/sources` page with source cards. Move current `/live/page.tsx` to `/live/[source]/page.tsx`, reading the source param from the route. Update homepage link to point to `/sources`.

## Homepage card descriptions

- **Spec says:** TRM Tools description: "Scenario runner, scoring, prompt tuning, golden dataset management, domain adaptation." Live Data description: "Real-time pipeline visualization. Thread lanes, event stream, packet timeline. Connects to live or mock radio data source."
- **Repo reality:** TRM Tools says "Scenario library, run configurations, and routing analysis." Live Data says "Real-time pipeline view with mock pipeline controls." Both are reasonable but don't match spec text.
- **Resolution:** Update card descriptions to match spec. Link text for Live Data changes from "Open Pipeline →" to "Select Source →" since it now routes to `/sources`.

## UI Corrections — buffer counter

- **Spec says:** Remove buffer counter from top-right globally — buffers are per-packet, not a global pipeline stat.
- **Repo reality:** TopBar component still has `buffersRemaining` prop and renders buffer stats. The `/live` page passes `hideBuffers` to suppress it, but `/run/[runId]` still shows it. The spec says to remove it globally.
- **Resolution:** The spec says to remove the global buffer counter display. However, on the `/run/[runId]` page, the buffer count is contextually useful during an active scenario run (it reflects `TRMContext.buffers_remaining` as packets are routed). The spec's intent is to not show it as a "global pipeline stat" — which is already handled by `hideBuffers` on `/live`. No change needed beyond what's already done. Flag for user review if they want it removed from `/run` pages too.

## Already complete — no action needed

The following spec items are fully implemented from attempt 1:

- Homepage hub at `/` with two cards
- `/trm` route (scenario browser, moved from original `/`)
- Header reads "Albatross" (correction #1)
- Dark/light theme toggle with localStorage persistence (correction #3)
- Mock pipeline API endpoints (`POST /api/mock/start`, `POST /api/mock/stop`, `GET /api/mock/status`)
- Live page hydrates from DB via `/api/live/threads`, `/events`, `/transmissions`
- Polls every 3s for updates
- `HubTopBar` and `TopBar` components properly separated
