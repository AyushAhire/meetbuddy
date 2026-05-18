# MeetBuddy

Privacy-first AI meeting intelligence. Captures meeting audio locally via a browser extension (no bot joins), transcribes it, and builds a searchable memory across all your meetings.

**Your meeting data never leaves your machine unless you choose the hosted version.**

## Quick start

```bash
cp .env.example .env   # fill in LLM keys if using OpenAI/Anthropic
./scripts/setup.sh     # starts Postgres, Redis, MinIO and runs migrations
```

Then in separate terminals:

```bash
# API
cd apps/api && uv run uvicorn main:app --reload

# Celery worker
cd apps/api && uv run celery -A tasks.celery_app worker --loglevel=info

# Web dashboard
cd apps/web && pnpm dev

# Extension (load unpacked from apps/extension/.plasmo/chrome-mv3-dev after building)
cd apps/extension && pnpm dev
```

Open http://localhost:3000, register an account, then install the extension and join a Google Meet.

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js 14, Tailwind, shadcn/ui, TanStack Query |
| Extension | Plasmo (Chrome MV3), TypeScript strict |
| API | FastAPI, SQLAlchemy 2.0 async, Alembic |
| AI | faster-whisper, sentence-transformers, LangChain |
| DB | PostgreSQL 16 + pgvector, Redis |
| Storage | MinIO (local) / Cloudflare R2 (prod) |

## LLM providers

Set `LLM_PROVIDER` in `.env`:

- `ollama` (default — fully local, requires [Ollama](https://ollama.ai) running)
- `anthropic` — set `ANTHROPIC_API_KEY`
- `openai` — set `OPENAI_API_KEY`

## Phase 1 scope

- [x] Docker Compose stack boots with one command
- [x] User auth (register, login, JWT)
- [x] Extension captures Google Meet audio via WebSocket
- [x] Transcription pipeline (faster-whisper)
- [x] Post-meeting: summary + action items via LLM
- [x] Web dashboard: list meetings, view insights
- [x] Semantic search across all meetings

## License

Apache 2.0
