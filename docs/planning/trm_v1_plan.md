# TRM v1 — Build Plan

*Minimal viable Thread Routing Module built against the Tier 1 golden dataset.*

---

## Goal

Build the simplest possible TRM that correctly threads and correlates events from plain-language input. No domain complexity. No radio metadata. No ASR. The goal is to validate the core routing logic against a known-good dataset before any domain-specific concerns enter the picture.

---

## Scope

**In scope:**
- Tier 1 golden dataset creation
- TRM core routing logic (thread + event decisions)
- Scoring against `expected_output.json`
- `ReadyPacket` queue implementation

**Out of scope:**
- Radio metadata or domain-specific signal weighting
- ASR or any preprocessing beyond trivial packet promotion
- Tier 2–4 scenarios
- UI, storage, or any Analysis layer

---

## Packet Types in v1

v1 introduces one concrete type: `ReadyPacket`.

### ProcessedPacket (contract — unchanged from spec)

```json
{
  "id": "uuid",
  "timestamp": "ISO8601",
  "text": "processed text content",
  "metadata": {}
}
```

### ReadyPacket (runtime concept)

A `ReadyPacket` is a `ProcessedPacket` that has been dequeued and handed to the TRM for routing. The schema is identical — `ReadyPacket` is not a structural subtype, it's a positional state. A `ProcessedPacket` becomes a `ReadyPacket` when it enters the TRM queue.

In v1, since input is already plain text, `ProcessedPacket` creation is trivial — the source data is loaded directly into the schema with no transformation. The queue boundary is still honored so the pattern holds for future implementations where preprocessing is non-trivial.

```
Source text → ProcessedPacket → [queue] → ReadyPacket → TRM
```

---

## Tier 1 Golden Dataset

Three scenarios. Each isolates one core TRM behavior. All use plain language, named speakers, and minimal metadata (speaker ID and timestamp only).

### Scenario 01 — Simple Two-Party

**What it tests:** Baseline. One thread, one event, no ambiguity.

Two speakers discuss a single topic start to finish. The TRM should open one thread, open one event, and assign every message to both without hesitation.

### Scenario 02 — Interleaved Conversations

**What it tests:** Thread separation. The TRM's primary challenge — two unrelated conversations happening in the same stream.

Four speakers, two pairs. Each pair is having a completely unrelated conversation. Messages are interleaved by timestamp. The TRM must correctly separate them into two threads and two events with zero cross-contamination.

### Scenario 03 — Thread with No Event, Then Event Opens

**What it tests:** Layer independence. Thread and event decisions are made independently — a thread can exist before any event is associated with it.

Two speakers start with small talk (thread opens, no event). Mid-conversation, the topic shifts to coordinating a real-world action. The TRM must recognize the moment the event opens without closing or splitting the thread.

---

## File Structure

```
/datasets/
  /tier1_plain_conversation/
    /scenario_01_simple_two_party/
      packets.json           # Input ReadyPackets
      expected_output.json   # Ground truth
      README.md              # Human description
    /scenario_02_interleaved/
      packets.json
      expected_output.json
      README.md
    /scenario_03_event_opens_mid_thread/
      packets.json
      expected_output.json
      README.md
```

---

## TRM v1 Architecture

```
packets.json
    │
    ▼
PacketLoader        # Reads packets.json, emits ProcessedPackets
    │
    ▼
PacketQueue         # Buffers ProcessedPackets
    │
    ▼
ReadyPacket         # Dequeued, passed to router
    │
    ▼
TRMRouter           # Core logic — makes thread + event decisions
    │
    ▼
RoutingOutput       # Structured JSON — threads, events, routing decisions
    │
    ▼
Scorer              # Compares RoutingOutput against expected_output.json
```

### TRMRouter

The router receives one `ReadyPacket` at a time and produces two decisions:

**Thread decision:** `new` / `existing` / `unknown`
**Event decision:** `new` / `existing` / `none` / `unknown`

In v1 the router is LLM-backed. It maintains a running context of open threads and events and reasons about each new `ReadyPacket` against that context. Domain-specific behavior is not yet needed — the system prompt describes generic conversational threading and event correlation logic only.

State passed to the LLM on each call:
- Currently open threads (ID + label + last few messages)
- Currently open events (ID + label + associated thread IDs)
- The incoming `ReadyPacket`

Output is always structured JSON. No freeform prose in the routing contract.

---

## Scoring

For each scenario, `RoutingOutput` is compared against `expected_output.json` and the following are computed:

| Metric | Description |
|--------|-------------|
| Thread classification accuracy | Correct `new` / `existing` / `unknown` per packet |
| Event classification accuracy | Correct `new` / `existing` / `none` / `unknown` per packet |
| Thread grouping accuracy | Right packets in the right threads |
| Event grouping accuracy | Right threads linked to the right events |
| Thread-event decoupling accuracy | Correct handling where thread and event decisions diverge |

A composite score is computed as a weighted average. All five metrics are weighted equally in v1 — weights can be tuned in later iterations.

---

## Success Criteria

v1 is considered passing when:

- All three Tier 1 scenarios score above **90% composite**
- Scenario 02 (interleaved) produces zero cross-contamination between threads
- Scenario 03 correctly identifies the packet at which the event opens

Passing v1 is the gate for introducing Tier 2 (radio domain) scenarios and domain-specific metadata configuration.

---

## Build Order

1. Write the three Tier 1 scenario files (`packets.json` + `expected_output.json` + `README.md`)
2. Build `PacketLoader` and `PacketQueue`
3. Build `TRMRouter` with a minimal system prompt
4. Build `RoutingOutput` schema and serialization
5. Build `Scorer`
6. Run against all three scenarios, iterate on system prompt until passing
7. Lock the dataset — scenarios are frozen once the TRM passes

---

## What v1 Explicitly Does Not Solve

- Metadata signal weighting — no domain metadata in Tier 1
- Cold re-entry / inactivity timeouts — no silence gaps in Tier 1 scenarios
- Multi-department or multi-channel separation — radio concerns, Tier 2+
- Confidence scoring — decisions are binary in v1, confidence is a future addition