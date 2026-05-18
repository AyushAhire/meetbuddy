# MeetBuddy — AI Coding Spec

> This file is the source of truth for Claude (or any AI assistant) when writing code for MeetBuddy.
> Read this entire file before writing any code. Follow every decision here — do not invent alternatives unless explicitly asked.

---

## What is MeetBuddy

MeetBuddy is an open-source, privacy-first AI meeting intelligence platform. It captures meeting audio locally via a browser extension (no bot joins the call), transcribes it, and builds a searchable, queryable memory across all meetings.

**Core promise:** Your meeting data never leaves your machine unless you choose the hosted version.

**Not building:** A meeting bot. A Zoom/Teams native app (Phase 1 is browser only). A real-time transcription overlay (Phase 1 is post-meeting processing).

---

## Monorepo Structure

```
meetbuddy/
├── apps/
│   ├── web/                  # Next.js dashboard (user-facing app)
│   ├── extension/            # Chrome/Firefox extension (Plasmo)
│   └── api/                  # FastAPI backend
├── packages/
│   ├── shared-types/         # TypeScript types shared between web + extension
│   └── ui/                   # Shared React components (shadcn-based)
├── docker/
│   ├── docker-compose.yml    # Full local stack
│   ├── docker-compose.dev.yml
│   └── Dockerfile.*          # Per-service Dockerfiles
├── scripts/
│   └── setup.sh              # One-command local setup
├── docs/
│   └── architecture.md
├── CLAUDE.md                 # This file
├── README.md
└── .github/
    └── workflows/
        ├── ci.yml
        └── release.yml
```

---

## Tech Stack — Exact Choices, No Alternatives

### Frontend — `apps/web`
- **Framework:** Next.js 14 (App Router)
- **Styling:** Tailwind CSS
- **Components:** shadcn/ui (import from `@/components/ui`)
- **State:** Zustand for client state, React Query (TanStack Query v5) for server state
- **Auth:** NextAuth.js v5 with Google OAuth provider
- **Forms:** React Hook Form + Zod
- **Icons:** Lucide React
- **Date handling:** date-fns

### Browser Extension — `apps/extension`
- **Framework:** Plasmo (handles MV3 complexity)
- **Language:** TypeScript strict mode
- **Styling:** Tailwind CSS (Plasmo supports it natively)
- **Audio capture:** Chrome `tabCapture` API + `getUserMedia`
- **Storage:** `chrome.storage.local` for settings, session state
- **Messaging:** Plasmo messaging API (not raw `chrome.runtime`)

### Backend — `apps/api`
- **Framework:** FastAPI (Python 3.11+)
- **Package manager:** uv (not pip, not poetry — uv is faster)
- **Task queue:** Celery with Redis as broker
- **ORM:** SQLAlchemy 2.0 (async) with Alembic for migrations
- **Validation:** Pydantic v2
- **Auth:** python-jose for JWT, passlib for hashing

### AI & Transcription
- **Transcription:** faster-whisper (`large-v3` model for quality, `base` for speed)
- **Diarization:** pyannote-audio 3.x (requires HuggingFace token — document this clearly)
- **Embeddings:** sentence-transformers (`nomic-ai/nomic-embed-text-v1`) — local by default
- **LLM:** Configurable via env var `LLM_PROVIDER`:
  - `openai` → OpenAI API (`gpt-4o-mini` for extraction, `gpt-4o` for queries)
  - `anthropic` → Claude API (`claude-haiku-4-5-20251001` for extraction, `claude-sonnet-4-6` for queries)
  - `ollama` → Local Ollama (`llama3.1:8b` default)
- **LLM abstraction:** Use LangChain's chat model interface so provider is swappable

### Database
- **Primary:** PostgreSQL 16
- **Vector search:** pgvector extension (`vector` column type)
- **Cache / broker:** Redis 7
- **Migrations:** Alembic (auto-generate, never hand-write migration files)

### Storage
- **Local dev:** MinIO (S3-compatible, runs in Docker)
- **Production:** Cloudflare R2
- **Client:** boto3 with custom endpoint URL (works for both MinIO and R2)

