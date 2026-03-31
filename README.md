# Albatross

A general-purpose pipeline for turning continuous data streams into structured, queryable intelligence.

The reference implementation is a P25 trunked radio dispatch intelligence system. The architecture is domain-agnostic — the radio pipeline is one application of a reusable pattern.

If you're new here, start with `docs/albatross.md`. Everything else will make more sense after that.

---

## Phases

Albatross is being built in phases. Each phase is documented separately.

| Phase | Description | Status | Key Documents |
|-------|-------------|--------|---------------|
| **Phase 1** — TRM Core | Async packet pipeline, LLM-backed thread and event router, Tier 1 scenario dataset | Complete | `docs/trm_spec.md`, `docs/trm_runtime_loop.md` |
| **Phase 2** — Web UI & API | FastAPI backend, WebSocket streaming, Next.js dashboard with live run visualization | Complete | `docs/webui-api.md` |
| **Phase 3** — Database & Data Pipeline | Shared DB, contracts layer, mock pipeline, UI hydration from DB | In progress (3.1, 3.2, 3.2b, 3.3 complete) | `docs/albatross_phase_3.md`, `docs/db-datapipeline.md` |

> **Note on document naming:** Some documents in `docs/` use naming conventions from earlier in the project when scope was narrower. `docs/albatross_runtime_loop.md` is the architectural spec for the full radio pipeline and database design — it is the primary reference for Phase 3 despite its name. The phase numbering inside `docs/webui-api.md` (phases 1–6) refers to sub-phases of the web build, not Albatross-level phases.

---

## Docs

| Document | Description |
|----------|-------------|
| `docs/albatross.md` | The Albatross pattern — pipeline stages, contracts, how to add a new implementation |
| `docs/albatross_runtime_loop.md` | Full radio pipeline architecture — DB schema, stage handoffs, production TRM requirements |
| `docs/albatross_phase_3.md` | Phase 3 plan — database setup, mock pipeline, UI hydration |
| `docs/db-datapipeline.md` | Phase 3 implementation specs — synthetic data, simulation parameters, DB schema |
| `docs/trm_spec.md` | TRM specification — packet types, routing decisions, golden dataset tiers, scoring metrics |
| `docs/trm_runtime_loop.md` | TRM runtime loop — context schema, per-packet decision cycle, buffering, open problems |
| `docs/trm_outline.md` | TRM current state — what's built, key design decisions |
| `docs/webui-api.md` | Web UI & API build plan — six sub-phases, all complete |
| `docs/ui_spec.md` | Visual design spec — design tokens, component specs, layout, interaction patterns |
| `docs/ui_mockup.jsx` | Interactive React mockup — component reference |

---

## Status

Phase 1 and Phase 2 are complete. The TRM pipeline runs against four Tier 1 scenarios. The FastAPI backend serves scenario data and streams live runs over WebSocket. The Next.js frontend renders a live dashboard — thread lanes, events view, chronological timeline, decision badges.

Phase 3 is in progress. Sub-phases 3.1 (DB schema + ORM), 3.2 (contracts layer), 3.2b (mock pipeline + DB reset), and 3.3 (TRM persistence layer) are complete. SQLAlchemy 2.0 async models with Alembic migrations, shared Pydantic boundary types in `contracts/`, mock capture/preprocessing scripts, and DB-driven TRM routing (`src/main_live.py`) are in place. The remaining sub-phase wires up UI hydration from the database.

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

**Mock pipeline (capture + preprocessing + TRM):**
```bash
python db/reset.py                  # clear all tables
python preprocessing/mock/run.py &  # start preprocessing (polls for captured rows)
python capture/mock/run.py &        # start capture (writes packets to DB)
python src/main_live.py             # start TRM (polls for processed rows, routes + persists)
```

**Tests:**
```bash
python -m pytest tests/ -v
```

Requires `ANTHROPIC_API_KEY`. LLM calls are mocked in tests — no API key needed to run the test suite.