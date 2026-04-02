# Albatross Web UI — Restructure Spec

**Status:** Draft  
**Scope:** Web UI restructure, homepage routing, mock live data API endpoint, and small UI corrections  
**References:** `docs/ui_spec.md`, `docs/webui-api.md`, `docs/albatross_phase_3.md`, `docs/db-datapipeline.md`

---

## Overview

The current web UI has two pages:

- `/` — scenario runner (TRM tools)
- `/live` — live data view (structurally similar to `/`, runs against live data)

This spec restructures the UI around a **homepage hub** that clearly separates two domains:

1. **TRM Tools** — offline, controlled, workbench for tuning the TRM
2. **Live Data** — real-time, stream-fed, pipeline visualization

These are fundamentally different in data source, update pattern, and purpose. Mixing them or treating them as the same page creates long-term confusion. The split should be made now before the UI grows further.

---

## Route Structure

### Current
```
/           → scenario runner
/live       → live data (mirrors /)
```

### Target
```
/                → homepage (hub/router)
/trm             → TRM Tools (moved from /)
/sources         → Live Data source selection
/live/[source]   → Live Data view for a selected source
```

---

## Homepage (`/`)

A simple hub page. No data fetching. Two clearly labeled entry points.

**Layout:** Two large cards or sections side by side (or stacked on mobile):

### Card 1 — TRM Tools
- **Label:** `TRM Tools`
- **Description:** Scenario runner, scoring, prompt tuning, golden dataset management, domain adaptation. Everything needed to evaluate and improve the TRM.
- **Link:** `/trm`

### Card 2 — Live Data
- **Label:** `Live Data`
- **Description:** Real-time pipeline visualization. Thread lanes, event stream, packet timeline. Connects to live or mock radio data source.
- **Link:** `/sources`

**Design notes:**
- Dark theme consistent with existing UI (`docs/ui_spec.md` design tokens)
- Header should read `Albatross` (not `TRM`) — see Corrections section
- Minimal — this is a router, not a dashboard

---

## TRM Tools (`/trm`)

This is the existing `/` page, moved. No functional changes in this spec — just route migration.

**Contains (existing):**
- Scenario selector
- Scenario runner / live run visualization
- Thread lanes
- Events view
- Chronological timeline
- Decision badges
- Scoring display

---

## Sources (`/sources`)

A source selection page. No data fetching. Lists available data sources the user can connect to. Selecting a source navigates to `/live/[source]`.

**Initial sources:**

| Source | Route | Description |
|--------|-------|-------------|
| Mock Pipeline | `/live/mock` | Replays a scenario with full radio metadata, simulating live capture |

**Future sources (not in scope for this spec):**
- Real radio hardware (RTL-SDR / gr-op25)
- Recorded capture replay
- Remote feeds

**Design notes:**
- Similar card layout to homepage
- Each source card shows name, description, and status (e.g. available / not configured)
- Selecting a source navigates to its live view — no pipeline starts on selection

---

## Live Data View (`/live/[source]`)

The live data view for a specific source. The existing `/live` page becomes `/live/mock` as the first concrete implementation.

**Behavior:**
- Source is determined by the `[source]` route param
- Page does not auto-start any pipeline on load
- User explicitly starts the data source via a Start button on the page
- On Start: calls the appropriate API endpoint for that source (e.g. `POST /api/mock/start` for mock)
- On Stop: calls the stop endpoint
- Status indicator shows running / stopped

**Mock source specifics (`/live/mock`):**

### Mock Pipeline API Endpoints

The mock pipeline (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) currently runs as CLI scripts. This spec adds FastAPI endpoints to control it from the UI.

```
POST /api/mock/start    → starts the mock pipeline (capture → preprocessing → TRM)
POST /api/mock/stop     → stops the mock pipeline
GET  /api/mock/status   → returns running | stopped
```

**Behavior:**
- The mock pipeline replays a scenario augmented with full radio metadata, simulating live capture
- It feeds into the same DB and WebSocket path as real live data
- The pipeline does NOT start automatically on page load — only when the user hits Start
- This validates the full live data path end-to-end before real radio hardware is available

### UI Hydration from DB

On page load, `/live` fetches existing thread and packet data from the DB to populate the view before the WebSocket stream takes over. This is the remaining sub-phase from `docs/albatross_phase_3.md`.

**Behavior:**
- On mount: single DB fetch via API to hydrate thread list and recent packets into Zustand store
- After hydration: WebSocket connection opens and feeds new data into the same store
- No polling — push only after initial load

---

## UI Corrections

Small fixes to be applied globally or per-component:

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 1 | Top-left header / nav | Reads `TRM` | Change to `Albatross` |
| 2 | Top-right | Buffer counter displayed globally | Remove — buffers are per-packet, not a global pipeline stat. Buffer state is visible in individual packet/decision views only. |
| 3 | Theme | Light/dark mode not implemented | Add dark/light toggle. Default: dark. Persist preference in Zustand (localStorage via persist middleware). |

---

## Zustand Store Notes

The UI already uses Zustand (or should — verify in `web/`). For this spec:

- **UI state** (theme preference, selected scenario, active view): Zustand with `persist` middleware → `localStorage`
- **Live data** (threads, packets, transmissions): Zustand without persist — hydrated from DB on mount, then fed by WebSocket. No stale data on refresh; always re-hydrates from DB.

---

## What This Spec Does NOT Include

To keep scope clean:

- No changes to TRM core logic
- No changes to DB schema or ORM models
- No changes to WebSocket protocol
- No new analysis views or visualization features
- No radio capture integration (deferred until hardware available)
- No TanStack Query migration (future consideration when cache invalidation complexity is warranted)

---