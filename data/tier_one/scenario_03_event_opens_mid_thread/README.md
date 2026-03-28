# Scenario 03 — Event Opens Mid-Thread

## What's happening

A single conversation between Tom and Priya that starts as casual small talk and then pivots to discussing a real-world event.

**Thread A — Tom and Priya** start with weekend chit-chat (how was your weekend, watched movies, stayed in). At pkt_004, Priya introduces the water main break on Elm Street. The conversation shifts entirely to discussing the break, the flooding, the city repair crew, and Tom's cousin who lives on the affected block.

## What this tests

**Primary:** Mid-thread event emergence. The thread exists before any event does. The TRM must correctly produce `event_decision: none` for the opening small talk, then `event_decision: new` when the water main break is introduced, without splitting the thread.

**Secondary:** The conversation is continuous between the same two people — there is no reason to open a second thread. The event opens inside an already-running thread.

## Key decisions to watch

- pkt_001–003 — Pure small talk. Thread opens, no event. All three should be `event_decision: none`.
- pkt_004 — The pivot. Priya mentions the water main break. This is `event_decision: new`. The thread decision is `existing` — the conversation doesn't restart, it shifts topic.
- pkt_005–010 — All about the water main break. `event_decision: existing` for every one.

## Failure modes to watch for

- Opening the event at pkt_001 (premature — nothing event-worthy has been said yet).
- Splitting the thread at pkt_004 (new topic doesn't mean new thread — same speakers, continuous conversation).
- Treating pkt_004 as `event_decision: none` because the question "did you hear about..." is phrased as a question rather than a statement of fact. The event is the water main break, not the question — and pkt_004 is where it enters the conversation.
