# Thread Routing Module — Spec

## What Is the Thread Routing Module?

The **Thread Routing Module (TRM)** is a domain-agnostic, reusable intelligence component that ingests a stream of `ProcessedPacket` objects and does two things simultaneously:

1. **Thread Routing** — classifies each packet into a conversation thread (who is talking to whom, in sequence)
2. **Event Correlation** — associates threads with real-world events (the thing being talked about)

These are two distinct layers. A thread is a communication pattern. An event is a real-world occurrence. The TRM maintains both.

It is not a radio module. It is not tied to any specific use case. It sits at the intelligence layer of any Albatross pipeline, consuming `ProcessedPacket` objects regardless of what domain produced them. The radio dispatch pipeline is one consumer. Others can be built by following the same pattern.

---

## Core Concepts

### The ProcessedPacket

The TRM ingests `ProcessedPacket` objects. A `ProcessedPacket` is the abstract Albatross type that any domain-specific Packet becomes after preprocessing — whatever that preprocessing requires for that domain.

For a text-based domain (e.g. a live social media feed), a Packet may already carry text in its payload, making preprocessing trivial or nonexistent. For an audio domain (e.g. radio), preprocessing is ASR — the Packet's audio payload is transcribed into text before the `ProcessedPacket` is emitted. Either way, the TRM receives the same thing.

Every `ProcessedPacket` conforms to this schema:

```json
{
  "id": "uuid",
  "timestamp": "ISO8601",
  "text": "processed text content",
  "metadata": {}
}
```

The `metadata` field carries domain-specific context forwarded from the upstream Packet — talk group IDs, source unit identifiers, department tags, or whatever signals are relevant to routing decisions in that domain. The TRM is told via configuration what those fields mean and how much weight to give them.

> **Note on naming:** In the radio pipeline, the upstream Packet type is `TransmissionPacket` (defined in the Phase 1A spec) and the TRM input type is `ProcessedTransmissionPacket` — the radio-specific instantiation of `ProcessedPacket`. These are out of scope for this document. The TRM only knows about `ProcessedPacket`.

### The ReadyPacket

A `ReadyPacket` is a `ProcessedPacket` that has been dequeued and handed to the TRM router. It is not a structural subtype — the schema is identical to `ProcessedPacket`. The name reflects a positional state in the pipeline: a `ProcessedPacket` sitting in the queue becomes a `ReadyPacket` the moment the TRM pulls it for routing.

```
ProcessedPacket → [queue] → ReadyPacket → TRM router
```

This boundary matters because preprocessing and routing are decoupled. Packets can accumulate in the queue while the router is busy, and the router always operates on one `ReadyPacket` at a time. For implementations where preprocessing is trivial, the queue may be nearly instantaneous — but the boundary is still honored so the pattern holds as implementations grow more complex.

### The Thread

A thread is a group of messages the TRM has determined belong to the same conversation. Threads have:

- A unique ID
- An open/closed status
- A summary (maintained by the LLM)
- Constraints (max duration, max silence gap, max message count, etc.)
- Zero or more associated events

### The Event

An event is a real-world occurrence that one or more threads are about. Events have:

- A unique ID
- An open/closed status
- A label/summary (maintained by the LLM)
- One or more associated threads

The relationship between threads and events is **many-to-many**:

- One event can have multiple threads (e.g. different talk groups coordinating on the same incident)
- One thread can reference multiple events (e.g. a unit clears one call and gets dispatched to another in the same conversation)
- A thread can exist with no event (routine chatter, administrative talk)
- An event can be inferred across threads even when no single thread contains the full picture

```
ReadyPacket ──belongs to──▶ Thread ──relates to──▶ Event
Thread ◀──has many── Event
```

### The Two-Layer Routing Decision

For every `ReadyPacket` the router receives, the TRM produces decisions at both layers:

**Thread layer:**

| Decision | Meaning |
|----------|---------|
| `existing` | Belongs to an already-open thread (includes thread ID) |
| `new` | Opens a new thread |
| `buffer` | Hold this packet in `packets_to_resolve` — costs one buffer |
| `unknown` | Cannot be confidently classified |

**Event layer:**

| Decision | Meaning |
|----------|---------|
| `existing` | Thread relates to an already-open event (includes event ID) |
| `new` | Opens a new event |
| `none` | Thread has no associated real-world event |
| `unknown` | Cannot be confidently classified |

These decisions are made independently. A `ReadyPacket` can join an existing thread while that thread is simultaneously being linked to a new event — for example, when a unit that was on routine patrol is suddenly dispatched to an incident mid-conversation.

---

## Why a Golden Dataset?

Before any model is run in production, we need a baseline — a fixed set of inputs where the correct outputs are already known. This allows us to:

- Benchmark models against each other objectively
- Measure the impact of prompt changes without guessing
- Catch regressions when logic is modified
- Compare modes of operation (e.g. aggressive vs. conservative threading)
- Onboard new use cases with a clear pattern to follow

