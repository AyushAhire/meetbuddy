# MeetBuddy

> Privacy-first AI meeting intelligence — no bots, no cloud lock-in, runs entirely on your machine.

![License](https://img.shields.io/badge/license-Apache%202.0-blue)
![Python](https://img.shields.io/badge/python-3.11-blue)
![Node](https://img.shields.io/badge/node-20-green)
![Phase](https://img.shields.io/badge/phase-1%20complete-brightgreen)

MeetBuddy captures meeting audio locally via a Chrome extension (no bot joins your call), transcribes it with faster-whisper, and builds a searchable memory across all your meetings — powered by the LLM of your choice, fully offline-capable.

**Your meeting data never leaves your machine unless you choose the hosted version.**

---

## How it works

```
Browser Tab (Google Meet)
        │  WebSocket audio stream
        ▼
Chrome Extension (Plasmo MV3)
        │  POST /meetings + audio chunks
        ▼
FastAPI Backend
        │
        ├─ Celery Worker ──► faster-whisper ──► Transcript
        │                          │
        │                          ▼
        │                 sentence-transformers ──► pgvector (embeddings)
        │                          │
        │                          ▼
        │                    LLM (local or API) ──► Summary + Action Items
        │
        └─ REST API ──► Next.js Dashboard (search, browse, insights)
```

---

## Features

- **Zero-bot capture** — audio captured in the browser tab; nobody sees a bot join your call
- **Fully local by default** — Ollama + faster-whisper means no data leaves your machine
- **Searchable memory** — semantic search across all transcripts via pgvector
- **LLM-agnostic** — swap between Ollama, Anthropic, or OpenAI with one env var
- **Action items** — LLM extracts follow-ups automatically after each meeting
- **Multi-meeting context** — ask questions that span your entire meeting history

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Docker + Compose | 24+ | For Postgres, Redis, MinIO |
| Python | 3.11 | Managed by `uv` |
| Node.js | 20+ | For web dashboard |
| pnpm | 8+ | `npm i -g pnpm` |
| Ollama | latest | Optional — for fully local LLM |

---

## Quick start

```bash
cp .env.example .env        # fill in LLM keys if not using Ollama
./scripts/setup.sh          # starts Postgres, Redis, MinIO and runs migrations
```

Then in separate terminals:

```bash
# API server
cd apps/api && uv run uvicorn main:app --reload

# Celery pipeline worker
cd apps/api && uv run celery -A tasks.celery_app worker --loglevel=info

# Web dashboard
cd apps/web && pnpm dev

# Chrome extension (dev mode)
cd apps/extension && pnpm dev
# then load apps/extension/.plasmo/chrome-mv3-dev as an unpacked extension in Chrome
```

Open [http://localhost:3000](http://localhost:3000), register an account, install the extension, and join a Google Meet. MeetBuddy starts recording automatically.

---

## Project structure

```
meetbuddy/
├── apps/
│   ├── api/                  # FastAPI backend
│   │   ├── main.py           # App entry point + router registration
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── routes/           # HTTP route handlers
│   │   ├── services/
│   │   │   └── llm.py        # Single LLM abstraction (ollama/anthropic/openai)
│   │   ├── tasks/
│   │   │   └── pipeline.py   # Celery chain: transcribe → embed → insights
│   │   └── alembic/          # DB migrations (autogenerate only)
│   ├── web/                  # Next.js 14 App Router dashboard
│   └── extension/            # Plasmo Chrome MV3 extension
├── packages/
│   └── shared-types/         # TypeScript types shared by web + extension
├── docker/                   # Docker Compose stack
└── scripts/
    └── setup.sh              # One-command local bootstrap
```

---

## Stack

| Layer | Tech |
|---|---|
| Web | Next.js 14, Tailwind CSS, shadcn/ui, TanStack Query |
| Extension | Plasmo (Chrome MV3), TypeScript strict |
| API | FastAPI, SQLAlchemy 2.0 async, Alembic, Celery |
| AI | faster-whisper, sentence-transformers, LangChain |
| DB | PostgreSQL 16 + pgvector, Redis |
| Storage | MinIO (local) / Cloudflare R2 (prod) |

---

## LLM configuration

Set `LLM_PROVIDER` in `.env`:

| Value | Description |
|---|---|
| `ollama` (default) | Fully local — requires [Ollama](https://ollama.ai) running locally |
| `anthropic` | Set `ANTHROPIC_API_KEY` |
| `openai` | Set `OPENAI_API_KEY` |

All LLM calls are routed through `apps/api/services/llm.py` — a single place to add new providers.


## License

[Apache 2.0](LICENSE)
