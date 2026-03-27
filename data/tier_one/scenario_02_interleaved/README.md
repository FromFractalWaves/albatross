# Scenario 02 — Interleaved Conversations

## What's happening

Two completely unrelated conversations happening simultaneously, interleaved by timestamp.

**Thread A — Bob and Dylan** greet each other by name, then complain about the new timesheet policy and the HR enforcement around it.

**Thread B — Sam and Jose** exchange anonymous "hey" greetings with no names, then talk about lemon pie and plans for a lemon blueberry pound cake.

## What this tests

**Primary:** Thread separation under interleaving. The TRM must correctly assign each packet to its conversation with zero cross-contamination.

**Secondary stress:** pkt_002 and pkt_004 are both just "hey" with no speaker names mentioned. The TRM cannot rely on any named reference to separate these early packets — it has to hold them as a nascent thread and confirm the separation once Sam and Jose diverge into dessert territory.

## Key decisions to watch

- pkt_001 and pkt_003 — Bob and Dylan use each other's names. Thread A should be unambiguous from the start.
- pkt_002 and pkt_004 — just "hey". The TRM should open thread_B but the separation from thread_A rests entirely on the absence of names and the different speakers.
- pkt_005 onward — topics are completely unrelated. No vocabulary overlap between timesheet complaints and lemon desserts. Clean separation should be easy once topics emerge.
- Events open at pkt_005 (timesheet policy) and pkt_006 (lemon pie).
- Greetings (pkt_001–004) are thread-only, event_decision = none.

## Failure modes to watch for

- Any packet from thread_B bleeding into thread_A or vice versa (cross-contamination)
- pkt_002 or pkt_004 being incorrectly merged with thread_A due to temporal proximity to pkt_001/003