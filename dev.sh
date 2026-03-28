#!/usr/bin/env bash
# Launch the TRM API server and Next.js frontend together.
# Usage: ./dev.sh
# Stop:  Ctrl+C (kills both processes)

set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
  echo ""
  echo "Shutting down..."
  kill $API_PID $WEB_PID 2>/dev/null
  wait $API_PID $WEB_PID 2>/dev/null
  echo "Done."
}
trap cleanup EXIT INT TERM

# Activate venv and start API
echo "Starting API server on :8000..."
(cd "$ROOT" && source src/.venv/bin/activate && uvicorn api.main:app --reload --port 8000) &
API_PID=$!

# Start Next.js frontend
echo "Starting frontend on :3000..."
(cd "$ROOT/web" && npm run dev -- --port 3000) &
WEB_PID=$!

echo ""
echo "  API:      http://localhost:8000"
echo "  Frontend: http://localhost:3000"
echo "  Press Ctrl+C to stop both."
echo ""

wait
