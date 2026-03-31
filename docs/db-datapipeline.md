# DB & Data Pipeline — Implementation Specs

*Detailed implementation specs for Albatross Phase 3. High-level plan lives in `docs/albatross_phase_3.md`.*

---

## Sub-phase 3.2 — Synthetic Live Data & Mock Pipeline

### Source Dataset

Base: `data/tier_one/scenario_02_interleaved/packets.json`

This scenario has 12 packets across two interleaved conversations — enough to produce two threads and at least one event, which exercises the full routing surface. The text content stays unchanged. Radio metadata is added to each packet.

### Augmented Packet Shape

Each packet in the augmented dataset gets a `metadata` block that mirrors what real capture would produce:

```json
{
  "id": "uuid-here",
  "timestamp": "2024-01-15T14:23:01Z",
  "text": "Hey, did you get the memo about the new shift schedule?",
  "metadata": {
    "talkgroup_id": 1001,
    "source_unit": 4021,
    "frequency": 851.0125,
    "duration": 3.2,
    "encryption_status": false,
    "audio_path": "out/wav/mock_001.wav"
  }
}
```

Use two talkgroup IDs to reflect the two interleaved conversations — e.g. TGID `1001` for thread A speakers, TGID `1002` for thread B speakers. This gives the TRM a real metadata signal to work with alongside the text.

Augmented dataset lives at: `data/tier_one/scenario_02_interleaved/packets_radio.json`

The original `packets.json` is untouched. The augmented file is the mock pipeline's input.

---

### Simulation Parameters

| Parameter | Value |
|-----------|-------|
| Packet arrival interval | 10 seconds |
| Mock ASR delay | 10 seconds |
| Loop | No — run through dataset once and stop |

**What this means in practice:** With 12 packets at 10 second intervals, the full capture phase takes ~2 minutes. Each packet then waits 10 seconds in preprocessing before the TRM picks it up. The TRM processes packets sequentially as they become available. Total wall time from first capture to last routed packet: roughly 4 minutes.

This is slow enough to watch the pipeline progress in real time in the UI without being painful to sit through during development.

---

### Mock Capture Script

Location: `capture/mock/run.py`

**Behavior:**
1. Reads `packets_radio.json`
2. For each packet, writes a row to `transmissions` with `status = 'captured'`
   - All capture fields populated from the packet metadata
   - `text` field left null — preprocessing hasn't run yet
3. Waits 10 seconds
4. Moves to the next packet
5. Exits after the last packet

**Invocation:**
```bash
python capture/mock/run.py
```

---

### Mock Preprocessing Script

Location: `preprocessing/mock/run.py`

**Behavior:**
1. Polls `transmissions` for rows with `status = 'captured'` every 2 seconds
2. On finding one, flips status to `'processing'` immediately (prevents double-pickup)
3. Waits 10 seconds (simulated ASR time)
4. Writes `text` from the source packet into the `transmissions` row
5. Writes mock ASR metadata: `asr_model = 'mock'`, `asr_confidence = 1.0`, `asr_passes = 1`
6. Flips status to `'processed'`
7. Continues polling until no `captured` or `processing` records remain, then exits

**Invocation:**
```bash
python preprocessing/mock/run.py
```

Both scripts are designed to run concurrently in separate terminals — capture is writing, preprocessing is picking up behind it.

---

### DB Reset

A clean reset truncates all data tables without touching the schema. Foreign key order matters.

Location: `db/reset.py`

**Truncation order:**
1. `routing_records`
2. `thread_events`
3. `transmissions`
4. `threads`
5. `events`

**Invocation:**
```bash
python db/reset.py
```

Prints a confirmation before truncating. Does not drop or recreate any tables. Safe to run between simulation runs during development.

---

### Running a Full Simulation

```bash
# 1. Reset the database
python db/reset.py

# 2. Start mock preprocessing (leave running)
python preprocessing/mock/run.py &

# 3. Start mock capture (leave running)
python capture/mock/run.py &

# 4. Start TRM in DB-driven mode (leave running)
python src/main_live.py

# 5. Open the web UI
# http://localhost:3000
```

Watch packets appear in the UI every ~20 seconds (10s capture interval + 10s ASR delay). The TRM routes each one as it becomes available. The UI updates live via WebSocket and hydrates correctly on refresh.