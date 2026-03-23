welcome to spagetti brain land

# thread-routing-module

The Thread Routing Module (TRM) is a component of **Albatross** — a general-purpose pipeline for turning continuous data streams into structured, queryable intelligence.

The TRM is the intelligence layer of any Albatross pipeline. It takes a stream of processed packets and does two things: figures out who is talking to whom (threads), and figures out what real-world thing they're talking about (events).

If you're new here, start with the Albatross spec. Everything else will make more sense after that.

---

## Docs

| Document | Description |
|----------|-------------|
| [`docs/albatross.md`](docs/albatross.md) | Start here — the Albatross pattern, pipeline stages, and where the TRM fits |
| [`docs/trm_spec.md`](docs/trm_spec.md) | TRM specification — packet types, routing decisions, golden dataset structure, scoring |
| [`docs/planning/trm_v1_plan.md`](docs/planning/trm_v1_plan.md) | v1 build plan — scope, architecture, Tier 1 dataset, success criteria |

---

## Status

Pre-build. Docs are being finalized and the Tier 1 golden dataset is being written. No runnable code yet.