The dataset is a permanent fixture of the repository, not a throwaway dev tool.

---

## Dataset Structure

### The Four Tiers

#### Tier 1 — Plain Conversation (Domain Agnostic)

**Purpose:** Establish a baseline for the core threading and event correlation logic with zero domain complexity.

Messages are plain natural language between named speakers. No codes, no jargon. Anyone can read the scenario and immediately know what the correct output should be. Metadata is minimal — just speaker identifiers and timestamps.

Events at this tier are simple and obvious — a topic being discussed, a problem being solved, a plan being made. The distinction between "thread" (the conversation) and "event" (the thing being discussed) should be immediately legible to a human reader.

> If the TRM cannot thread and correlate these correctly, nothing else matters.

Example scenarios:

- Two people discussing a problem, interleaved with two other people having a completely unrelated conversation — two threads, two events, zero cross-contamination
- A conversation that starts as small talk (thread with no event) and then pivots to coordinating a response to something (thread now linked to an event)
- A three-way conversation where two people are discussing one thing and a third party introduces a separate topic — one thread forks or a new thread opens, producing two distinct events

#### Tier 2 — Radio Domain (Semantics Matter)

**Purpose:** Test whether the TRM handles domain-specific language and richer metadata correctly.

Messages use realistic public safety communication patterns — unit designators, 10-codes, dispatch language. Talk group structure is introduced. Metadata carries TGID, unit IDs, department identifiers, timestamps.

Events at this tier are real-world incidents. The distinction between thread (the radio exchange) and event (the incident being responded to) is central to this tier.

Tests the interplay between text meaning and metadata signals.

Example scenarios:

- A traffic stop dispatched and acknowledged — one thread, one event (the stop)
- A multi-unit response to a single incident across two talk groups — two threads, one shared event
- A unit that clears a call and immediately gets dispatched to a new one — one continuous thread, two sequential events
- Routine chatter with no incident — thread present, no event

#### Tier 3 — Metadata Dominant

**Purpose:** Validate that the TRM can route correctly even when text is ambiguous or semantically sparse, relying primarily on metadata.

Text content may be identical or near-identical across messages from different threads and events. The metadata — specifically talk group ID, department, unit type — is what determines correct routing.

Example scenarios:

- Two units on different TGIDs saying nearly identical things about completely unrelated incidents — same text, different threads, different events
- A transmission whose text is unclear but whose TGID places it unambiguously in an existing thread and event
- A message that metadata alone can assign to an event even before the text is parsed

**Key insight this tier validates:** A TGID mismatch is nearly disqualifying for thread grouping ~90% of the time. However, shared event correlation can sometimes survive a TGID mismatch — e.g. two departments talking on separate channels about the same incident. The TRM must understand the difference between these two signals: TGID is a strong thread signal, but a weaker event signal.

#### Tier 4 — Adversarial / Edge Cases

**Purpose:** Stress-test failure modes and corner cases that real-world data will eventually produce.

Example scenarios:

- **Mutual aid:** Two units from different departments/TGIDs legitimately coordinating — separate threads correctly linked to the same event
- **Cold re-entry:** A unit goes silent for a long time then transmits again — does the thread re-open, does the event re-open, or do both start fresh?
- **Semantic trap:** Near-identical language used in two completely unrelated incidents — must not be merged into the same event
- **Thread-event decoupling:** A thread that transitions from one event to another mid-stream — the thread is continuous but the event changes
- **Ambiguous unit ID:** Same unit ID appearing in two different departments — metadata appears to match but context does not

---

## Dataset Directory Structure

```
/data/
  /tier_one/
    /scenario_01_simple_two_party/
      packets.json                       # Input ReadyPackets
      expected_output.json               # Ground truth threads, events, and decisions
      README.md                          # Human description of what's happening
    /scenario_02_interleaved/
      packets.json
      expected_output.json
      README.md
    /scenario_03_event_opens_mid_thread/
      packets.json
      expected_output.json
      README.md
    /scenario_04_three_way_split/
      packets.json
      expected_output.json
      README.md
  /tier_two/
    /scenario_01_traffic_stop/
      ...
  /tier_three/
    /scenario_01_tgid_separation/
      ...
  /tier_four/
    /scenario_01_mutual_aid_cross_tgid/
      ...
```

---

## Scenario File Format

### `packets.json`

Each entry is a `ReadyPacket` — a `ProcessedPacket` dequeued and ready for routing. In Tier 1 scenarios, metadata is minimal: just a speaker identifier. Tier 2+ scenarios populate metadata with domain-specific fields.
  
