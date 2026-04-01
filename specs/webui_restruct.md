# Build Plan: Web UI Restructure

_Generated from spec — aligned with repo on 2026-04-01_

## Goal

Restructure the web UI around a homepage hub that separates TRM Tools from Live Data, add mock pipeline API controls, and fix UI labeling/theme issues.

## Context

The frontend is a Next.js 16 / React 19 app in `web/` with Tailwind CSS v4. Current routes:

- `/` (`web/src/app/page.tsx`) — Scenario hub with HubTopBar, fetches from `/api/scenarios`, links to scenario detail pages. Already has a TabBar with SCENARIOS (active), LIVE (disabled), HISTORY (disabled).
- `/live` (`web/src/app/live/page.tsx`) — Live pipeline view using `useLiveData` hook (polls `/api/live/*` every 3s). Three tabs: LIVE, EVENTS, TIMELINE.
- `/run/[runId]` (`web/src/app/run/[runId]/page.tsx`) — Live run visualization via WebSocket.
- `/scenarios/[tier]/[scenario]` — Scenario detail page, launches runs.

State management is `useReducer` + `useState` — no Zustand. Two custom hooks: `useRunSocket.ts` (WebSocket) and `useLiveData.ts` (polling). 13 components in `web/src/components/`.

Backend is FastAPI (`api/main.py`) with three route modules: `scenarios.py`, `runs.py`, `live.py`. Mock pipeline is three CLI scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) with no API control surface.

## Plan

### Step 1: Create homepage hub at `/`

**Files:** `web/src/app/page.tsx` (rewrite), `web/src/components/HubTopBar.tsx` (modify)

Replace the current scenario-listing homepage with a minimal hub page. Two large cards linking to `/trm` and `/live`. No data fetching. Dark themed, consistent with existing design tokens in `web/src/app/globals.css`.

Update `HubTopBar.tsx`: change display text from "TRM" to "Albatross" and subtitle from "Thread Routing Module" to a short project tagline or remove the subtitle.

### Step 2: Move scenario hub to `/trm`

**Files:** `web/src/app/trm/page.tsx` (new — current `page.tsx` content moves here), `web/src/app/scenarios/[tier]/[scenario]/page.tsx` (update back-link from `/` to `/trm`)

Move the entire current homepage (scenario listing, TabBar, tier cards) to `/trm/page.tsx`. Update the back-link in the scenario detail page from `/` to `/trm`. Check `web/src/app/run/[runId]/page.tsx` for any navigation back to `/` that should point to `/trm`.

### Step 3: UI label corrections

**Files:** `web/src/components/TopBar.tsx`, `web/src/components/HubTopBar.tsx`, `web/src/app/layout.tsx`

- `TopBar.tsx` line 53: change "TRM" brand text to "Albatross".
- `HubTopBar.tsx` line 4/6: already handled in Step 1.
- `layout.tsx`: update page title and meta description from "TRM — Thread Routing Module" to "Albatross".
- `TopBar.tsx`: remove the buffer counter display from the stats section when used on the `/live` page. Either accept a prop to hide it, or remove it from TopBar and let the run page show buffer state via BufferZone only.

### Step 4: Dark/light theme toggle

**Files:** `web/src/app/globals.css` (add light theme variables), `web/src/app/layout.tsx` (apply theme class), `web/src/components/TopBar.tsx` (add toggle button), `web/src/components/HubTopBar.tsx` (add toggle button)

Add CSS custom properties for a light theme alongside the existing dark values. Use a `dark`/`light` class on `<html>` to switch. Store preference in `localStorage`, default to dark. Add a simple sun/moon toggle icon to both TopBar and HubTopBar. Use `useState` initialized from `localStorage` — no state library needed.

### Step 5: Mock pipeline API endpoints

**Files:** `api/routes/mock.py` (new), `api/main.py` (mount new router)

Create three endpoints:

- `POST /api/mock/start` — Launches the three mock pipeline scripts (`capture/mock/run.py`, `preprocessing/mock/run.py`, `trm/main_live.py`) as subprocesses via `asyncio.create_subprocess_exec`. Store process handles in app state (similar to how `app.state.run_manager` works). Reset the DB first via `db/reset.py` logic (truncate tables). Return `{status: "started"}`.
- `POST /api/mock/stop` — Terminates the subprocess handles. Return `{status: "stopped"}`.
- `GET /api/mock/status` — Return `{status: "running" | "stopped"}` based on whether subprocesses are alive.

The scripts already have auto-exit logic (idle timeouts), so the stop endpoint is for early termination. Each script runs in its own subprocess with the project venv's Python.

### Step 6: Live page mock pipeline controls

**Files:** `web/src/app/live/page.tsx` (modify)

Add a control bar at the top of the `/live` page with:
- A "Start Mock Pipeline" button that calls `POST /api/mock/start`
- A "Stop" button that calls `POST /api/mock/stop`
- A status indicator that polls `GET /api/mock/status` (or reads it after start/stop responses)

This lets the user trigger a full mock pipeline run from the browser and watch data flow into the live view.

## Testing

- **Route tests**: Verify `/trm` serves the scenario list, `/` serves the hub. Check that `/scenarios/[tier]/[scenario]` back-link points to `/trm`. These are manual browser checks or could be light Playwright tests if the project adds them later.
- **Mock pipeline API tests**: Add tests in `tests/` following the existing pattern (e.g., `tests/test_live_api.py` uses `httpx.AsyncClient` with `app`). Test `POST /api/mock/start` returns 200, `GET /api/mock/status` returns running, `POST /api/mock/stop` returns stopped. Mock `asyncio.create_subprocess_exec` to avoid actually launching scripts in tests.
- **Existing tests**: Run `python -m pytest tests/ -v` to confirm nothing breaks. The 9 scenario endpoint tests reference `/api/scenarios` which is unchanged. The 7 live API tests reference `/api/live/*` which is unchanged.

## Doc Updates

- `CLAUDE.md` — Update the Frontend section: new route structure (`/`, `/trm`, `/live`), mention mock pipeline API endpoints, update component descriptions (HubTopBar now says Albatross, TopBar rebranded).
- `docs/web/api.md` — Add mock pipeline endpoints (`/api/mock/start`, `/stop`, `/status`). Update route table.
- `docs/web/ui_spec.md` — Update with light/dark theme toggle, new homepage layout, Albatross branding.
- `docs/albatross.md` — Note the UI restructure in the phase history section.