### Infrastructure
- **Containerization:** Docker + Docker Compose
- **CI:** GitHub Actions
- **Environment:** `.env` files, never hardcoded secrets

---

## Database Schema

Always use these exact table and column names. Do not rename.

```sql
-- Users
CREATE TABLE users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       TEXT UNIQUE NOT NULL,
  name        TEXT,
  avatar_url  TEXT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Meetings
CREATE TABLE meetings (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
  title         TEXT,
  platform      TEXT NOT NULL,          -- 'google_meet' | 'zoom' | 'teams' | 'unknown'
  started_at    TIMESTAMPTZ NOT NULL,
  ended_at      TIMESTAMPTZ,
  duration_secs INTEGER,
  status        TEXT NOT NULL DEFAULT 'recording',  -- 'recording' | 'processing' | 'done' | 'failed'
  audio_url     TEXT,                   -- S3/R2 path to raw audio
  transcript_url TEXT,                  -- S3/R2 path to full transcript JSON
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Speakers detected in a meeting
CREATE TABLE speakers (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id  UUID REFERENCES meetings(id) ON DELETE CASCADE,
  label       TEXT NOT NULL,            -- 'SPEAKER_00', 'SPEAKER_01' etc.
  name        TEXT,                     -- resolved name if matched from DOM
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- Transcript chunks (searchable units)
CREATE TABLE chunks (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id  UUID REFERENCES meetings(id) ON DELETE CASCADE,
  speaker_id  UUID REFERENCES speakers(id),
  text        TEXT NOT NULL,
  start_time  FLOAT NOT NULL,           -- seconds from meeting start
  end_time    FLOAT NOT NULL,
  embedding   vector(768),              -- nomic-embed output dimension
  created_at  TIMESTAMPTZ DEFAULT now()
);

-- AI-extracted structured data per meeting
CREATE TABLE meeting_insights (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id    UUID REFERENCES meetings(id) ON DELETE CASCADE UNIQUE,
  summary       TEXT,
  action_items  JSONB DEFAULT '[]',     -- [{text, owner, due_date}]
  decisions     JSONB DEFAULT '[]',     -- [{text, context}]
  topics        JSONB DEFAULT '[]',     -- [{name, duration_secs}]
  participants  JSONB DEFAULT '[]',     -- [{name, talk_time_secs}]
  raw_llm_output JSONB,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Persistent entity memory (clients, people, topics across meetings)
CREATE TABLE memory_entities (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  type        TEXT NOT NULL,            -- 'person' | 'company' | 'project' | 'topic'
  facts       JSONB DEFAULT '[]',       -- [{fact, source_meeting_id, created_at}]
  updated_at  TIMESTAMPTZ DEFAULT now(),
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, name, type)
);

-- Vector index for semantic search
CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

---

## API Design

Base URL: `/api/v1`

### Auth
```
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh
DELETE /api/v1/auth/logout
```

### Meetings
```
GET    /api/v1/meetings              # list, supports ?status=done&limit=20&offset=0
POST   /api/v1/meetings              # create (called by extension when meeting starts)
GET    /api/v1/meetings/:id          # single meeting with insights
PATCH  /api/v1/meetings/:id          # update title, status
DELETE /api/v1/meetings/:id
GET    /api/v1/meetings/:id/transcript  # full transcript with speaker labels
GET    /api/v1/meetings/:id/audio    # presigned URL to audio file
```

### Upload (for extension to push audio)
```
POST   /api/v1/upload/audio          # multipart, returns upload_id
POST   /api/v1/upload/complete       # signals processing can start
```

### Query (RAG endpoint)
```
POST   /api/v1/query
Body: { "q": "what did we decide about pricing?", "meeting_ids": [] }
# meeting_ids: empty array = search all meetings
# Returns: { answer, sources: [{ chunk_id, meeting_id, text, start_time }] }
```

### Memory
```
GET    /api/v1/memory                # all entities
GET    /api/v1/memory/:id            # single entity with all facts
PATCH  /api/v1/memory/:id            # manual edit
DELETE /api/v1/memory/:id
```

### WebSocket (live extension communication)
```
WS     /api/v1/ws/:meeting_id        # extension connects here during recording
# Messages:
# extension → server: { type: "chunk", audio_b64: "...", seq: 1 }
# server → extension: { type: "status", message: "Recording..." }
# server → extension: { type: "transcript_partial", text: "..." }
```

---

## Extension Architecture

The extension has four parts. Keep them strictly separated:

```
extension/
├── background.ts          # Service worker — manages recording lifecycle
├── content.ts             # Injected into meet.google.com — scrapes participant names
├── sidepanel/
│   └── index.tsx          # React sidepanel UI (shows during meeting)
└── popup/
    └── index.tsx          # Extension popup (settings, status)
