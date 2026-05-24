# MeetBuddy

> Privacy-first AI meeting intelligence — no bots, no cloud lock-in, runs entirely on your machine.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-20-green)](https://nodejs.org)

MeetBuddy captures Google Meet audio directly in the browser — no bot joins your call, no third-party server sees your audio. A Chrome extension mixes tab audio (remote participants) and your microphone into a single stream, ships it to a local FastAPI server over WebSocket, and a Celery pipeline transcribes, embeds, and summarizes the meeting automatically.

**Your meeting data never leaves your machine unless you choose a Cloud LLM.**

---

## How it works

```
Google Meet tab
      │
      │  chrome.tabCapture (tab audio — remote participants)
      │  getUserMedia      (mic audio — you)
      │         ↓
Chrome Extension (Plasmo MV3 side panel)
      │
      │  WebSocket — audio/webm chunks every 5 s
      ↓
FastAPI  /api/v1/ws/{meeting_id}
      │
      ├─ MinIO ←── raw audio stored per chunk
      │
      └─ Celery chain
            │
            ├─ faster-whisper ──► transcript segments
            ├─ sentence-transformers ──► pgvector embeddings
            └─ LLM (Ollama / Anthropic / OpenAI)
                   └─► summary + action items
                              │
                              ▼
               Next.js dashboard  (search, browse, insights)
```

---

## Features

- **Zero-bot capture** — audio is grabbed inside the browser tab; no bot appears on the call
- **Both audio tracks** — tab audio (remote speakers) and your microphone are mixed and sent separately, then merged in transcription
- **Fully local by default** — faster-whisper + Ollama means nothing leaves your machine
- **Semantic search** — find anything across your full meeting history via pgvector
- **LLM-agnostic** — switch between Ollama, Anthropic, and OpenAI with a single env var
- **Auto action items** — extracted by the LLM after each meeting completes
- **Mic selection** — choose which microphone the extension uses from the side panel

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker + Compose | 24+ | Postgres, Redis, MinIO |
| Python | 3.11 | API + worker (`uv` manages the venv) |
| Node.js | 20+ | Web dashboard |
| pnpm | 8+ | JS package manager (`npm i -g pnpm`) |
| Chrome | any | Extension host |
| Ollama | latest | Optional — fully local LLM |

---

## Quick start

```bash
# 1. Clone and configure
git clone https://github.com/yourname/meetbuddy.git
cd meetbuddy
cp .env.example .env          # edit at minimum: JWT_SECRET, NEXTAUTH_SECRET

# 2. Start infrastructure and run DB migrations
./scripts/setup.sh
```

Then open four terminals:

```bash
# Terminal 1 — API server
cd apps/api && uv run uvicorn main:app --reload --port 8000

# Terminal 2 — Celery pipeline worker
cd apps/api && uv run celery -A tasks.celery_app worker --loglevel=info

# Terminal 3 — Web dashboard
cd apps/web && pnpm dev

# Terminal 4 — Chrome extension (dev build + hot-reload)
cd apps/extension && pnpm dev
```

Load the extension in Chrome:
1. Go to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select `apps/extension/.plasmo/chrome-mv3-dev`

Open [http://localhost:3000](http://localhost:3000), register an account, then join any Google Meet — the MeetBuddy side panel appears automatically.

---

## Environment variables

Key vars in `.env` (full list in `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` · `anthropic` · `openai` |
| `ANTHROPIC_API_KEY` | — | Required when provider is `anthropic` |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `WHISPER_MODEL` | `base` | faster-whisper model size (`tiny` · `base` · `small` · `medium` · `large`) |
| `JWT_SECRET` | **change this** | Signs user JWTs |
| `NEXTAUTH_SECRET` | **change this** | NextAuth session secret |
| `GOOGLE_CLIENT_ID` | — | Optional — enables Google OAuth login |

---

## Project structure

```
meetbuddy/
├── apps/
│   ├── api/                       # FastAPI backend
│   │   ├── main.py                # App entry point + router registration
│   │   ├── config.py              # Pydantic settings (reads .env)
│   │   ├── models/                # SQLAlchemy 2.0 ORM models
│   │   ├── routes/
│   │   │   ├── auth.py            # JWT login / register / Google OAuth
│   │   │   ├── meetings.py        # CRUD for meeting records
│   │   │   ├── upload.py          # Manual audio file upload
│   │   │   ├── query.py           # Semantic search endpoint
│   │   │   └── websocket.py       # Real-time audio streaming ingestion
│   │   ├── services/
│   │   │   └── llm.py             # Single LLM abstraction (all providers)
│   │   ├── tasks/
│   │   │   └── pipeline.py        # Celery chain: transcribe → embed → insights
│   │   └── alembic/               # DB migrations
│   ├── web/                       # Next.js 14 App Router dashboard
│   │   └── app/
│   │       ├── meetings/          # Meeting list + detail view
│   │       └── query/             # Cross-meeting semantic search UI
│   └── extension/                 # Plasmo Chrome MV3 extension
│       ├── content.ts             # Injected into Meet tab — mic capture + participant detection
│       ├── background.ts          # Service worker — tab capture orchestration
│       └── sidepanel.tsx          # Side panel UI — record / stop / settings
├── packages/
│   └── shared-types/              # TypeScript types shared by web + extension
├── docker/                        # Docker Compose stack (dev + prod variants)
└── scripts/
    └── setup.sh                   # One-command bootstrap
```

---

## Tech stack

| Layer | Tech |
|---|---|
| Extension | Plasmo (Chrome MV3), TypeScript strict, WebSocket, Web Audio API |
| API | FastAPI, SQLAlchemy 2.0 async, Alembic, Celery |
| AI | faster-whisper, sentence-transformers, LangChain |
| DB | PostgreSQL 16 + pgvector, Redis |
| Storage | MinIO (local) / Cloudflare R2 (prod) |
| Dashboard | Next.js 14 App Router, Tailwind CSS, shadcn/ui, TanStack Query |

---

## LLM providers

All LLM calls are routed through `apps/api/services/llm.py` — a single file to swap or add providers.

| `LLM_PROVIDER` | What you need |
|---|---|
| `ollama` (default) | [Ollama](https://ollama.ai) running locally; `ollama pull llama3` to get a model |
| `anthropic` | `ANTHROPIC_API_KEY` in `.env` |
| `openai` | `OPENAI_API_KEY` in `.env` |

---

## API reference

Base URL: `http://localhost:8000/api/v1`

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create account |
| `POST` | `/auth/login` | Get JWT |
| `GET` | `/meetings` | List meetings |
| `POST` | `/meetings` | Create meeting record |
| `GET` | `/meetings/{id}` | Meeting detail + transcript |
| `POST` | `/upload` | Upload an existing audio file |
| `GET` | `/query?q=...` | Semantic search across all meetings |
| `WS` | `/ws/{meeting_id}` | Stream audio chunks during a live meeting |

Health check: `GET /health`

---

## License

[Apache 2.0](LICENSE)
