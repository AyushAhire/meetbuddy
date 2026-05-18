from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.auth import router as auth_router
from routes.meetings import router as meetings_router
from routes.query import router as query_router
from routes.upload import router as upload_router
from routes.websocket import router as ws_router

app = FastAPI(title="MeetBuddy API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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


@app.get("/health")
async def health():
    return {"status": "ok"}
