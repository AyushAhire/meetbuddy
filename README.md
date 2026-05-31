# MeetBuddy

> Privacy-first AI meeting intelligence — no bots, no cloud lock-in, runs entirely on your machine.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](https://www.python.org)
[![Node](https://img.shields.io/badge/node-20-green)](https://nodejs.org)

MeetBuddy records your meetings, transcribes the audio, extracts summaries and action items, and lets you search across your full meeting history — all running locally. No bots join your call. No third-party server sees your audio.

**Your meeting data never leaves your machine unless you choose a Cloud LLM.**

---

## How it works

Two ways to capture audio — use whichever fits your setup:

### Option A — Desktop tray app (recommended)
Uses PipeWire to capture your microphone and all speaker output at the OS level. Works with any meeting platform (Google Meet, Zoom, Teams, etc.).

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
Captures tab audio via `chrome.tabCapture` and your mic via `getUserMedia` in the Google Meet content script. Streams chunks over WebSocket in real time.

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

Both paths feed the same backend pipeline:

```
Celery chain
  ├─ faster-whisper ──► transcript segments
  ├─ sentence-transformers ──► pgvector embeddings
  └─ LLM (Ollama / Anthropic / OpenAI)
         └─► summary + action items
                    │
                    ▼
     Next.js dashboard  (browse, search, insights)
```

---

## Features

- **Zero-bot capture** — audio is grabbed at the OS or browser level; no bot appears on the call
- **Any platform** — tray app works with Google Meet, Zoom, Teams, or any app that uses your speakers
- **Native desktop app** — system tray icon with a built-in pywebview window; start/stop recording with one click
- **Both audio tracks** — mic and speaker output captured and mixed separately for better transcription
- **Fully local by default** — faster-whisper + Ollama means nothing leaves your machine
- **Semantic search** — find anything across your full meeting history via pgvector
- **LLM-agnostic** — switch between Ollama, Anthropic, and OpenAI with a single env var
- **Auto action items** — extracted by the LLM after each meeting completes
- **Browser fallback** — `BrowserRecorder` in the web dashboard uses `getDisplayMedia` if neither option above is available

---

## Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Docker + Compose | 24+ | Postgres, Redis, MinIO |
| Python | 3.11+ | API, worker, capture daemon, tray app |
| Node.js | 20+ | Web dashboard |
| pnpm | 8+ | JS package manager (`npm i -g pnpm`) |
| PipeWire | any | Audio capture on Linux (usually pre-installed) |
| Chrome | any | Extension (Option B only) |
| Ollama | latest | Optional — fully local LLM |

Python deps for the tray app:
```bash
pip install pystray pillow pywebview
# httpx is already installed via apps/api requirements
```

---

## Quick start

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

### Option A — Desktop tray app (recommended)

```bash
# Install tray deps once
pip install pystray pillow pywebview

# Launch (persists in system tray)
DISPLAY=:0 PYSTRAY_BACKEND=xorg python3 apps/tray/tray.py
```

Left-click the tray icon to open the app window. First launch: open **Settings** and paste your token from the dashboard.

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
# Build the extension
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

Key vars in `.env` (full list in `.env.example`):

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
│   ├── mic-test/
│   │   └── index.html              # Browser-based mic diagnostic tool
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
| Extension | Plasmo (Chrome MV3), TypeScript, WebSocket, Web Audio API |
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
