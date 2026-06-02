# MeetBuddy

**AI meeting notes that never send a bot into your call and never upload your audio to a stranger's server.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-20-green)](https://nodejs.org)

---

## The problem

Every meeting assistant today works the same way: a bot joins your call as a participant, your audio streams to their cloud, and you hope they handle it responsibly. That model is a non-starter for sales calls, legal discussions, medical conversations, or any company with a security policy.

## What MeetBuddy does

MeetBuddy captures audio at the OS level (via PipeWire on Linux) or through a Chrome extension — no bot, no third-party server, nothing visible to other participants. It transcribes with [faster-whisper](https://github.com/guillaumekynast/faster-whisper) locally, extracts summaries and action items with an LLM of your choice (Ollama, Anthropic, or OpenAI), and indexes everything in a local Postgres database with vector search so you can find anything you've ever discussed.

**Your audio never leaves your machine unless you explicitly configure a cloud LLM.**

Works with Google Meet, Zoom, Teams, or any app that uses your speakers — because it captures at the audio driver level, not the application level.

---

## How it works

### Option A — Desktop tray app (recommended)

Uses PipeWire to capture both your mic and speaker output at the OS level. Works with any meeting platform.

```
PipeWire
  ├─ mic input  (your voice)
  └─ sink monitor  (everything you hear)
        │
        ▼
  capture.py daemon  (port 7779)
        │
        ▼
  FastAPI  /api/v1/upload
        │
        └─ Celery pipeline  (transcribe → embed → insights)
```

### Option B — Chrome extension

Captures tab audio via `chrome.tabCapture` and your mic via `getUserMedia` inside the Google Meet tab. Streams chunks over WebSocket in real time. No bot joins the call.

```
Google Meet tab
  ├─ tabCapture  → offscreen document  → WebSocket chunks
  └─ getUserMedia  → content script  → WebSocket chunks
        │
        ▼
  FastAPI  /api/v1/ws/{meeting_id}
        │
        └─ Celery pipeline
```

Both paths feed the same backend:

```
Celery chain
  ├─ faster-whisper ──► transcript segments
  ├─ sentence-transformers ──► pgvector embeddings
  └─ LLM (Ollama / Anthropic / OpenAI)
         └─► summary + action items
                    │
                    ▼
     Next.js dashboard  (browse, search, query)
```

---

## Features

- **No bot** — audio is grabbed at the OS or browser level; nothing joins your call
- **Any platform** — tray app works with Google Meet, Zoom, Teams, or anything that uses your speakers
- **Fully local by default** — faster-whisper + Ollama; nothing leaves your machine
- **Separate audio tracks** — mic and speaker captured independently for better transcription accuracy
- **Semantic search** — find any moment across your full meeting history via pgvector
- **LLM-agnostic** — switch between Ollama, Anthropic, and OpenAI with one env var
- **Native desktop app** — system tray icon with one-click start/stop

---

## Quick start

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker + Compose | 24+ | Postgres, Redis, MinIO |
| Python | 3.11+ | API, worker, capture daemon, tray app |
| Node.js | 20+ | Web dashboard |
| pnpm | 8+ | JS package manager (`npm i -g pnpm`) |
| PipeWire | any | Audio capture on Linux (usually pre-installed) |
| Chrome | any | Extension (Option B only) |
| Ollama | latest | Optional — fully local LLM |

```bash
# 1. Clone and configure
git clone https://github.com/yourname/meetbuddy.git
cd meetbuddy
cp .env.example .env          # edit: JWT_SECRET, NEXTAUTH_SECRET, and your LLM key

# 2. Start infrastructure + API + worker
./scripts/start.sh

# 3. Start the web dashboard
cd apps/web && pnpm dev

# 4. Open http://localhost:3000, register an account, copy your token
```

### Option A — Desktop tray app

```bash
pip install pystray pillow pywebview

DISPLAY=:0 PYSTRAY_BACKEND=xorg python3 apps/tray/tray.py
```

Left-click the tray icon to open the app window. Open **Settings** and paste your token from the dashboard.

You can also run the capture daemon directly and control it from the web UI:

```bash
python3 apps/capture/capture.py --daemon
# Then click Record in the nav bar at http://localhost:3000/meetings
```

Or one-shot from the CLI:
```bash
python3 apps/capture/capture.py --token <jwt>
# Ctrl+C to stop — audio uploads automatically
```

### Option B — Chrome extension

```bash
cd apps/extension && pnpm dev
```

Load in Chrome:
1. Go to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** → select `apps/extension/.plasmo/chrome-mv3-dev`

Click the MeetBuddy icon while on a Google Meet tab. Paste your token in Settings, then click **Start**.

---

## Audio device selection

```bash
# List available PipeWire nodes
python3 apps/capture/capture.py --list

# Override mic or output device
python3 apps/capture/capture.py --mic <node-name> --monitor <node-name>
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` · `anthropic` · `openai` |
| `ANTHROPIC_API_KEY` | — | Required when provider is `anthropic` |
| `OPENAI_API_KEY` | — | Required when provider is `openai` |
| `GROQ_API_KEY` | — | Optional — fast cloud transcription via Groq Whisper |
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
│   ├── api/                        # FastAPI backend
│   │   ├── main.py                 # App entry point + router registration
│   │   ├── config.py               # Pydantic settings (reads .env)
│   │   ├── models/                 # SQLAlchemy 2.0 ORM models
│   │   ├── routes/
│   │   │   ├── auth.py             # JWT login / register / Google OAuth
│   │   │   ├── meetings.py         # CRUD for meeting records
│   │   │   ├── upload.py           # Audio file upload + pipeline trigger
│   │   │   ├── query.py            # Semantic search endpoint
│   │   │   └── websocket.py        # Real-time audio streaming (extension)
│   │   ├── services/
│   │   │   └── llm.py              # Unified LLM abstraction (all providers)
│   │   ├── tasks/
│   │   │   └── pipeline.py         # Celery chain: transcribe → embed → insights
│   │   └── alembic/                # DB migrations
│   ├── capture/
│   │   └── capture.py              # PipeWire capture daemon (mic + speaker)
│   ├── tray/
│   │   ├── tray.py                 # System tray app (pystray + pywebview)
│   │   └── requirements.txt        # pystray, pillow, pywebview
│   ├── web/                        # Next.js 14 App Router dashboard
│   │   └── app/
│   │       ├── meetings/           # Meeting list + detail view
│   │       ├── query/              # Cross-meeting semantic search UI
│   │       └── components/
│   │           ├── recording-control.tsx   # Daemon control widget
│   │           └── browser-recorder.tsx    # getDisplayMedia fallback recorder
│   └── extension/                  # Plasmo Chrome MV3 extension
│       ├── content.ts              # Injected into Meet tab — mic capture + participant detection
│       ├── background.ts           # Service worker — tab capture orchestration
│       ├── sidepanel.tsx           # Side panel UI — record / stop / settings
│       └── tabs/offscreen.tsx      # Offscreen doc — tab audio capture only
├── docker/                         # Docker Compose stack
└── scripts/
    ├── start.sh                    # Start infra + API + worker
    └── meetbuddy-capture.service   # systemd user service for the capture daemon
```

---

## Tech stack

| Layer | Tech |
|---|---|
| Tray app | pystray, pywebview (GTK/WebKit), Pillow |
| Capture | PipeWire (`pw-record`), Python asyncio |
| Extension | Plasmo (Chrome MV3), TypeScript, WebSocket |
| API | FastAPI, SQLAlchemy 2.0 async, Alembic, Celery |
| AI | faster-whisper, sentence-transformers, LangChain |
| DB | PostgreSQL 16 + pgvector, Redis |
| Storage | MinIO (local) / Cloudflare R2 (prod) |
| Dashboard | Next.js 14 App Router, Tailwind CSS, shadcn/ui, TanStack Query |

---

## LLM providers

All LLM calls are routed through `apps/api/services/llm.py`.

| `LLM_PROVIDER` | What you need |
|---|---|
| `ollama` (default) | [Ollama](https://ollama.ai) running locally; `ollama pull llama3` |
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
| `POST` | `/upload/audio` | Upload an audio file |
| `POST` | `/upload/complete` | Trigger processing pipeline |
| `GET` | `/query?q=...` | Semantic search across all meetings |
| `WS` | `/ws/{meeting_id}` | Stream audio chunks (extension) |

Health check: `GET /health`

---

## License

[Apache 2.0](LICENSE)
