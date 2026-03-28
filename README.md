thread-routing-module
The Thread Routing Module (TRM) is a component of Albatross — a general-purpose pipeline for turning continuous data streams into structured, queryable intelligence.
The TRM is the intelligence layer of any Albatross pipeline. It takes a stream of processed packets and does two things: figures out who is talking to whom (threads), and figures out what real-world thing they're talking about (events).
If you're new here, start with the Albatross spec. Everything else will make more sense after that.

Docs
DocumentDescriptiondocs/albatross.mdStart here — the Albatross pattern, pipeline stages, and where the TRM fitsdocs/trm_spec.mdTRM specification — packet types, routing decisions, golden dataset structure, scoringdocs/runtime_loop.mdRuntime loop — context schema, per-packet decision cycle, buffering, output formatdocs/planning/trm_v1_plan.mdv1 build plan — scope, architecture, Tier 1 dataset, success criteria

Status
In progress. Core pipeline is running — packet loading, async queue, and LLM-backed router are all live. One Tier 1 scenario built and passing. Scorer not yet built.