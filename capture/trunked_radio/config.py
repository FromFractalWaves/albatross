import os

# ZMQ ports (backend-side)
PCM_PORT = 5580
CONTROL_PORT = 5581
PACKET_PUSH_PORT = 5590

# Timeouts
INACTIVITY_TIMEOUT = 1.5  # seconds — close call after this much silence
SWEEP_INTERVAL = 0.5      # seconds — how often to check for timed-out calls
POLL_TIMEOUT = 10          # ms — ZMQ poller timeout

# WAV output
CAPTURE_WAV_DIR = os.environ.get("CAPTURE_WAV_DIR", "data/wav")

# Audio
SAMPLE_RATE = 8000

# Bridge-side ZMQ ports (flowgraph → bridge)
METADATA_PORT = 5557
PCM_BASE_PORT = 5560
NUM_LANES = 3  # reduced from 8 — CPU budget issue, see specs/radio_integration.md


def pcm_endpoint(lane_id: int) -> str:
    return f"tcp://127.0.0.1:{PCM_BASE_PORT + lane_id}"


def metadata_endpoint() -> str:
    return f"tcp://127.0.0.1:{METADATA_PORT}"


def pcm_backend_endpoint() -> str:
    return f"tcp://127.0.0.1:{PCM_PORT}"


def control_backend_endpoint() -> str:
    return f"tcp://127.0.0.1:{CONTROL_PORT}"


# SDR parameters
CENTER_FREQ = 855_962_500       # Hz (855.9625 MHz) — midpoint of control + voice range
SDR_SAMPLE_RATE = 3_200_000     # 3.2 Msps
SDR_RF_GAIN = 30                # dB
SDR_IF_GAIN = 20                # dB
SDR_BB_GAIN = 20                # dB

# Control channel
CONTROL_FREQ = 854_612_500      # Hz (854.6125 MHz)
CONTROL_OFFSET = CONTROL_FREQ - CENTER_FREQ  # -1,137,500 Hz

# Channelizer
CHANNEL_DECIMATION = 50
CHANNEL_RATE = SDR_SAMPLE_RATE // CHANNEL_DECIMATION  # 64,000 Hz
CHANNEL_FILTER_CUTOFF = 6250    # Hz, low-pass cutoff
CHANNEL_FILTER_TRANSITION = 1500  # Hz, transition width
FM_DEVIATION = 600              # Hz, P25 C4FM symbol deviation

# Lane manager timing
STALE_SWEEP_INTERVAL = 2.0     # seconds — how often to sweep stale lanes
STALE_MAX_AGE = 5.0            # seconds — release lane if tgid unseen this long

# OP25 dependency
OP25_APPS_DIR = os.environ.get("OP25_APPS_DIR", "/usr/local/lib/op25/apps")

# ZMQ sink
ZMQ_SINK_TIMEOUT = 100         # ms — voice lane PCM push timeout
