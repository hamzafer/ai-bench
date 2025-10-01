#!/usr/bin/env bash
# Launch the API (uvicorn) and React dev server together.
# Usage: ./scripts/run_dev.sh

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
API_PORT=${API_PORT:-8000}
VITE_PORT=${VITE_PORT:-5173}

cd "$ROOT_DIR"

start_backend() {
  echo "[backend] Starting uvicorn on port ${API_PORT}..."
  uv run uvicorn comment_benchmark.api:app --reload --port "$API_PORT"
}

start_frontend() {
  echo "[frontend] Preparing React dev server on port ${VITE_PORT}..."
  cd "$ROOT_DIR/ui"
  if [ ! -d node_modules ]; then
    echo "[frontend] Installing npm dependencies..."
    npm install
  fi
  npm run dev -- --port "$VITE_PORT"
}

cleanup() {
  echo
  echo "Stopping dev servers..."
  pkill -P $$ || true
}

trap cleanup EXIT

start_backend &
BACK_PID=$!

start_frontend &
FRONT_PID=$!

echo "Backend PID: ${BACK_PID}"
echo "Frontend PID: ${FRONT_PID}"
echo "Press Ctrl+C to stop both servers."

wait
