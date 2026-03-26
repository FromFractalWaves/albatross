
Example scenarios:

- Two people discussing a problem, interleaved with two other people having a completely unrelated conversation — two threads, two events, zero cross-contamination
- A conversation that starts as small talk (thread with no event) and then pivots to coordinating a response to something (thread now linked to an event)
- A three-way conversation where two people are discussing one thing and a third party introduces a separate topic — one thread forks or a new thread opens, producing two distinct events


Three scenario directories to write, in order:

scenario_01_simple_two_party — baseline, one thread, one event
scenario_02_interleaved — two unrelated conversations in the same stream
scenario_03_event_opens_mid_thread — small talk that pivots to a real-world coordination

data model:

  
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
