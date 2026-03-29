# TRM Runtime Loop

*How the Thread Routing Module processes packets, manages state, and makes decisions.*

---

## Overview

The TRM is a stateful, LLM-backed runtime. It processes one packet at a time, maintaining a live context that evolves as packets arrive. The LLM is not a stateless classifier — it is the context manager. It holds the full state of the session, updates it on every turn, and reasons about each new packet against everything it already knows.

---

## Implementation

The runtime is implemented across two files:

- `src/models/router.py` — data models: `Thread`, `Event`, `RoutingRecord`, `TRMContext`, `ThreadDecision`, `EventDecision`
- `src/pipeline/router.py` — `TRMRouter`: the stateful runtime, system prompt, LLM call, state update logic

The pipeline is async. The router consumes `ReadyPacket` objects from a `PacketQueue` one at a time. Each packet triggers a full LLM call with the current session context. The router updates its state from the response and emits a `RoutingRecord`.

---

## The Context

At any point in time, the TRM holds the following state in a `TRMContext` object:

```python
class TRMContext(BaseModel):
    active_threads: list[Thread] = []
    active_events: list[Event] = []
    packets_to_resolve: list[ReadyPacket] = []
    buffers_remaining: int = 5
    incoming_packet: ReadyPacket | None = None
```

This object is serialized to JSON and passed to the LLM in full on every turn. It is the single source of truth for the current state of the session.

### Active Threads

Each open thread contains:

```python
class Thread(BaseModel):
    thread_id: str
    label: str
    packets: list[ReadyPacket] = []
    event_ids: list[str] = []
    status: str = "open"
```

The `packets` list is ordered by arrival. The `label` is LLM-maintained — a running summary of the conversation that the LLM updates as context grows.

### Active Events

Each open event contains:

```python
class Event(BaseModel):
    event_id: str
    label: str
    opened_at: str       # packet_id of the packet that opened this event
    thread_ids: list[str] = []
    status: str = "open"
```

### Packets to Resolve

Buffered packets awaiting assignment. Each retains its original timestamp so that when eventually assigned, ordering within its thread remains correct.

### Buffers Remaining

A session-level counter. Decrements by one each time the LLM chooses to buffer a packet. When it reaches zero, buffering is no longer available. The starting value is configurable at router instantiation:

```python
router = TRMRouter(buffers=5)
```

---

## The Loop

Every time a new packet arrives:

```
1. ReadyPacket dequeued from PacketQueue
        │
        ▼
2. TRMContext updated with incoming_packet
        │
        ▼
3. TRMContext serialized to JSON and sent to LLM
   with full session state:
   - active_threads (with all packets)
   - active_events (with thread tags)
   - packets_to_resolve (buffered)
   - buffers_remaining
   - incoming_packet
        │
        ▼
4. LLM returns structured JSON routing decision
        │
        ▼
5. RoutingRecord parsed from response
        │
        ▼
6. State updated:
   - packet appended to its thread (or buffered)
   - new thread or event opened if needed
   - event tagged to thread if needed
   - buffers_remaining decremented if buffered
        │
        ▼
7. RoutingRecord appended to session log
        │
        ▼
8. Wait for next packet
```

In code, each packet goes through `TRMRouter.route()`:

```python
async def route(self, packet: ReadyPacket) -> RoutingRecord:
    self.context.incoming_packet = packet

    response = self.client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": json.dumps(self.context.model_dump(mode="json"), indent=2)
        }]
    )

    data = json.loads(response.content[0].text)
    record = self._parse_record(data)
    self._apply(packet, record, data)
    self.routing_records.append(record)
    return record
```

---

## Decisions

### Thread Decisions

| Decision | Meaning |
|----------|---------|
| `new` | Open a new thread and assign this packet to it |
| `existing` | Assign this packet to an already-open thread |
| `buffer` | Hold this packet in `packets_to_resolve` — costs one buffer |
| `unknown` | Cannot be classified — packet is logged but not assigned |

