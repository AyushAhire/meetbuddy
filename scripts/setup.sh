#!/usr/bin/env bash
set -euo pipefail

echo "==> MeetBuddy local setup"

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker required but not found. Install Docker Desktop."; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo "docker compose required."; exit 1; }

# Copy env file
if [ ! -f .env ]; then
  cp .env.example .env
  echo "==> Created .env from .env.example — edit it with your API keys before running."
fi

# Start infrastructure
echo "==> Starting Docker services..."
docker compose -f docker/docker-compose.yml up -d postgres redis minio minio-init

echo "==> Waiting for Postgres..."
until docker compose -f docker/docker-compose.yml exec -T postgres pg_isready -U meetbuddy >/dev/null 2>&1; do
  sleep 1
done

# Run migrations
echo "==> Running database migrations..."
if command -v uv >/dev/null 2>&1; then
  (cd apps/api && uv run alembic upgrade head)
else
  echo "uv not found — skipping migrations. Run: cd apps/api && uv run alembic upgrade head"
fi

echo ""
echo "==> Setup complete!"
echo ""
echo "  Start API:       cd apps/api && uv run uvicorn main:app --reload"
echo "  Start web:       cd apps/web && pnpm dev"
echo "  Start worker:    cd apps/api && uv run celery -A tasks.celery_app worker --loglevel=info"
echo "  MinIO console:   http://localhost:9001  (meetbuddy / meetbuddy123)"
echo ""
