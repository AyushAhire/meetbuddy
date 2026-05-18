"""WebSocket endpoint for live extension → server communication during recording."""
import base64
import json
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from database import AsyncSessionFactory
from models.meeting import Meeting
from utils.storage import upload_file

router = APIRouter(tags=["websocket"])

# Separate tab (remote participants) and mic (local speaker) streams per meeting
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
                source = msg.get("source", "tab")  # "tab" | "mic"
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


async def _finalize_recording(meeting_id: uuid.UUID, streams: dict[str, list[bytes]]) -> None:
    tab_data = b"".join(streams.get("tab", []))
    mic_data = b"".join(streams.get("mic", []))

    if not tab_data and not mic_data:
        return

    if tab_data:
        upload_file(f"audio/{meeting_id}/tab.webm", tab_data, "audio/webm")
    if mic_data:
        upload_file(f"audio/{meeting_id}/mic.webm", mic_data, "audio/webm")

    # audio_url points to tab stream (primary); pipeline also checks for mic stream
    primary_key = f"audio/{meeting_id}/tab.webm" if tab_data else f"audio/{meeting_id}/mic.webm"

    async with AsyncSessionFactory() as db:
        meeting = await db.get(Meeting, meeting_id)
        if meeting:
            meeting.audio_url = primary_key
            meeting.status = "processing"
            await db.commit()

    from tasks.pipeline import process_meeting
    process_meeting(str(meeting_id))
