# Scenario 01 — Simple Two-Party Conversation

## What's happening

A single conversation between Li and Marcus. They start by troubleshooting a broken build caused by a bad deploy to the token refresh endpoint, then the conversation drifts into small talk about a team lunch on Friday.

**Thread A — Li and Marcus** discuss the broken build, identify the cause (Nina's token expiry change), coordinate a rollback, then shift to talking about Friday lunch plans.

## What this tests

**Primary:** Basic two-party threading. One thread, one event. The simplest possible scenario — can the TRM keep a single conversation together and correctly identify the event?

**Secondary:** Thread-event decoupling at the tail end. The conversation continues past the event (pkt_007–010 are about lunch, not the build). The thread stays open but the event decision should flip to `none` once the topic shifts.

## Key decisions to watch

- pkt_001 — Opens both the thread and the event. The broken build is introduced immediately.
- pkt_006 — Last packet directly about the build incident.
- pkt_007 — Topic pivot to Friday lunch. Thread continues, but event_decision should be `none` from here on.
- pkt_010 — Marcus references the rollback ("let me know if the rollback fixes things") but the primary topic is lunch confirmation. Event decision stays `none` — the mention is a callback, not active coordination on the event.

## Failure modes to watch for

- Splitting the conversation into two threads at the topic change (pkt_007). This is one continuous conversation between the same two people.
- Opening a second event for the lunch plans. Lunch plans are casual chatter, not a trackable event.
- Keeping event_decision as `existing` for pkt_007–010 because of Marcus's passing reference to the rollback in pkt_010.
