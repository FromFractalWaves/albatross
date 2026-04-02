# Misalignments: Web UI Restructure

_Spec: `specs/webui_restruct.md` — reviewed against repo on 2026-04-01_

## Route structure — `/trm` is the scenario browser, not a hub

- **Spec says:** `/trm` is a tool selection hub (like `/sources`), listing available TRM tools as cards. The scenario browser lives at `/trm/scenarios`.
- **Repo reality:** `/trm` (`web/src/app/trm/page.tsx`) is the scenario browser itself — it fetches `/api/scenarios` and lists tiers with clickable scenario links. There is no tool hub layer above it.
- **Resolution:** Convert current `/trm/page.tsx` into a hub page with a single "Scenarios" card. Move the scenario browser logic into a new `web/src/app/trm/scenarios/page.tsx`. The scenario detail pages currently at `/scenarios/[tier]/[scenario]` should move to `/trm/scenarios/[tier]/[scenario]` to keep the URL hierarchy consistent under `/trm`.

## Route structure — `/sources` and `/live/[source]` not implemented

- **Spec says:** Homepage links to `/sources` (source selection page), which then links to `/live/[source]` (e.g. `/live/mock`). The live data view is parameterized by source.
- **Repo reality:** Homepage links directly to `/live`. There is no `/sources` route. `/live` is a static page with hardcoded mock pipeline controls — not a dynamic `[source]` route.
- **Resolution:** Add `/sources` page with source cards. Move current `/live/page.tsx` to `/live/[source]/page.tsx`, reading the source param from the route. Update homepage link to point to `/sources`.

## Homepage card descriptions

- **Spec says:** TRM Tools description: "Scenario runner, scoring, prompt tuning, golden dataset management, domain adaptation. Everything needed to evaluate and improve the TRM." Live Data description: "Real-time pipeline visualization. Thread lanes, event stream, packet timeline. Connects to live or mock radio data source."
- **Repo reality:** TRM Tools says "Scenario library, run configurations, and routing analysis." Live Data says "Real-time pipeline view with mock pipeline controls."
- **Resolution:** Update card descriptions and link targets to match spec.

## Scenario detail pages — URL mismatch

- **Spec says:** Scenarios live under `/trm/scenarios`, implying detail pages at `/trm/scenarios/[tier]/[scenario]`.
- **Repo reality:** Detail pages are at `/scenarios/[tier]/[scenario]` (`web/src/app/scenarios/[tier]/[scenario]/page.tsx`). The back-link in the detail page points to `/trm`.
- **Resolution:** Move `web/src/app/scenarios/[tier]/[scenario]/page.tsx` to `web/src/app/trm/scenarios/[tier]/[scenario]/page.tsx`. Update the back-link to point to `/trm/scenarios`.

## Already complete — no action needed

The following spec items are fully implemented from attempt 1:

- Homepage hub at `/` with two cards
- Header reads "Albatross" (correction #1)
- Dark/light theme toggle with localStorage persistence (correction #3)
- Mock pipeline API endpoints (`POST /api/mock/start`, `POST /api/mock/stop`, `GET /api/mock/status`)
- Live page hydrates from DB via `/api/live/threads`, `/events`, `/transmissions`
- Polls every 3s for updates
- `HubTopBar` and `TopBar` components properly separated
- Buffer counter hidden on live page via `hideBuffers` prop (correction #2)
