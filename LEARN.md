# MeetBuddy — How Everything Works

A complete walkthrough of the codebase, written to help you learn the full system from scratch.

---

## What This App Does

MeetBuddy automatically records your Google Meet calls, transcribes the audio, extracts insights (summary, action items, decisions), and lets you search across all your past meetings using plain English questions.

**Three moving parts:**
1. **Chrome Extension** — captures audio during a live meeting
2. **FastAPI backend** — processes the audio and stores everything
3. **Next.js web app** — shows you the results and lets you query them

---

## System Architecture Overview

```
Chrome Extension (background.ts)
  │  detects Google Meet tab
  │  captures tab audio via MediaRecorder
  │  streams chunks via WebSocket every 5 seconds
  ▼
FastAPI API (main.py)  ←→  PostgreSQL (with pgvector)
  │  receives audio chunks                ↑
  │  stores audio in MinIO             models
  │  triggers Celery pipeline              │
  ▼                                        │
Celery Worker (tasks/pipeline.py)  ────────┘
  │  transcribes audio (Whisper)
  │  embeds transcript chunks (sentence-transformers)
  │  extracts insights (LLM)
  │  marks meeting "done"
  ▼
MinIO (S3-compatible object storage)
  stores: raw audio files, transcript JSON files

Next.js Web App
  reads from FastAPI to show meetings, transcripts, insights
  query page: sends a question → API does vector search → LLM answers
```

---

## The Infrastructure (docker-compose.yml)

Five services run together:

