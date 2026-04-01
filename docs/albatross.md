# Albatross

*A general-purpose pipeline for turning continuous data streams into structured, queryable intelligence.*

---

## What Is Albatross?

Albatross is not a framework. It's a pattern — a way of thinking about how to take a raw, continuous stream of domain-specific data and systematically transform it into structured knowledge you can reason about.

It was discovered, not designed. The first implementation was a radio dispatch intelligence pipeline built on top of OP25. While building that system, a reusable architecture emerged beneath the radio-specific details. Albatross is that architecture, named and documented so it can be applied elsewhere.

---

## The Pattern

```
Data Stream → Packets → Preprocessing → TRM → Analysis
```

Every Albatross implementation maps its domain onto these five stages. The stages are always present. What changes between implementations is what each stage *is*.

---

## The Five Stages

### 1. Data Stream

The raw, continuous source of information. Albatross doesn't care what it is — RF signals, API events, log files, sensor output, message queues. The only requirement is that it emits something that can be segmented into discrete units.

**The question this stage answers:** *What is the raw input?*

### 2. Packets

The ingestion layer. The stream is segmented into discrete, structured units called Packets. Every Packet conforms to a base schema regardless of domain:

```
Packet {
  packet_id,      # unique identifier
  packet_type,    # what kind of packet this is
  timestamp,      # when it occurred
  source,         # where it came from
  metadata,       # domain-specific context
  payload         # the content to be processed
}
```

Domain-specific implementations extend this base. The radio pipeline produces `TransmissionPacket`, which adds audio path, talkgroup ID, source unit IDs, and encryption status on top of the base fields.

Nothing downstream depends on the domain-specific fields directly — only the TRM configuration does, via the metadata field.

**The question this stage answers:** *How do we turn a stream into discrete, storable units?*

### 3. Preprocessing

Domain-specific enrichment. The raw Packet payload is transformed into a `ProcessedPacket` — the named type that the TRM ingests. In some domains this is heavy (radio: multi-pass ASR to convert audio into text). In others it may be trivial (a stream of text messages needs no preprocessing at all, and the Packet is promoted to a `ProcessedPacket` directly).

Every `ProcessedPacket` conforms to this schema:

```json
{
  "id": "uuid",
  "timestamp": "ISO8601",
  "text": "processed content",
  "metadata": {}
}
```

The `metadata` field is populated from the upstream Packet's metadata. This is the bridge between the domain-specific ingestion layer and the domain-agnostic intelligence layer.

Domain-specific implementations may define a named `ProcessedPacket` subtype. The radio pipeline produces `ProcessedTransmissionPacket` — the `TransmissionPacket` after ASR has run. See the TRM spec for the `ProcessedPacket` schema definition and the radio pipeline spec for `ProcessedTransmissionPacket`.

**The question this stage answers:** *How do we prepare a Packet for routing?*

### 4. TRM — Thread Routing Module

The intelligence layer. The TRM is fully domain-agnostic. It receives a stream of `ProcessedPacket` objects and simultaneously maintains two structures:

- **Threads** — communication patterns (who is talking to whom)
- **Events** — real-world occurrences (what is being talked about)

For every incoming `ProcessedPacket` it makes two independent decisions:

| Layer | Decisions |
|---|---|
| Thread | `new` / `existing` / `unknown` |
| Event | `new` / `existing` / `none` / `unknown` |

The TRM knows nothing about radio, audio, or talkgroups. It knows about `ProcessedPacket` objects, metadata weights, conversational structure, and routing logic. Domain-specific behavior is injected through configuration — telling the TRM what the metadata fields mean and how much to trust them.

Output is always structured JSON. Freeform reasoning may be retained as a debug artifact but is not part of the contract.

**The question this stage answers:** *What is this `ProcessedPacket` part of, and what is it about?*

### 5. Analysis

Everything downstream of the TRM. Summaries, reports, storage, UI, alerting — whatever the use case demands. This stage consumes the structured thread and event output produced by the TRM.

Because the TRM output is always structured JSON with a consistent schema, the Analysis layer can be built independently of the domain. A summary generator, a timeline UI, or a reporting pipeline built for radio data could theoretically be reused for any other Albatross implementation.

**The question this stage answers:** *What do we do with the structured intelligence?*

---

## What Albatross Is Not

**Not a framework.** There is no Albatross library to import. It's a pattern you implement.

**Not prescriptive about technology.** Each stage can be any language, any infrastructure. The contracts between stages matter. The implementation of each stage doesn't.

**Not finished.** Albatross is being distilled from a real implementation. The radio pipeline is the reference. As that project matures, the abstraction will sharpen.

---

## The Contracts

The only thing that makes stages interoperable is the contracts at their boundaries.

| Boundary | Contract |
|---|---|
| Stream → Packets | Base `Packet` schema |
| Preprocessing → TRM | `ProcessedPacket` (`id`, `timestamp`, `text`, `metadata`) |
| TRM → Analysis | Structured JSON routing output (`thread_id`, `event_id`, decisions, confidence) |

Implementations can do anything they want inside a stage. They must honor these contracts at the boundaries.

---

## The Reference Implementation

The radio dispatch intelligence pipeline is the first and currently only Albatross implementation. It maps to the pattern as follows:

| Albatross Stage | Radio Implementation |
|---|---|
| Data Stream | OP25 trunked radio receiver |
| Packets | `TransmissionPacket` (audio + radio metadata) |
| Preprocessing | Multi-pass ASR (Whisper + alternatives) → `ProcessedTransmissionPacket` |
| TRM | Thread routing + event correlation on `ProcessedTransmissionPacket` objects |
| Analysis | Incident summaries, timeline UI, daily reports |

See `docs/pipeline/architecture.md` for the full radio pipeline architecture and database design.

---

## Adding a New Implementation

To build a new Albatross implementation:

1. Identify your data stream
2. Define how it segments into Packets — what does a discrete unit look like in your domain?
3. Define your Preprocessing step — what does a Packet need to become a `ProcessedPacket`? For text-based domains this may be trivial. For audio or binary domains it may be substantial.
4. Configure the TRM for your domain — what do your metadata fields mean? What are the threading and event signals?
5. Define your Analysis layer — what do you want to do with threads and events once they exist?
6. Build a golden dataset — Tier 1 scenarios are always plain-language, domain-agnostic. Tiers 2–4 are domain-specific.

The Tier 1 golden dataset scenarios from the radio implementation are valid baselines for any new implementation. If the TRM can't handle plain-language threading and event correlation, domain-specific tuning won't fix it.

---

## Build History

Albatross is built in phases. Each phase has its own document.

| Phase | Description | Status | Document |
|-------|-------------|--------|----------|
| **Phase 1** | TRM core — async packet pipeline, LLM-backed router, four Tier 1 scenarios | Complete | `docs/trm/spec.md`, `docs/trm/runtime_loop.md` |
| **Phase 2** | Web UI + API — FastAPI backend, WebSocket streaming, Next.js dashboard | Complete | `docs/web/api.md` |
| **Phase 3** | Database + inter-module data pipeline — shared DB, contracts layer, mock pipeline, UI hydration | Complete | `docs/pipeline/database.md` |
| **Phase 4** | UI — live mode, scorer, tuning workflow, prompt editor | Not started | — |
| **Phase 5** | Data integration — real capture, ASR, radio hardware | Not started (hardware-gated) | — |