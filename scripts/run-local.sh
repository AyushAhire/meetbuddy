#!/usr/bin/env bash
# Run MeetBuddy in fully-local mode — SQLite + local file storage + in-process
# pipeline + capture daemon. No Docker, no Postgres, no Redis, no MinIO, no login.
#
# Usage:
#   scripts/run-local.sh        # start API + dashboard + capture daemon
#
# Then open http://127.0.0.1:8000 and click Record.
# Data (DB + recordings) lives in $MEETBUDDY_DATA_DIR. Ctrl+C stops everything.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export MEETBUDDY_DATA_DIR="${MEETBUDDY_DATA_DIR:-$HOME/.local/share/MeetBuddy}"
mkdir -p "$MEETBUDDY_DATA_DIR"
# Override the dev .env's DATABASE_URL — env vars win over .env in pydantic.
export DATABASE_URL="sqlite+aiosqlite:///$MEETBUDDY_DATA_DIR/meetbuddy.db"
export MEETBUDDY_STORAGE_BACKEND=local

# Build the dashboard once if it hasn't been exported yet.
if [ ! -f "$ROOT/apps/web/out/index.html" ]; then
  echo "Building the dashboard (first run, ~30s)…"
  ( cd "$ROOT/apps/web" && NEXT_PUBLIC_API_URL="" pnpm install && NEXT_PUBLIC_API_URL="" pnpm build )
fi

cd "$ROOT/apps/api"

# Start the capture daemon (PipeWire) in the background; stop it on exit.
echo "Starting capture daemon…"
uv run python "$ROOT/apps/capture/capture.py" --daemon > "$MEETBUDDY_DATA_DIR/daemon.log" 2>&1 &
DAEMON_PID=$!
cleanup() { kill "$DAEMON_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo ""
echo "MeetBuddy — local mode"
echo "  data dir  : $MEETBUDDY_DATA_DIR"
echo "  database  : sqlite ($MEETBUDDY_DATA_DIR/meetbuddy.db)"
echo "  dashboard : http://127.0.0.1:8000        ← open this in your browser"
echo "  API docs  : http://127.0.0.1:8000/docs"
echo "  daemon log: $MEETBUDDY_DATA_DIR/daemon.log"
echo ""
echo "Press Ctrl+C to stop everything."
echo ""

uv run uvicorn main:app --host 127.0.0.1 --port 8000
