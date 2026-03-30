albatross
The Thread Routing Module (TRM) is a component of Albatross — a general-purpose pipeline for turning continuous data streams into structured, queryable intelligence.
The TRM is the intelligence layer of any Albatross pipeline. It takes a stream of processed packets and does two things: figures out who is talking to whom (threads), and figures out what real-world thing they're talking about (events).
If you're new here, start with the Albatross spec. Everything else will make more sense after that.

Docs
| Document | Description |
|----------|-------------|
| `docs/albatross.md` | Start here — the Albatross pattern, pipeline stages, and where the TRM fits |
| `docs/trm_spec.md` | TRM specification — packet types, routing decisions, golden dataset structure, scoring |
| `docs/runtime_loop.md` | Runtime loop — context schema, per-packet decision cycle, buffering, output format |
| `docs/trm_outline.md` | Current state and next steps |
| `docs/webui-api.md` | 7-phase plan for web UI and API |
| `docs/ui_spec.md` | Visual design spec — design tokens, component specs, layout, interaction patterns |
| `docs/ui_mockup.jsx` | Interactive React mockup — component reference for dashboard implementation |

Status
In progress. Core pipeline running with four Tier 1 scenarios. FastAPI backend serves scenario data and streams live runs over WebSocket. Next.js frontend with visual dashboard — three-tab interface (live thread lanes, events view, chronological timeline) with color-coded packets, decision badges, buffer zone, and live stats. Scorer not yet built.