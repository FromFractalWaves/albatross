# Albatross — Vision

*What a complete Albatross looks like.*

---

## TRM Tools

The TRM is the core of Albatross, but right now the only way to interact with it is to run a scenario and watch. A fully realized Albatross has a **TRM Tools** surface — a set of UI-driven tools for building, tuning, and evaluating TRM behavior.

### Dataset Creator

Building scenario datasets by hand-editing JSON is functional but brittle. The dataset creator lets you build scenarios visually — using the same thread lanes, event cards, and packet blocks that the dashboard already renders.

You create threads, create events, and place packets into them. The act of assembling a scenario in the UI *is* the creation of the expected output — the threads and events you build become `expected_output.json`, and the packets you place become `packets.json`. No separate annotation step. The structure you see is the structure you're testing against.

This also makes it possible to hand-curate edge cases that are hard to describe in JSON — interleaving patterns, ambiguous thread boundaries, events that span threads in non-obvious ways. If you can see it, you can build it.

### Prompt Tuning

The TRM's behavior is shaped by its system prompt. Right now, changing the prompt means editing a file and re-running. TRM Tools should surface prompt editing directly — tied to scenarios, so you can iterate on a prompt and immediately see how it changes routing decisions against a known dataset.

This may be intertwined with the scenario workflow: pick a scenario, edit the prompt, run, compare, repeat. The tuning loop should be tight enough that you can feel the effect of a change in seconds, not minutes.

### Scorer

The scorer compares a TRM run's output against a scenario's `expected_output.json` and produces structured metrics — thread accuracy, event accuracy, boundary detection, false groupings. The scoring metrics are defined in `docs/trm/spec.md`. The vision-level point: the scorer is a first-class tool in the UI, not a script you run from the terminal. It's what closes the loop between prompt tuning and measurable improvement.

### Golden Dataset

Tier 1 scenarios exist. Tiers 2–4 do not. A complete Albatross has all four tiers populated — plain conversation, radio domain, metadata-dominant, and adversarial edge cases. The tier definitions and example scenarios are specified in `docs/trm/spec.md`. Building the full dataset is what makes the scorer meaningful and the prompt tuning loop trustworthy.

---

## Pipeline Observability

In live mode, the TRM is the last stage of a multi-stage pipeline. If packets stop arriving, you need to know *where* they stopped — did capture die? Is preprocessing stuck? Is the TRM itself the bottleneck? Right now the only way to know is to watch terminal output, which defeats the purpose of having a web UI.

The dashboard should surface pipeline health directly — stage-by-stage status showing what's running, what's stalled, and where packets are in the pipeline. For the P25 reference implementation, that means visibility into capture → preprocessing → TRM. Each stage reports its state, and the UI renders it.

But like everything in Albatross, this can't be hardcoded to P25's three stages. Different domains have different pipeline shapes — a text-ingestion pipeline might have no preprocessing stage at all. The observability layer needs to work the same way as the rest of the system: the pipeline describes its own shape, and the UI adapts. What stages exist, what each stage reports, how health is measured — that comes from the pipeline, not from the frontend.

This is related to the adaptive metadata problem below. Both are instances of the same design principle: the data describes itself, the UI renders it.

---

## Live Mode

Live mode is the end state of the pipeline — real data flowing through capture → preprocessing → TRM → UI in real time. But architecturally, live mode shouldn't be a separate thing. The mock pipeline and the live pipeline should use the same push path. Mock capture emits packets over the same WebSocket channel that real capture will. The UI doesn't know or care whether the data is synthetic or coming off a radio.

This means getting mock to run push-only *is* the live mode architecture. Once that works end-to-end through the UI, plugging in real hardware is a plumbing change at the capture boundary — not a redesign. The pipeline is production-shaped regardless of what's feeding it.

Once the pipeline runs continuously rather than processing a finite scenario and stopping, a new category of problems opens up: session separation (when does one "run" end and the next begin?), data lifecycle for closed threads and resolved events, and browsing or querying historical routed data after the fact. None of this is needed for push-only mock, but it will need to be solved before live mode is real.

---

## Adaptive Metadata Display

Albatross is a general-purpose pipeline. The reference implementation is P25 radio, but the architecture is designed so any domain can plug in at the Packet boundary. The problem: metadata is domain-specific, and right now displaying it means writing UI code for each domain's metadata shape.

A complete Albatross solves this with adaptive metadata rendering — a system that can inspect the `metadata` field on any packet and render it meaningfully without domain-specific UI code. The metadata schema itself should drive the display. Add a new field to your packets, it shows up in the UI. Change the shape, the UI adapts.

This is what separates "a P25 radio tool" from "a general-purpose pipeline intelligence system." Without it, every new domain requires frontend work. With it, the UI is as domain-agnostic as the pipeline.

---

## How Work Gets Done

Albatross was built in phases — TRM first, then UI, then database pipeline. That sequencing made sense when each layer depended on the one before it. Now that the foundation is in place, work doesn't follow a linear path anymore.

Going forward, work is organized as specs. A spec describes what to change or build, gets aligned with the repo via the plan-spec skill, and becomes a build plan. When the work is done, the spec is deleted and the docs are updated. No phase numbers, no sub-phases. Just named units of work that say what they are.

The vision doc says *what Albatross should become*. Specs say *what to build next*. Docs say *what exists now*.

---

## What Else Belongs Here

This document is intentionally incomplete. It captures design intent as it crystallizes — not a roadmap, not a phase plan. Items land here when they represent what Albatross *should be*, independent of when or whether they get built.