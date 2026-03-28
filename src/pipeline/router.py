import json
import logging
import anthropic

from src.models.packets import ReadyPacket
from src.models.router import (
    Thread,
    Event,
    RoutingRecord,
    TRMContext,
    ThreadDecision,
    EventDecision,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are the Thread Routing Module (TRM) — a stateful intelligence layer that processes a stream of messages one at a time.

Your job is to make two independent decisions for every incoming packet:

1. THREAD DECISION — which conversation does this packet belong to?
2. EVENT DECISION — is there a real-world event associated with this packet?

---

## Definitions

A THREAD is a conversation — a group of messages between the same people about the same topic.
An EVENT is a real-world occurrence being discussed. Not all conversations have events.

These are independent. A thread can exist with no event (small talk, greetings).
An event can span multiple threads. A thread can outlast its event.

---

## Thread decisions

- "new" — this packet starts a new conversation. Open a new thread and assign this packet to it.
- "existing" — this packet belongs to an already-open thread. Include the thread_id.
- "buffer" — you genuinely cannot tell yet. Hold the packet for later. Costs one buffer.
- "unknown" — cannot be classified at all.

Only use "buffer" when you truly need more context. Buffers are limited.

---

## Event decisions

- "new" — this packet introduces a real-world event. Open a new event and tag it to the thread.
- "existing" — this packet's thread relates to an already-open event. Include the event_id.
- "none" — no real-world event here (greetings, small talk, admin chatter).
- "unknown" — cannot be classified.

---

## Thread and event labels

When you open a new thread or event, give it a short descriptive label.
Maintain and update labels as context grows — they are your running summary.

---

## Output format

You must respond with a single JSON object. No prose, no explanation, no markdown.

For a simple routing decision:
{
  "packet_id": "pkt_001",
  "thread_decision": "new",
  "thread_id": "thread_A",
  "thread_label": "Alice and Bob discussing the server issue",
  "event_decision": "none",
  "event_id": null,
  "event_label": null
}

Rules:
- thread_id is required when thread_decision is "new" or "existing". Generate a short id like "thread_A", "thread_B" etc for new threads.
- event_id is required when event_decision is "new" or "existing". Generate a short id like "event_A", "event_B" etc for new events.
- thread_label is required when thread_decision is "new". Optional but encouraged when "existing" if the label should be updated.
- event_label is required when event_decision is "new". Optional but encouraged when "existing" if the label should be updated.
- All other fields are null when not applicable.
""".strip()


class TRMRouter:
    def __init__(self, buffers: int = 5):
        self.client = anthropic.Anthropic()
        self.context = TRMContext(buffers_remaining=buffers)
        self.routing_records: list[RoutingRecord] = []

    async def route(self, packet: ReadyPacket) -> RoutingRecord:
        self.context.incoming_packet = packet

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(self.context.model_dump(mode="json"), indent=2)
                }
            ]
        )

        raw = response.content[0].text
        logger.debug(f"LLM response for {packet.id}: {raw}")

        data = json.loads(raw)
        record = self._parse_record(data)
        self._apply(packet, record, data)

        self.routing_records.append(record)
        logger.info(f"{packet.id} → thread={record.thread_decision.value}:{record.thread_id} event={record.event_decision.value}:{record.event_id}")

        return record

    def _parse_record(self, data: dict) -> RoutingRecord:
        return RoutingRecord(
            packet_id=data["packet_id"],
            thread_decision=ThreadDecision(data["thread_decision"]),
            thread_id=data.get("thread_id"),
            event_decision=EventDecision(data["event_decision"]),
            event_id=data.get("event_id"),
        )

    def _apply(self, packet: ReadyPacket, record: RoutingRecord, data: dict) -> None:
        if record.thread_decision == ThreadDecision.NEW:
            thread = Thread(
                thread_id=record.thread_id,
                label=data.get("thread_label", ""),
                packets=[packet],
            )
            self.context.active_threads.append(thread)

        elif record.thread_decision == ThreadDecision.EXISTING:
            thread = self._get_thread(record.thread_id)
            if thread:
                thread.packets.append(packet)
                if data.get("thread_label"):
                    thread.label = data["thread_label"]

        elif record.thread_decision == ThreadDecision.BUFFER:
            if self.context.buffers_remaining > 0:
                self.context.packets_to_resolve.append(packet)
                self.context.buffers_remaining -= 1
            else:
                logger.warning(f"Buffer exhausted — marking {packet.id} as unknown")

        if record.event_decision == EventDecision.NEW:
            event = Event(
                event_id=record.event_id,
                label=data.get("event_label", ""),
                opened_at=packet.id,
                thread_ids=[record.thread_id] if record.thread_id else [],
            )
            self.context.active_events.append(event)
            thread = self._get_thread(record.thread_id)
            if thread and record.event_id not in thread.event_ids:
                thread.event_ids.append(record.event_id)

        elif record.event_decision == EventDecision.EXISTING:
            event = self._get_event(record.event_id)
            if event and record.thread_id and record.thread_id not in event.thread_ids:
                event.thread_ids.append(record.thread_id)
            if event and data.get("event_label"):
                event.label = data["event_label"]

    def _get_thread(self, thread_id: str | None) -> Thread | None:
        if not thread_id:
            return None
        return next((t for t in self.context.active_threads if t.thread_id == thread_id), None)

    def _get_event(self, event_id: str | None) -> Event | None:
        if not event_id:
            return None
        return next((e for e in self.context.active_events if e.event_id == event_id), None)