| Service | Image | Purpose |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16` | Database — the `pgvector` image adds a vector similarity extension |
| `redis` | `redis:7-alpine` | Message broker for Celery task queue |
| `minio` | `minio/minio` | S3-compatible object storage (stores audio + transcript files) |
| `api` | Custom Dockerfile | Runs the FastAPI server |
| `worker` | Same Dockerfile | Runs Celery worker (same code, different startup command) |
| `web` | Custom Dockerfile | Runs the Next.js app |

The `worker` service uses the exact same Docker image as `api` but is started with `celery -A tasks.celery_app worker` instead of uvicorn. This is a common pattern: one codebase, two processes.

---

## Backend Deep Dive (`apps/api/`)

### Configuration (`config.py`)

Uses `pydantic-settings` to read environment variables. Every config value is one attribute on the `Settings` class. Values come from a `.env` file at project root. Key settings:

- `database_url` — PostgreSQL connection string (uses `asyncpg` driver for async support)
- `redis_url` — Redis for Celery
- `storage_*` — MinIO credentials and endpoint
- `jwt_secret` — used to sign/verify JWT tokens
- `llm_provider` — switches between `ollama` (local), `openai`, or `anthropic`
- `whisper_model` — size of the Whisper speech-to-text model (`base`, `small`, `medium`, etc.)

### Database Setup (`database.py`)

```python
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)
```

This creates an **async** SQLAlchemy engine. Async means database calls don't block the server while waiting for a result — FastAPI can handle other requests at the same time.

`get_db()` is a FastAPI dependency that yields a session, commits on success, and rolls back on any exception. Routes receive this session via `Depends(get_db)`.

### Data Models (`models/`)

All models use SQLAlchemy's **mapped column** style (modern Python with type hints):

**`User`** — stores email, name, avatar URL, and a bcrypt-hashed password. ID is a UUID.

**`Meeting`** — the core entity. Tracks:
- Which user it belongs to (`user_id` foreign key)
- Which platform (`google_meet`, etc.)
- Status: `"recording"` → `"processing"` → `"done"`
- Where the audio file lives in MinIO (`audio_url` = a storage key like `audio/<uuid>/recording.webm`)
- Where the transcript JSON lives (`transcript_url` = key in MinIO)
- Related: `speakers`, `chunks`, `insights` (via SQLAlchemy relationships)

**`Speaker`** — represents one speaker identified in the recording (Phase 2 feature — diarization not fully wired yet). Has a `label` (like "SPEAKER_0") and an optional `name`.

**`Chunk`** — a segment of the transcript. Stores the text, start/end timestamps, and critically: a **768-dimension embedding vector**. This is what enables semantic search. The `embedding` column uses `pgvector.sqlalchemy.Vector(768)`.

**`MeetingInsights`** — one row per meeting (1:1 relationship). Stores `summary`, `action_items`, `decisions`, `topics` as JSONB arrays, plus the raw LLM output.

**`MemoryEntity`** — stores named entities (people, companies, projects) extracted from meetings for cross-meeting memory. Not yet wired into the main pipeline.

### Database Migration (`alembic/versions/0001_initial_schema.py`)

Alembic manages schema changes. The first migration:
1. Creates the `vector` PostgreSQL extension (required by pgvector)
2. Creates all tables in order (users → meetings → speakers → chunks → meeting_insights → memory_entities)
3. Creates an **IVFFlat index** on the `chunks.embedding` column — this makes vector similarity searches fast at scale

The `downgrade()` function drops everything in reverse order.

### API Entry Point (`main.py`)

```python
app = FastAPI(title="MeetBuddy API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "chrome-extension://*"], ...)
```

CORS middleware allows the web app (`localhost:3000`) and the Chrome extension (`chrome-extension://...`) to make API requests. Without this, browsers would block the requests.

All routes are mounted under `/api/v1`. There's also a `/health` endpoint for Docker healthchecks.

---

## Authentication (`routes/auth.py`, `services/auth.py`, `utils/auth.py`)

**JWT-based auth with access + refresh tokens.**

### How password auth works:

1. **Register** (`POST /api/v1/auth/register`): creates a user, hashes the password with bcrypt, returns both tokens
2. **Login** (`POST /api/v1/auth/login`): looks up user by email, verifies bcrypt hash, returns tokens
3. **Refresh** (`POST /api/v1/auth/refresh`): verifies the refresh token, issues a new pair
4. **Logout** (`DELETE /api/v1/auth/logout`): stateless — the client just drops its token. A real blocklist would go here.
5. **Me** (`GET /api/v1/auth/me`): returns the current user's profile

### JWT structure (`utils/auth.py`)

Every token payload has three fields:
- `sub` — the user's UUID (the "subject")
- `type` — either `"access"` or `"refresh"` (prevents using a refresh token as an access token)
- `exp` — expiry timestamp

Access tokens expire in 60 minutes. Refresh tokens expire in 30 days.

`passlib` with bcrypt handles password hashing. `python-jose` handles JWT encoding/decoding.

### How auth guards work in FastAPI

Any route that needs authentication has this dependency:
```python
current_user: User = Depends(get_current_user)
```

`get_current_user` reads the `Authorization: Bearer <token>` header, decodes the JWT, looks up the user in the database, and returns the User object. If anything fails, it raises a 401. All protected routes then automatically receive the User object.

---

## Meetings CRUD (`routes/meetings.py`, `services/meeting.py`)

Standard REST endpoints:

| Method | Path | What it does |
|---|---|---|
| `GET` | `/meetings` | List your meetings (filterable by status, paginated) |
| `POST` | `/meetings` | Create a new meeting record |
| `GET` | `/meetings/{id}` | Get one meeting (with insights eagerly loaded) |
| `PATCH` | `/meetings/{id}` | Update title, status, end time |
| `DELETE` | `/meetings/{id}` | Delete meeting (cascades to chunks, insights) |
| `GET` | `/meetings/{id}/transcript` | Get all chunks with timestamps and speaker names |
| `GET` | `/meetings/{id}/audio` | Get a signed URL to play the audio file |

**Ownership check**: every query in `services/meeting.py` filters by `Meeting.user_id == user_id` — you can only ever see your own meetings.

`selectinload(Meeting.insights)` tells SQLAlchemy to load the related `MeetingInsights` row in a second SQL query, avoiding the N+1 problem. The insights are then included in the `MeetingResponse` Pydantic schema.

---

## Audio Upload (`routes/upload.py`)

Two endpoints:

**`POST /upload/audio`** — accepts a file upload:
- Verifies you own the meeting
- Reads the file bytes
- Uploads to MinIO with key `audio/<meeting_id>/<filename>`
- Saves the key to `meeting.audio_url`

**`POST /upload/complete`** — signals upload is done:
- Sets status to `"processing"`
- Calls `process_meeting(meeting_id)` to kick off the Celery pipeline

This is used when the extension uploads a completed file (alternative to the streaming WebSocket approach).

---

## WebSocket Streaming (`routes/websocket.py`)

`WS /api/v1/ws/{meeting_id}` — used by the extension during a live meeting.

The server keeps an in-memory dict `AUDIO_CHUNK_STORE` mapping `meeting_id → list[bytes]`.

**Protocol:**
- Client sends `{"type": "chunk", "audio_b64": "<base64>", "seq": 0}` every 5 seconds
- Server decodes the base64 audio and appends to the in-memory list
- Client sends `{"type": "stop"}` when the meeting ends
- Server concatenates all chunks, uploads to MinIO, triggers the pipeline

If the client disconnects unexpectedly (`WebSocketDisconnect`), the server still finalizes whatever audio it received.

**Limitation**: `AUDIO_CHUNK_STORE` lives in process memory. In a multi-process deployment, the chunks would be lost if requests hit different workers. A real fix would use Redis or shared storage for the chunks.

---

## The Processing Pipeline (`tasks/pipeline.py`, `tasks/celery_app.py`)

Celery is a task queue — it lets you run code asynchronously in a separate worker process. This is important because transcription and LLM calls can take minutes; you don't want them blocking an HTTP request.

### Setup (`celery_app.py`)

```python
celery_app = Celery("meetbuddy", broker=settings.redis_url, backend=settings.redis_url)
```

- **Broker**: Redis receives the task message ("run this function with these args")
- **Backend**: Redis stores the task result (success/failure, return value)

### The Pipeline Chain

```python
def process_meeting(meeting_id: str) -> None:
    pipeline = chain(
        transcribe_audio.si(meeting_id),
        store_and_embed_chunks.si(meeting_id),
        extract_insights_task.si(meeting_id),
        mark_complete.si(meeting_id),
    )
    pipeline.delay()
```

`chain()` runs tasks in sequence — step 2 only starts after step 1 completes. `.si()` means "ignore the return value of the previous task" (the `i` stands for immutable signature). `.delay()` sends the chain to Redis so the Celery worker picks it up.

### Why sync tasks with async code?

Celery tasks are synchronous (they're normal Python functions). But the database layer is async. The bridge is:

```python
def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)
```

Each task defines an `async def _run_async()` inner function and calls `_run(_run_async())`. This blocks the sync Celery task until the async work is done.

### Step 1: `transcribe_audio`

1. Loads the meeting from the database
2. Sets status to `"processing"`
3. Calls `transcribe_audio_file(meeting.audio_url)` — downloads audio from MinIO, writes to a temp file, runs faster-whisper
4. Uploads the transcript JSON back to MinIO
5. Saves the transcript key to `meeting.transcript_url`

faster-whisper returns segments with `text`, `start`, `end`. These become the transcript chunks.

### Step 2: `store_and_embed_chunks`

1. Downloads the transcript JSON from MinIO
2. Extracts all segment texts
3. Calls `embed_texts(texts)` — runs all texts through `nomic-ai/nomic-embed-text-v1` (a sentence-transformer model) to produce 768-dim vectors
4. Creates a `Chunk` row for each segment with its embedding vector

This is what enables semantic search later.

### Step 3: `extract_insights_task`

1. Downloads transcript JSON
2. Concatenates all segment texts into one big string
3. Calls `extract_insights(transcript_text)` — sends to LLM with a prompt
4. LLM returns a JSON object
5. Saves a `MeetingInsights` row

### Step 4: `mark_complete`

Sets `meeting.status = "done"`.

### Retry logic

All tasks have `max_retries=3` and `bind=True` (so they can call `self.retry()`). If a step fails, it retries after a countdown (`countdown=30` seconds for most steps). This makes the pipeline resilient to transient failures.

---

## Transcription Service (`services/transcription.py`)

**Lazy loading**: both the Whisper model and the embedding model are loaded once on first use (via module-level `None` globals and `if _model is None: load it`). This avoids loading multi-GB models at import time.

**`transcribe_audio_file(audio_key)`**:
- Downloads audio bytes from MinIO
- Writes to a temp `.webm` file (Whisper needs a file path)
- Runs `model.transcribe(path, beam_size=5)` — higher beam size = slightly better accuracy, slower
- Returns segments as dicts: `[{"text": "...", "start": 0.0, "end": 2.3}, ...]`
- Deletes the temp file

**`embed_texts(texts)`**:
- Runs `model.encode(texts, normalize_embeddings=True, batch_size=32)`
- `normalize_embeddings=True` means vectors have length 1, so cosine similarity equals dot product
- Returns a list of lists of floats (one 768-dim vector per text)

All CPU-intensive work runs via `asyncio.to_thread()` — this moves blocking work off the async event loop into a thread pool, so FastAPI can handle other requests while Whisper or the embedding model is running.

---

## LLM Service (`services/llm.py`)

**Provider switching** via `llm_provider` config:
- `ollama` → `ChatOllama` with `llama3.1:8b` (local, free, needs Ollama running)
- `openai` → `ChatOpenAI` with `gpt-4o-mini` (extraction) or `gpt-4o` (query)
- `anthropic` → `ChatAnthropic` with `claude-haiku-4-5` (extraction) or `claude-sonnet-4-6` (query)

All three use LangChain's interface (`BaseChatModel.ainvoke([HumanMessage(...)])`), so the rest of the code doesn't care which provider is active.

**`extract_insights(transcript)`**:
- Loads `prompts/extract_insights.txt`
- Substitutes `{transcript}` with the actual transcript
- Calls the LLM
- Parses the response as JSON (with a fallback regex to find `{...}` if the LLM adds surrounding text)

**`answer_query(question, context)`**:
- Loads `prompts/query_meetings.txt`
- Substitutes `{context}` (the retrieved transcript chunks) and `{question}`
- Returns the LLM's text answer

---

## LLM Prompts (`prompts/`)

**`extract_insights.txt`** — tells the LLM to return ONLY valid JSON with no explanation. The schema has `summary`, `action_items`, `decisions`, `topics`. Enforcing JSON output is necessary because you need to save structured data to the database.

**`query_meetings.txt`** — tells the LLM to answer based ONLY on provided excerpts (RAG pattern). If the answer isn't in the excerpts, say so. This prevents hallucination.

**`extract_entities.txt`** — extracts people, companies, projects from a transcript. Intended for the memory system (not yet fully wired in).

---

## Semantic Search (`services/query.py`)

This is the "ask a question across all your meetings" feature.

```python
async def semantic_search(req: QueryRequest, user_id: uuid.UUID, db: AsyncSession) -> QueryResponse:
    # 1. Embed the user's question
    query_embedding = await embed_text(req.q)
    
    # 2. Find the 8 most similar chunks using pgvector's <=> operator (cosine distance)
    base_query = (
        select(Chunk.id, Chunk.meeting_id, Chunk.text, Chunk.start_time)
        .join(Meeting, Chunk.meeting_id == Meeting.id)
        .where(Meeting.user_id == user_id)
        .order_by(text(f"embedding <=> '{embedding_str}'::vector"))
        .limit(SIMILARITY_LIMIT)
    )
    
    # 3. Build context string from retrieved chunks
    # 4. Ask LLM to answer using that context
    answer = await answer_query(req.q, "\n".join(context_parts))
```

This is the **RAG (Retrieval-Augmented Generation)** pattern:
1. Convert the question to a vector
2. Find the most semantically similar transcript snippets (not keyword match — meaning match)
3. Feed those snippets to the LLM as context
4. LLM generates an answer grounded in your actual meetings

The `<=>` operator is pgvector's cosine distance. The IVFFlat index on `chunks.embedding` makes this fast.

---

## Object Storage (`utils/storage.py`)

Uses `boto3` (the AWS SDK) pointed at MinIO — MinIO implements the S3 API, so the same code works with real S3 in production.

Three operations:
- `upload_file(key, data, content_type)` — `put_object` to the bucket
- `download_file(key)` — `get_object`, reads the full body
- `get_presigned_url(key, expires_in=3600)` — generates a signed URL valid for 1 hour, used to let the web app serve audio without proxying through the API

The client is lazily initialized (singleton pattern with a global `_client = None`).

---

## Chrome Extension (`apps/extension/`)

Built with [Plasmo](https://docs.plasmo.com/), a framework for Chrome extensions with React and TypeScript.

### `background.ts` — The Service Worker

This is the brain of the extension. It runs persistently in the background.

**Tab detection:**
```typescript
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url && MEET_PATTERN.test(tab.url)) {
    handleMeetTabOpened(tabId);
  }
});
```

When a Google Meet URL fully loads, it automatically starts recording.

**Recording flow:**
1. `handleMeetTabOpened` — gets auth token from `chrome.storage.local`, calls API to create a meeting record, calls `startRecording`
2. `startRecording` — uses `chrome.tabCapture.getMediaStreamId` to get permission to capture the tab's audio, then creates a `MediaRecorder` with `audio/webm;codecs=opus`
3. Opens a WebSocket connection to the backend
4. `setInterval(flushChunk, 5000)` — every 5 seconds, converts buffered audio blobs to base64 and sends over WebSocket
5. `stopRecording` — flushes remaining audio, sends `{"type": "stop"}`, closes WebSocket

**Communication with other extension pages:**
```typescript
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "STOP_RECORDING") stopRecording("user requested");
});
```

### `content.ts` — The Content Script

Injected into every `meet.google.com` page. Watches the DOM for participant tile elements using a `MutationObserver`. When participants change, it waits 2 seconds (debounce), extracts names, and sends them to the background service worker. Used for speaker diarization (Phase 2).

### `popup/index.tsx` — Settings Popup

A small React form that saves two values to `chrome.storage.local`:
- `apiUrl` — which backend to talk to
- `accessToken` — the JWT to authenticate with

This is how the extension knows who you are. You paste your token from the web app.

### `sidepanel/index.tsx` — Side Panel UI

Shows recording status during a meeting. Listens to `chrome.storage.onChanged` — whenever `recordingState` changes in storage (the background sets it when recording starts/stops), the UI updates automatically. Has a "Stop recording" button that sends `STOP_RECORDING` to the background.

---

## Next.js Web App (`apps/web/`)

### Authentication (`lib/auth.ts`)

Uses **NextAuth** with two providers:
- **Google OAuth** — for sign in with Google
- **Credentials** — for email/password (calls the FastAPI `/auth/login` endpoint)

The `jwt` callback stores the FastAPI access token inside the NextAuth JWT. The `session` callback exposes it as `session.accessToken`. This bridges NextAuth's session management with the FastAPI JWT system.

### API Client (`lib/api.ts`)

A thin wrapper around `fetch`. Every call goes to `NEXT_PUBLIC_API_URL/api/v1`. If the response isn't OK, it parses the JSON error detail and throws. Organized into three groups:

```typescript
authApi.register(email, password, name)
authApi.login(email, password)

meetingsApi.list(token, status?)
meetingsApi.get(token, id)
meetingsApi.transcript(token, id)

queryApi.ask(token, question, meetingIds?)
```

### State Management (`lib/store.ts`)

Uses **Zustand** — a minimal state library. Currently just holds the `accessToken`:

```typescript
export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  setAccessToken: (token) => set({ accessToken: token }),
}));
```

### Key Pages

**`/meetings`** — lists all meetings with their status badges. Clicking one goes to `/meetings/[id]`.

**`/meetings/[id]`** — shows the `MeetingDetail` component:
- Two tabs: "Summary" and "Transcript"
- Summary tab shows insights (summary paragraph, action items list, decisions, topics chips)
- Transcript tab loads lazily (only when that tab is active and meeting is `"done"`) using `useQuery` from TanStack Query
- Shows a "Processing..." banner while status is `"processing"`

**`/query`** — shows the `QueryInterface` component:
- Text input for asking questions
- Submits to `/query` endpoint
- Displays the LLM's answer and source chunks (each linked to the meeting it came from)

---

## Data Flow: End to End

Here's what happens from you joining a Google Meet to being able to ask "what did we decide?":

```
1. You open meet.google.com
   → Extension detects the URL
   → Creates meeting record via POST /api/v1/meetings
   → Captures tab audio with MediaRecorder

2. Every 5 seconds while meeting runs
   → Audio chunks sent as base64 over WebSocket
   → Server buffers them in memory

3. Meeting ends (tab closes or you click Stop)
   → Extension sends {"type": "stop"}
   → Server concatenates all audio bytes
   → Uploads to MinIO: audio/<uuid>/recording.webm
   → Sets meeting.status = "processing"
   → Fires process_meeting(meeting_id) into Celery queue

4. Celery worker picks up the job
   Step 1 — Transcription:
     Downloads audio from MinIO
     Runs faster-whisper (speech-to-text)
     Uploads transcript JSON to MinIO
   
   Step 2 — Embedding:
     Downloads transcript JSON
     Runs each segment through nomic-embed-text
     Stores Chunk rows with 768-dim vectors in PostgreSQL

   Step 3 — Insights extraction:
     Downloads transcript JSON
     Concatenates all text
     Sends to LLM with extract_insights prompt
     Saves MeetingInsights row

   Step 4 — Mark done:
     meeting.status = "done"

5. You open the web app → /meetings
   → Sees the meeting listed as "done"
   → Clicks it → sees summary, action items, decisions

6. You go to /query and type "what did we decide about pricing?"
   → Web app POSTs {"q": "what did we decide about pricing?"}
   → API embeds your question (same 768-dim model)
   → PostgreSQL cosine similarity search finds top 8 chunks
   → Those chunks become context for the LLM
   → LLM answers grounded in your real meeting content
   → You see the answer with links to source meetings
```

---

## Key Technologies and Why They're Used

| Technology | Why |
|---|---|
| **FastAPI** | Async Python web framework — handles many requests concurrently without threads |
| **SQLAlchemy async** | Async ORM — database calls don't block the event loop |
| **Alembic** | Schema migrations — controlled, versioned database changes |
| **Celery + Redis** | Background job queue — long tasks (transcription, LLM) run outside the HTTP request lifecycle |
| **PostgreSQL + pgvector** | Stores vectors alongside regular data — enables SQL-level vector similarity search |
| **MinIO** | S3-compatible local storage — audio and transcript files aren't stored in the database |
| **faster-whisper** | Efficient CPU/GPU speech-to-text from OpenAI Whisper weights, faster than the original |
| **sentence-transformers** | Converts text to semantic vectors — "pricing discussion" ≈ "cost debate" at the vector level |
| **LangChain** | Unified interface to switch between Ollama/OpenAI/Anthropic without changing business logic |
| **JWT** | Stateless auth — no server-side session storage needed |
| **Plasmo** | Chrome extension framework — handles bundling TypeScript/React for extension contexts |
| **NextAuth** | Handles OAuth flows and session management in Next.js |
| **TanStack Query** | Smart data fetching with caching and lazy loading in React |
| **Zustand** | Minimal global state — lighter than Redux for simple cases |

---

## Common Patterns to Learn From

**Dependency Injection in FastAPI:**
```python
@router.get("/{id}")
async def get_one(id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
```
FastAPI resolves `Depends(...)` by calling the function and injecting the result. `get_db` and `get_current_user` are called automatically for every request that needs them.

**Async to sync bridge (Celery tasks):**
```python
@celery_app.task(bind=True, max_retries=3)
def my_task(self, meeting_id: str):
    async def _work():
        async with AsyncSessionFactory() as db:
            ...
    try:
        asyncio.get_event_loop().run_until_complete(_work())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
```

**Singleton lazy init (expensive models):**
```python
_model = None
def get_model():
    global _model
    if _model is None:
        _model = ExpensiveModel()
    return _model
```

**Pydantic for validation and serialization:**
- Input schemas (e.g., `MeetingCreate`) validate incoming JSON
- Output schemas (e.g., `MeetingResponse`) control what fields are returned
- `from_attributes = True` in `Config` allows reading from SQLAlchemy model instances directly

**RAG (Retrieval-Augmented Generation):**
The query pipeline is a textbook RAG implementation: embed the question → vector search → feed top-K results as context → LLM generates a grounded answer.
