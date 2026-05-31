"""WebSocket endpoint for live extension → server communication during recording."""
import asyncio
import base64
import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import AsyncSessionFactory
from models.meeting import Meeting
from utils.storage import upload_file

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

AUDIO_CHUNK_STORE: dict[str, dict[str, list[bytes]]] = {}


@router.websocket("/ws/{meeting_id}")
async def meeting_ws(websocket: WebSocket, meeting_id: uuid.UUID):
    await websocket.accept()
    key = str(meeting_id)
    AUDIO_CHUNK_STORE[key] = {"tab": [], "mic": []}

    try:
        await websocket.send_text(json.dumps({"type": "status", "message": "Connected"}))

        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            if msg.get("type") == "chunk":
                audio_bytes = base64.b64decode(msg["audio_b64"])
                source = msg.get("source", "tab")
                # "mixed" falls back to the "tab" bucket
                bucket = AUDIO_CHUNK_STORE[key].get(source, AUDIO_CHUNK_STORE[key]["tab"])
                bucket.append(audio_bytes)

            elif msg.get("type") == "stop":
                streams = AUDIO_CHUNK_STORE.pop(key, {"tab": [], "mic": []})
                await _finalize_recording(meeting_id, streams)
                await websocket.send_text(json.dumps({"type": "status", "message": "Processing started"}))
                break

    except WebSocketDisconnect:
        streams = AUDIO_CHUNK_STORE.pop(key, {"tab": [], "mic": []})
        if streams["tab"] or streams["mic"]:
            await _finalize_recording(meeting_id, streams)
    except Exception:
        logger.exception("Unexpected error in WebSocket handler for meeting %s", meeting_id)
        AUDIO_CHUNK_STORE.pop(key, None)


async def _finalize_recording(meeting_id: uuid.UUID, streams: dict[str, list[bytes]]) -> None:
    tab_data = b"".join(streams.get("tab", []))
    mic_data = b"".join(streams.get("mic", []))

    logger.info(
        "Finalizing meeting %s — tab=%d bytes mic=%d bytes",
        meeting_id, len(tab_data), len(mic_data),
    )

    if not tab_data and not mic_data:
        logger.warning("Meeting %s has no audio data — marking as failed", meeting_id)
        async with AsyncSessionFactory() as db:
            meeting = await db.get(Meeting, meeting_id)
            if meeting:
                meeting.status = "failed"
                await db.commit()
        return

    # Upload runs synchronously in a thread so it doesn't block the event loop.
    if tab_data:
        await asyncio.to_thread(upload_file, f"audio/{meeting_id}/tab.webm", tab_data, "audio/webm")
    if mic_data:
        await asyncio.to_thread(upload_file, f"audio/{meeting_id}/mic.webm", mic_data, "audio/webm")

    primary_key = f"audio/{meeting_id}/tab.webm" if tab_data else f"audio/{meeting_id}/mic.webm"

    async with AsyncSessionFactory() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting:
            meeting.audio_url = primary_key
            meeting.status = "processing"
            await db.commit()

    try:
        from tasks.pipeline import process_meeting
        await asyncio.to_thread(process_meeting, str(meeting_id))
        logger.info("Queued pipeline for meeting %s", meeting_id)
    except Exception:
        logger.exception("Failed to queue Celery pipeline for meeting %s", meeting_id)
