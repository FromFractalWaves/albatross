# Scenario 04 — Three-Way Split

## What's happening

A three-person group conversation where one participant introduces an unrelated topic, creating a second thread that interleaves with the original.

**Thread A — Vince, Rachel, and Deon** are planning a client demo for Thursday. They discuss leading with the dashboard, freezing the schema, prepping a slide deck, and deciding to leave out the flaky export feature.

**Thread B — Deon** raises a separate issue: the staging server is returning 502 errors. He investigates, finds the disk is full from logs, clears it, and reports the services are coming back up.

Vince bridges the two threads in pkt_010 ("make sure it's stable, we'll need staging for the demo dry run") — but this packet belongs to thread_A because Vince is giving a demo-planning directive, not troubleshooting the server.

## What this tests

**Primary:** Thread forking within a shared group. Three people are in one conversation. One participant (Deon) introduces a completely separate topic. The TRM must open a second thread for the staging issue without pulling other demo-planning packets into it.

**Secondary:** Speaker overlap across threads. Deon participates in both threads. Vince responds to the staging issue in the context of the demo. The TRM can't use speaker identity alone to separate threads — it has to read the content.

## Key decisions to watch

- pkt_006 — Deon explicitly flags "unrelated" and raises the staging 502s. This opens thread_B and event_B.
- pkt_007 — Rachel addresses Vince about the export feature. This is demo planning (thread_A), not staging troubleshooting, even though it follows pkt_006 immediately.
- pkt_009 — Deon reports on the disk issue. Back to thread_B.
- pkt_010 — Vince says "make sure it's stable, we'll need staging for the demo dry run." This references the staging server but the directive is about the demo. This belongs to thread_A.
- pkt_011 — Deon confirms disk is cleared and services are recovering. Thread_B.
- pkt_012 — Vince asks Rachel to send the deck draft. Pure demo planning, thread_A.

## Failure modes to watch for

- Merging all packets into one thread because all three speakers are in the same "group." The staging issue is explicitly flagged as unrelated.
- Putting pkt_010 in thread_B because it mentions staging. The intent is demo planning — Vince is telling Deon to make sure staging works *for the demo*.
- Missing the thread_B fork at pkt_006. Deon's "hey unrelated" is a clear conversational break signal.
- Failing to return to thread_A at pkt_007 after the fork. Rachel is addressing Vince about the export feature, not responding to Deon's staging issue.
