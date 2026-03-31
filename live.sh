#!/usr/bin/env bash
# Run the full mock live pipeline: capture, preprocessing, TRM, API, and frontend.
# Usage: ./live.sh
# Stop:  Ctrl+C (kills all processes)

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/src/.venv/bin/python"

PIDS=()

cleanup() {
  echo ""
  echo "Shutting down..."
  kill "${PIDS[@]}" 2>/dev/null
  wait "${PIDS[@]}" 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# 1. Ensure schema is up to date
echo "Applying migrations..."
(cd "$ROOT" && "$PY" -m alembic upgrade head)

# 2. Reset database
echo "Resetting database..."
(cd "$ROOT" && "$PY" db/reset.py)

# 3. Start API server
echo "Starting API server on :8000..."
(cd "$ROOT" && "$PY" -m uvicorn api.main:app --reload --port 8000) &
PIDS+=($!)

# 4. Start Next.js frontend
echo "Starting frontend on :3000..."
(cd "$ROOT/web" && npm run dev -- --port 3000) &
PIDS+=($!)

# 5. Start mock preprocessing (polls for captured rows)
echo "Starting mock preprocessing..."
(cd "$ROOT" && "$PY" preprocessing/mock/run.py) &
PIDS+=($!)

# 6. Start mock capture (writes packets to DB)
echo "Starting mock capture..."
(cd "$ROOT" && "$PY" capture/mock/run.py) &
PIDS+=($!)

# 7. Start TRM live runner (polls for processed rows)
echo "Starting TRM live runner..."
(cd "$ROOT" && "$PY" src/main_live.py) &
PIDS+=($!)

echo ""
echo "  API:      http://localhost:8000"
echo "  Frontend: http://localhost:3000/live"
echo ""
echo "  Packets arrive every ~20s (10s capture + 10s ASR)."
echo "  Press Ctrl+C to stop all processes."
echo ""

wait
