#!/usr/bin/env bash
# MeetBuddy — start everything and optionally launch the capture tool.
#
# Usage:
#   ./scripts/start.sh           # start infra + API + worker (background)
#   ./scripts/start.sh capture   # also launch the audio capture script

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# ── 1. Docker infra ──────────────────────────────────────────────────────────
echo "[1/3] Starting infra (Postgres, Redis, MinIO)…"
docker compose -f "$ROOT/docker/docker-compose.yml" up -d postgres redis minio minio-init \
  --quiet-pull 2>/dev/null
echo "      Waiting for services to be healthy…"
for svc in postgres redis; do
  until docker compose -f "$ROOT/docker/docker-compose.yml" exec -T $svc \
      sh -c '[ "$?" = "0" ]' 2>/dev/null; do sleep 1; done
done
sleep 2   # minio-init needs a moment

# ── 2. DB migrations ─────────────────────────────────────────────────────────
echo "[2/3] Running DB migrations…"
(cd "$ROOT/apps/api" && uv run alembic upgrade head 2>&1 | grep -v "^$")

# ── 3. API server + Celery worker (background) ───────────────────────────────
echo "[3/3] Starting API server and Celery worker…"
LOG_DIR="$ROOT/.logs"
mkdir -p "$LOG_DIR"

# Kill any existing instances
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "celery.*meetbuddy\|celery.*tasks" 2>/dev/null || true
sleep 1

(cd "$ROOT/apps/api" && uv run uvicorn main:app --host 0.0.0.0 --port 8000 \
  > "$LOG_DIR/api.log" 2>&1) &
API_PID=$!

(cd "$ROOT/apps/api" && uv run celery -A tasks.celery_app worker \
  --loglevel=info --concurrency=2 \
  > "$LOG_DIR/worker.log" 2>&1) &
WORKER_PID=$!

# Wait for API to be ready
echo "      Waiting for API…"
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs 2>/dev/null \
    | grep -q "200" && break
  sleep 1
done

echo ""
echo "  ✓  Infra:   Postgres · Redis · MinIO"
echo "  ✓  API:     http://localhost:8000  (logs: .logs/api.log)"
echo "  ✓  Worker:  Celery                 (logs: .logs/worker.log)"
echo "  ✓  Web:     http://localhost:3000  (run manually: cd apps/web && npm run dev)"
echo ""

# ── Optional: launch capture ─────────────────────────────────────────────────
if [[ "${1}" == "capture" ]]; then
  TOKEN="${MEETBUDDY_TOKEN:-}"
  if [[ -z "$TOKEN" ]]; then
    echo "  To start recording, get your token from http://localhost:3000/meetings"
    echo "  then run:"
    echo "    MEETBUDDY_TOKEN=<token> python3 apps/capture/capture.py"
    echo ""
  else
    echo "  Launching audio capture…"
    echo "  (Ctrl+C stops recording and triggers processing)"
    echo ""
    python3 "$ROOT/apps/capture/capture.py" --token "$TOKEN"
  fi
else
  echo "  To record a meeting:"
  echo "    python3 apps/capture/capture.py --token <jwt>"
  echo ""
  echo "  Or start everything including capture:"
  echo "    MEETBUDDY_TOKEN=<token> ./scripts/start.sh capture"
  echo ""
fi
