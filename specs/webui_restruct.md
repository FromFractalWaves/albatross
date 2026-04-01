# Albatross Web UI — Restructure Spec


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
/           → homepage (hub/router)
/trm        → TRM Tools (moved from /)
/live       → Live Data (remains, receives structural improvements)
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
- **Link:** `/live`

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

**Subagent alignment task:** Verify all internal links, API calls, and WebSocket connections that currently reference `/` are updated to `/trm`. Check `web/` for any hardcoded routes.

---

## Live Data (`/live`)

The existing `/live` page receives two changes in this spec:

### 1. Mock Pipeline API Endpoint

The mock pipeline (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) currently runs as a set of CLI scripts. This spec adds a FastAPI endpoint to start and stop a mock run so it can be triggered from the UI.

**New API endpoints:**

```
POST /api/mock/start    → starts the mock pipeline (capture → preprocessing → TRM)
POST /api/mock/stop     → stops the mock pipeline
GET  /api/mock/status   → returns running | stopped
```

**Behavior:**
- The mock pipeline replays a scenario augmented with full radio metadata, simulating live capture
- It feeds into the same DB and WebSocket path as real live data
- The `/live` page can trigger a mock run via these endpoints without leaving the browser
- This validates the full live data path end-to-end before real radio hardware is available

**Subagent alignment task:** Review `capture/mock/run.py`, `preprocessing/mock/run.py`, and `trm/main_live.py` to understand process lifecycle. Determine whether subprocess management (e.g. `asyncio.create_subprocess_exec`) or a shared process registry is appropriate. Check `api/main.py` for existing patterns.

### 2. UI Hydration from DB

On page load, `/live` fetches existing thread and packet data from the DB to populate the view before the WebSocket stream takes over. This is the remaining sub-phase from `docs/albatross_phase_3.md`.

**Behavior:**
- On mount: single DB fetch via API to hydrate thread list and recent packets into Zustand store
- After hydration: WebSocket connection opens and feeds new data into the same store
- No polling — push only after initial load

**Subagent alignment task:** Review `docs/albatross_phase_3.md` for hydration requirements and `docs/db-datapipeline.md` for hydration query design. Verify Zustand store shape matches DB contract types in `contracts/`.

---

## UI Corrections

Small fixes to be applied globally or per-component:

| # | Location | Issue | Fix |
|---|----------|-------|-----|
| 1 | Top-left header / nav | Reads `TRM` | Change to `Albatross` |
| 2 | Top-right | Buffer counter displayed globally | Remove — buffers are per-packet, not a global pipeline stat. Buffer state is visible in individual packet/decision views only. |
| 3 | Theme | Light/dark mode not implemented | Add dark/light toggle. Default: dark. Persist preference in Zustand (localStorage via persist middleware). |

**Subagent alignment task:** Search `web/` for all instances of the string `TRM` used as a display label (not a technical term). Distinguish between label usage (fix) and code/type references (do not change).

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

## Subagent Instructions

This spec is intended to be consumed by a Claude Code subagent. Before producing a build plan, the subagent must:

1. Read all referenced docs: `docs/ui_spec.md`, `docs/webui-api.md`, `docs/albatross_phase_3.md`, `docs/db-datapipeline.md`
2. Read `CLAUDE.md` for project conventions
3. Inspect `web/` directory structure and identify current route files
4. Inspect `api/main.py` for existing endpoint patterns
5. Inspect `contracts/` for shared types used at the UI/API boundary
6. Resolve any naming or structural drift between this spec and the actual codebase
7. Flag any conflicts or ambiguities before generating the build plan

**Output:** A phased build plan with sub-phases, each with:
- Clear scope boundary
- Files to create or modify
- Doc update checkpoint at phase end
- Acceptance criteria