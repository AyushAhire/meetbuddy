import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from database import AsyncSessionFactory, init_db
from routes.auth import router as auth_router
from routes.meetings import router as meetings_router
from routes.query import router as query_router
from routes.upload import router as upload_router
from routes.websocket import router as ws_router
from tasks.worker import start_worker, stop_worker
from utils.storage import open_file_path

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    if settings.single_user_mode:
        from services.auth import get_or_create_local_user
        async with AsyncSessionFactory() as db:
            await get_or_create_local_user(db)
            await db.commit()
    start_worker()
    logger.info("MeetBuddy API ready (db=%s, single_user=%s)", settings.database_url, settings.single_user_mode)
    try:
        yield
    finally:
        await stop_worker()


app = FastAPI(title="MeetBuddy API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                   "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_origin_regex=r"chrome-extension://[a-z]+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(meetings_router, prefix=API_PREFIX)
app.include_router(upload_router, prefix=API_PREFIX)
app.include_router(query_router, prefix=API_PREFIX)
app.include_router(ws_router, prefix=API_PREFIX)


@app.get("/files/{key:path}")
async def serve_file(key: str):
    """Serve a locally-stored blob (audio playback, etc.)."""
    try:
        path = open_file_path(key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)


@app.get("/health")
async def health():
    return {"status": "ok"}


# Serve the exported dashboard SPA (registered last so API/file routes win).
# html=True makes directory paths resolve to their index.html, which matches
# the Next.js `trailingSlash` export layout (/meetings/ → meetings/index.html).
if os.path.isdir(settings.web_dir):
    app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="dashboard")
    logger.info("Serving dashboard from %s", settings.web_dir)
else:
    logger.warning("Dashboard not built at %s — run `pnpm build` in apps/web", settings.web_dir)
