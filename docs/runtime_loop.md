# TRM Runtime Loop

*How the Thread Routing Module processes packets, manages state, and makes decisions.*

---

## Overview

The TRM is a stateful, LLM-backed runtime. It does not process packets in batch — it processes one packet at a time, maintaining a live context that evolves as packets arrive. The LLM is not just a classifier; it is the context manager. It holds the state, updates it, and reasons about each new packet against everything it already knows.

---

## The Context

At any point in time, the TRM holds the following state:

```
active_threads:       all currently open threads, each containing their packets in order
active_events:        all currently open events, each tagged to one or more threads
packets_to_resolve:   buffered packets awaiting assignment
buffers_remaining:    integer — how many more packets can be buffered
```

This context is passed to the LLM in full on every turn. It is the single source of truth for the current state of the session.

### Active Threads

Each open thread contains:
- A unique thread ID
- A label (LLM-maintained summary of the conversation)
- The ordered list of packets assigned to it
- Any events currently tagged to it

### Active Events

Each open event contains:
- A unique event ID
- A label (LLM-maintained summary of the real-world occurrence)
- The thread(s) it is tagged to
- The packet at which it was opened (`opened_at`)

### Packets to Resolve

Buffered packets that have not yet been assigned to a thread. Each buffered packet retains its original timestamp so that when it is eventually assigned, ordering within the thread remains correct.

### Buffers Remaining

A session-level counter. Each time the LLM chooses to buffer a packet, this counter decrements by one. When it reaches zero, buffering is no longer available — the LLM must make a hard decision on every incoming packet.

The starting value is configurable. It does not reset during a session.

---

## The Loop

Every time a new packet arrives, the following happens:

```
1. New packet arrives
        │
        ▼
2. LLM receives full context:
   - active_threads (with packets)
   - active_events (with tags)
   - packets_to_resolve (buffered)
   - buffers_remaining
   - incoming packet
        │
        ▼
3. LLM produces decisions:
   - thread decision for incoming packet
   - event decision for incoming packet
   - optionally: resolve one or more buffered packets
   - optionally: close a thread or event
        │
        ▼
4. State updates:
   - incoming packet appended to its thread (or buffered)
   - event tag applied if needed
   - resolved buffered packets inserted at original timestamps
   - closed threads / events removed from active context
   - buffers_remaining decremented if packet was buffered
        │
        ▼
5. Wait for next packet
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

### Thread Closure

The LLM may close a thread at any point — typically when a conversation has clearly ended. Closed threads are removed from `active_threads` and are no longer available for routing. They are retained in the session log.

### Event Closure

The LLM may close an event when it determines the real-world occurrence has concluded or is no longer being discussed. Closed events are removed from `active_events`.

---

## Buffering

Buffering exists to handle genuinely ambiguous packets — cases where the LLM cannot confidently assign a packet to a thread because not enough context has arrived yet.

### How it works

1. LLM decides to buffer an incoming packet
2. Packet moves to `packets_to_resolve`
3. `buffers_remaining` decrements by one
4. On subsequent turns, the LLM sees the buffered packet alongside new incoming packets and may choose to resolve it
5. When resolved, the packet is inserted into its assigned thread at its original timestamp

### Resolution

A buffered packet is resolved when the LLM assigns it to a thread (or opens a new one for it). Resolution can happen at any subsequent turn — the LLM may resolve buffered packets opportunistically as new context clarifies their meaning.

### Buffer exhaustion

When `buffers_remaining` reaches zero, no further buffering is allowed. Any packet the LLM cannot confidently assign must be marked `unknown`. Unresolved packets still in `packets_to_resolve` when the counter hits zero are force-resolved: the LLM makes a best-guess assignment or marks them `unknown`.

### Starting value

The starting value for `buffers_remaining` is configurable per deployment. The right value depends on the expected ambiguity of the domain and the typical gap between an ambiguous packet and the context that resolves it. This should be tuned against real data.

---

## Output

The TRM emits a routing record after each packet is processed. The full session output is the accumulation of these records.

Each routing record contains:

```json
{
  "packet_id": "pkt_004",
  "thread_decision": "existing",
  "thread_id": "thread_A",
  "event_decision": "new",
  "event_id": "event_A"
}
```

For buffered packets, the routing record is emitted at resolution time, not arrival time, but carries the original packet timestamp.

The full session state — threads with their packets, events with their tags — is always reconstructable from the ordered sequence of routing records.

---

## Context Schema

The full context passed to the LLM on each turn:

```json
{
  "active_threads": [
    {
      "thread_id": "thread_A",
      "label": "Alice and Bob morning check-in",
      "packets": [
        { "id": "pkt_001", "timestamp": "...", "text": "...", "metadata": {} },
        { "id": "pkt_002", "timestamp": "...", "text": "...", "metadata": {} }
      ],
      "events": ["event_A"]
    }
  ],
  "active_events": [
    {
      "event_id": "event_A",
      "label": "Warehouse fire on Meridian",
      "opened_at": "pkt_004",
      "thread_ids": ["thread_A"]
    }
  ],
  "packets_to_resolve": [
    { "id": "pkt_007", "timestamp": "...", "text": "...", "metadata": {} }
  ],
  "buffers_remaining": 3,
  "incoming_packet": {
    "id": "pkt_008",
    "timestamp": "...",
    "text": "...",
    "metadata": {}
  }
}
```

---

## What the LLM Does Not Do

- It does not have memory between sessions — context is always passed in full
- It does not have access to closed threads or events unless they are explicitly re-surfaced
- It does not produce freeform prose as part of the routing contract — output is always structured JSON
- It does not make decisions about what happens downstream of the routing output