`buffer` is only available when `buffers_remaining > 0`. If the LLM attempts to buffer when the counter is at zero, the decision falls back to `unknown`.

### Event Decisions

| Decision | Meaning |
|----------|---------|
| `new` | Open a new event and tag it to the current thread |
| `existing` | Tag this packet's thread to an already-open event |
| `none` | No real-world event associated with this packet |
| `unknown` | Cannot be classified |

Thread and event decisions are always made independently. A packet can join an existing thread while that thread is simultaneously being linked to a new event.

---

## Buffering

Buffering exists to handle genuinely ambiguous packets — cases where the LLM cannot confidently assign a packet because not enough context has arrived yet.

1. LLM decides to buffer an incoming packet
2. Packet moves to `packets_to_resolve`
3. `buffers_remaining` decrements by one
4. On subsequent turns, the LLM sees the buffered packet alongside the new incoming packet and may choose to resolve it
5. When resolved, the packet is inserted into its assigned thread at its original timestamp

When `buffers_remaining` reaches zero, no further buffering is allowed. Any unresolved packets still in `packets_to_resolve` must be assigned or marked `unknown`.

---

## Output

The TRM emits a `RoutingRecord` after each packet is processed:

```python
class RoutingRecord(BaseModel):
    packet_id: str
    thread_decision: ThreadDecision
    thread_id: str | None = None
    event_decision: EventDecision
    event_id: str | None = None
```

Which serializes to:

```json
{
  "packet_id": "pkt_005",
  "thread_decision": "existing",
  "thread_id": "thread_A",
  "event_decision": "new",
  "event_id": "event_A"
}
```

`thread_id` and `event_id` are only present when the decision is `new` or `existing`. The full session output is the ordered list of routing records accumulated in `router.routing_records`.

---

## Context Schema

The full object sent to the LLM on each turn, as serialized JSON:

```json
{
  "active_threads": [
    {
      "thread_id": "thread_A",
      "label": "Bob and Dylan discussing the timesheet policy",
      "packets": [
        { "id": "pkt_001", "timestamp": "...", "text": "...", "metadata": { "speaker": "bob" } },
        { "id": "pkt_003", "timestamp": "...", "text": "...", "metadata": { "speaker": "dylan" } }
      ],
      "event_ids": ["event_A"],
      "status": "open"
    }
  ],
  "active_events": [
    {
      "event_id": "event_A",
      "label": "New timesheet policy rollout",
      "opened_at": "pkt_005",
      "thread_ids": ["thread_A"],
      "status": "open"
    }
  ],
  "packets_to_resolve": [],
  "buffers_remaining": 5,
  "incoming_packet": {
    "id": "pkt_007",
    "timestamp": "...",
    "text": "Oh I saw it. You have to log in fifteen minute increments now?",
    "metadata": { "speaker": "dylan" }
  }
}
```

---

## Open Problems

### Thread correction

The current loop is append-only. Once a packet is assigned to a thread, that decision is final — the only escape hatch is buffering before commitment. There is no mechanism for the LLM to correct a routing decision it made on a previous turn.

The anticipated failure modes, in order of likelihood:

- **Retroactive reassignment** — a packet assigned to thread A turns out to belong to thread B once more context arrives
- **Thread merging** — two threads the LLM opened separately turn out to be the same conversation
- **Thread splitting** — a thread contains two conversations that got tangled early on

None of these are handled yet. The right correction mechanic should be designed against real observed failure modes from scored scenarios rather than anticipated ones. This is deferred until the scorer is built and the Tier 1 scenarios have been run enough times to surface the actual patterns.

---

## What the LLM Does Not Do

- It does not have memory between sessions — context is always passed in full
- It does not have access to closed threads or events unless explicitly re-surfaced
- It does not produce freeform prose as part of the routing contract — output is always structured JSON
- It does not make decisions about what happens downstream of the routing output