```

### background.ts responsibilities
- Detect when user navigates to `meet.google.com/*`
- Start/stop audio capture via `chrome.tabCapture`
- Open WebSocket connection to backend
- Chunk audio every 5 seconds, send via WebSocket
- Never do DOM manipulation here

### content.ts responsibilities
- Observe DOM for participant name elements
- Extract names from `[data-participant-id]` tiles
- Send names to background via `chrome.runtime.sendMessage`
- Never do audio capture here

### sidepanel/index.tsx responsibilities
- Show recording status indicator
- Show live partial transcript (streamed from WS)
- Query input: ask questions about current meeting
- Action items detected so far
- Never directly access audio APIs

---

## Processing Pipeline

When audio upload completes, Celery runs these tasks in order. Each task is idempotent — safe to retry.

```python
# Task chain (defined in api/tasks/)
process_meeting.si(meeting_id)
  → transcribe_audio(meeting_id)        # faster-whisper + pyannote
  → store_transcript(meeting_id)        # save to S3, store chunks in DB
  → embed_chunks(meeting_id)            # sentence-transformers, store vectors
  → extract_insights(meeting_id)        # LLM call → meeting_insights table
  → update_memory(meeting_id)           # extract entities → memory_entities
  → mark_complete(meeting_id)           # status = 'done', notify via WS
```

Each task takes only `meeting_id`. Fetch what it needs from DB. Do not pass large objects between tasks.

---

## LLM Prompts

Store all prompts in `api/prompts/` as `.txt` files. Load with `open()`. Never inline prompts in code.

### `api/prompts/extract_insights.txt`
```
You are an expert meeting analyst. Given the following meeting transcript, extract structured information.

Transcript:
{transcript}

Return ONLY valid JSON matching this exact schema — no explanation, no markdown:
{
  "summary": "2-3 sentence summary of the meeting",
  "action_items": [
    {"text": "action item description", "owner": "person name or null", "due_date": "YYYY-MM-DD or null"}
  ],
  "decisions": [
    {"text": "decision made", "context": "brief context"}
  ],
  "topics": [
    {"name": "topic name", "duration_secs": 0}
  ]
}
```

### `api/prompts/query_meetings.txt`
```
You are a helpful assistant with access to a user's meeting history.
Answer the user's question based ONLY on the provided meeting excerpts.
If the answer is not in the excerpts, say "I don't have enough information from your meetings to answer that."
Always cite which meeting the information comes from.

Meeting excerpts:
{context}

User question: {question}

Answer:
```

### `api/prompts/extract_entities.txt`
```
Given this meeting transcript, extract named entities to remember.
Return ONLY valid JSON, no explanation:
{
  "entities": [
    {"name": "entity name", "type": "person|company|project|topic", "facts": ["fact 1", "fact 2"]}
  ]
}

Transcript:
{transcript}
```

---

## Environment Variables

All services read from `.env` at repo root. Never commit `.env`. Always commit `.env.example`.

```bash
# Database
DATABASE_URL=postgresql+asyncpg://meetbuddy:meetbuddy@localhost:5432/meetbuddy
REDIS_URL=redis://localhost:6379/0

# Storage
STORAGE_ENDPOINT=http://localhost:9000    # MinIO local / R2 in prod
STORAGE_ACCESS_KEY=meetbuddy
STORAGE_SECRET_KEY=meetbuddy123
STORAGE_BUCKET=meetbuddy

# Auth
JWT_SECRET=change-this-in-production
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# LLM (set one provider)
LLM_PROVIDER=ollama                       # 'openai' | 'anthropic' | 'ollama'
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# Transcription
WHISPER_MODEL=base                        # 'base' | 'small' | 'medium' | 'large-v3'
HF_TOKEN=                                 # HuggingFace token for pyannote

# App
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_SECRET=change-this-in-production
NEXTAUTH_URL=http://localhost:3000
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
```

---

## Code Style Rules

### Python
- Type hints everywhere, no exceptions
- Async functions for all I/O (database, HTTP, file)
- Pydantic models for all request/response shapes
- Error handling: raise `HTTPException` in routes, catch in task workers and log
- File structure per service:
  ```
  api/
  ├── main.py              # FastAPI app init, middleware, router registration
  ├── config.py            # Settings class using pydantic-settings
  ├── database.py          # SQLAlchemy engine, session factory
  ├── models/              # SQLAlchemy ORM models (one file per table group)
  ├── schemas/             # Pydantic request/response schemas
  ├── routes/              # FastAPI routers (one file per resource)
  ├── services/            # Business logic (no DB calls in routes)
  ├── tasks/               # Celery task definitions
  ├── prompts/             # LLM prompt .txt files
  └── utils/               # Pure utility functions
  ```

### TypeScript
- Strict mode always (`"strict": true` in tsconfig)
- No `any` types — use `unknown` and narrow
- Prefer `interface` over `type` for object shapes
- Named exports only, no default exports except Next.js pages
- Component file structure:
  ```tsx
  // 1. Imports
  // 2. Types/interfaces
  // 3. Component function
  // 4. Named export
  ```

### General
- No commented-out code in commits
- No TODO comments — open a GitHub issue instead
- Every function longer than 20 lines needs a docstring/JSDoc
- No magic numbers — use named constants

---

## What to Build First (Phase 1 Scope)

Build ONLY these things for Phase 1. Do not scope-creep.

- [ ] Docker Compose stack (Postgres, Redis, MinIO, API, Web) boots with one command
- [ ] User auth (register, login, JWT)
- [ ] Extension detects Google Meet tab, captures audio, sends to backend via WebSocket
- [ ] Transcription pipeline (faster-whisper, no diarization in Phase 1 — just full transcript)
- [ ] Post-meeting processing: summary + action items extraction via LLM
- [ ] Web dashboard: list meetings, view summary + action items per meeting
- [ ] Basic semantic search: `POST /api/v1/query` returns relevant chunks

Phase 2 (do not build yet):
- Speaker diarization
- Real-time partial transcripts in sidepanel
- Memory entities
- Zoom / Teams support
- Team/multi-user features
- Billing

---

## Things Claude Should Never Do

- Never use `any` in TypeScript
- Never hardcode API keys, URLs, or secrets
- Never write raw SQL — use SQLAlchemy ORM
- Never call the LLM directly in a route handler — always via a service function
- Never store audio or transcripts in the database — always in object storage, store only the URL
- Never skip error handling on async operations
- Never use `setTimeout` for polling — use WebSockets or Celery task status
- Never mix business logic into route handlers — routes call services, services call models
- Never create a migration file by hand — always `alembic revision --autogenerate`

---

## Testing

- Python: pytest + pytest-asyncio, one test file per service file
- TypeScript: Vitest for unit tests, Playwright for E2E
- Minimum: every API route has at least one happy-path test
- Test files live next to the code they test (`services/transcription.py` → `services/transcription_test.py`)

---

## How to Ask Claude for Help

When asking Claude to write code for MeetBuddy, always include:

1. Which layer you're working on (extension / api / web)
2. The specific file path you want code written to
3. Reference to the relevant section of this spec

Example prompt:
> "Using CLAUDE.md, write the FastAPI route handler for `POST /api/v1/meetings` in `apps/api/routes/meetings.py`. It should create a meeting row, return the meeting ID, and follow the error handling patterns in the spec."

This gets you production-ready code instead of generic examples.

---

## Open Source Metadata

- **License:** Apache 2.0
- **Repo name:** `meetbuddy` (GitHub org TBD)
- **Contributing:** PRs welcome, issues before PRs for large changes
- **Code of conduct:** Contributor Covenant

---

*Last updated: May 2026. If this file conflicts with a newer decision, the newer decision wins — update this file.*
