# Albatross

A general-purpose pipeline for turning continuous data streams into structured, queryable intelligence.

The reference implementation is a P25 trunked radio dispatch intelligence system. The architecture is domain-agnostic — the radio pipeline is one application of a reusable pattern.

If you're new here, start with `docs/albatross.md`. Everything else will make more sense after that.

---

## Phases

Albatross is being built in phases. Each phase is documented separately.

| Phase | Description | Status | Key Documents |
|-------|-------------|--------|---------------|
| **Phase 1** — TRM Core | Async packet pipeline, LLM-backed thread and event router, Tier 1 scenario dataset | Complete | `docs/trm/spec.md`, `docs/trm/runtime_loop.md` |
| **Phase 2** — Web UI & API | FastAPI backend, WebSocket streaming, Next.js dashboard with live run visualization | Complete | `docs/web/api.md` |
| **Phase 3** — Database & Data Pipeline | Shared DB, contracts layer, mock pipeline, UI hydration from DB | Complete | `docs/pipeline/database.md` |
| **Phase 4** — Web UI Restructure | Homepage hub, TRM tools hub, live data source selection, mock pipeline UI controls | Complete | `docs/web/ui_spec.md` |

---

## Docs

| Document | Description |
|----------|-------------|
| `docs/albatross.md` | The Albatross pattern — pipeline stages, contracts, how to add a new implementation |
| `docs/pipeline/architecture.md` | Full radio pipeline architecture — DB schema, stage handoffs, production TRM requirements |
| `docs/pipeline/database.md` | Database & data pipeline — ORM models, contracts layer, mock pipeline, persistence |
| `docs/trm/spec.md` | TRM specification — packet types, routing decisions, golden dataset tiers, scoring metrics |
| `docs/trm/runtime_loop.md` | TRM runtime loop — context schema, per-packet decision cycle, buffering, open problems |
| `docs/web/api.md` | Web UI & API architecture — REST endpoints, WebSocket protocol, frontend pages |
| `docs/web/ui_spec.md` | Visual design spec — design tokens, component specs, layout, interaction patterns |
| `docs/web/ui_mockup.jsx` | Interactive React mockup — component reference |

---

## Status

Phases 1 through 4 are complete.

The TRM pipeline runs against four Tier 1 scenarios. The FastAPI backend serves scenario data and streams live runs over WebSocket. The Next.js frontend has a full dashboard — thread lanes, events view, chronological timeline, decision badges.

The database layer is complete: SQLAlchemy 2.0 async models with Alembic migrations, shared Pydantic boundary types in `contracts/`, and DB-driven TRM routing via `trm/main_live.py`.

The web UI is restructured around a hub pattern: a homepage routes to TRM Tools and Live Data. TRM Tools exposes the scenario runner (with more tools to come). Live Data exposes a source selection page — currently Mock Pipeline, with real radio hardware deferred until Phase 5. The mock pipeline is controlled from the browser: navigate to Live Data → Mock Pipeline → Start.

---

## Running

**API:**
```bash
uvicorn api.main:app --reload
```

**Web UI:**
```bash
cd web && npm run dev
```

**Database migrations:**
```bash
alembic upgrade head
```

**Mock pipeline:**

The mock pipeline is controlled from the web UI. Navigate to Live Data → Mock Pipeline → Start. This resets the database and launches the full pipeline stack automatically.

To run manually (for debugging):
```bash
python db/reset.py                   # clear all tables
python preprocessing/mock/run.py &   # start preprocessing (polls for captured rows)
python capture/mock/run.py &         # start capture (writes packets to DB)
python trm/main_live.py              # start TRM (polls for processed rows, routes + persists)
```

**Tests:**
```bash
python -m pytest tests/ -v
```

Requires `ANTHROPIC_API_KEY`. LLM calls are mocked in tests — no API key needed to run the test suite.