```json
[
  {
    "id": "pkt_001",
    "timestamp": "2024-01-15T14:00:00Z",
    "text": "Hey, did you sort out the issue with the server?",
    "metadata": {
      "speaker": "alice"
    }
  },
  {
    "id": "pkt_002",
    "timestamp": "2024-01-15T14:00:08Z",
    "text": "Yeah, it was a config problem. Fixed it this morning.",
    "metadata": {
      "speaker": "bob"
    }
  },
  {
    "id": "pkt_003",
    "timestamp": "2024-01-15T14:00:15Z",
    "text": "Are we still on for lunch at noon?",
    "metadata": {
      "speaker": "alice"
    }
  }
]
```

### `expected_output.json`

```json
{
  "threads": [
    {
      "thread_id": "thread_A",
      "label": "Alice and Bob discussing the server issue",
      "status": "open",
      "packet_ids": ["pkt_001", "pkt_002", "pkt_003"]
    }
  ],
  "events": [
    {
      "event_id": "event_A",
      "label": "Server config problem",
      "status": "open",
      "thread_ids": ["thread_A"]
    }
  ],
  "routing": [
    {
      "packet_id": "pkt_001",
      "thread_decision": "new",
      "thread_id": "thread_A",
      "event_decision": "new",
      "event_id": "event_A"
    },
    {
      "packet_id": "pkt_002",
      "thread_decision": "existing",
      "thread_id": "thread_A",
      "event_decision": "existing",
      "event_id": "event_A"
    },
    {
      "packet_id": "pkt_003",
      "thread_decision": "existing",
      "thread_id": "thread_A",
      "event_decision": "none"
    }
  ]
}
```

> Note how `pkt_003` joins the existing thread but produces an event decision of `none` — the conversation continues but the lunch question isn't a real-world event worth tracking. This illustrates that thread and event decisions are always made independently, and that threads routinely outlast the events they were opened around.

---

## Scoring Metrics

When a model's output is compared against `expected_output.json`, the following are computed:

### Thread-level metrics

| Metric | Description |
|--------|-------------|
| Thread accuracy | Were the right packets grouped into the right threads? |
| Thread boundary detection | Did threads open and close at the right packets? |
| False thread grouping rate | Unrelated packets incorrectly merged into one thread |
| Thread miss rate | Related packets incorrectly split across different threads |
| Thread classification accuracy | Correct `new` / `existing` / `unknown` decisions |

### Event-level metrics

| Metric | Description |
|--------|-------------|
| Event accuracy | Were the right threads linked to the right events? |
| Event boundary detection | Did events open and close at the right packets? |
| False event grouping rate | Unrelated threads incorrectly merged into one event |
| Event miss rate | Related threads incorrectly split across different events |
| Event classification accuracy | Correct `new` / `existing` / `none` / `unknown` decisions |

### Cross-cutting metrics

| Metric | Description |
|--------|-------------|
| Metadata sensitivity | Score delta when metadata is stripped vs. included (measures reliance on metadata signals) |
| Overall composite score | Weighted combination of thread and event metrics |
| Thread-event decoupling accuracy | Correct handling of messages where thread and event decisions diverge |

---

## Adding a New Use Case

To adapt the TRM to a new domain, follow this pattern:

1. Define how your domain's Packets are preprocessed into `ProcessedPacket` objects — or confirm that no preprocessing is needed
2. Define the metadata fields relevant to routing decisions in your domain
3. Define what constitutes a "thread" vs. an "event" in your domain
4. Write Tier 1 scenarios using the base `ProcessedPacket` schema (minimal metadata, plain language)
5. Write Tier 2–4 scenarios with your domain's metadata populated
6. Document what each metadata field means and its expected influence on thread and event routing
7. Run against the TRM and score against your ground truth
8. Tune the system prompt / config to reflect your domain's signal weights

The Tier 1 scenarios from the original dataset remain valid baselines across all use cases.

---

## Position in the Albatross Pipeline

The TRM occupies the intelligence layer of any Albatross pipeline. It sits between preprocessing and analysis, consuming `ProcessedPacket` objects via a queue and routing them as `ReadyPacket` objects.

```
Packet → [Preprocessing] → ProcessedPacket → [queue] → ReadyPacket → [TRM router] → Event store / Analysis
```

Preprocessing is domain-dependent. It may be heavy (radio: ASR to convert audio to text) or near-absent (text feeds: packet payload is already text). The queue decouples preprocessing from routing — packets accumulate while the router is busy, and the router always operates on one `ReadyPacket` at a time. For simple implementations the queue may be nearly instantaneous, but the boundary is always honored.

Everything upstream of the `ProcessedPacket` boundary is out of scope for the TRM. Everything downstream of the TRM's JSON output is out of scope for the TRM. The contracts at those two boundaries are the only interface points.

In the radio dispatch reference implementation specifically:

```
OP25 capture → TransmissionPacket → ASR → ProcessedTransmissionPacket → [queue] → ReadyPacket → [TRM router] → Event store → Web UI
```

See the Albatross spec and Phase 1A/1B documentation for the radio-specific types and pipeline details.