import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.meeting import Meeting
from models.user import User
from services.auth import get_current_user
from utils.storage import upload_file

router = APIRouter(prefix="/upload", tags=["upload"])

AUDIO_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB max per chunk


class CompleteUploadRequest(BaseModel):
    meeting_id: uuid.UUID


@router.post("/audio")
async def upload_audio(
    file: UploadFile,
    meeting_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept audio file from extension and store in object storage."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")

    data = await file.read()
    key = f"audio/{meeting_id}/{file.filename or 'recording.webm'}"
    upload_file(key, data, file.content_type or "audio/webm")

    meeting.audio_url = key
    await db.commit()
    return {"upload_id": key}


@router.post("/complete")
async def complete_upload(
    req: CompleteUploadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Signal that upload is done — trigger processing pipeline."""
    meeting = await db.get(Meeting, req.meeting_id)
    if not meeting or meeting.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    if not meeting.audio_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No audio uploaded")

    meeting.status = "processing"
    await db.commit()

    from tasks.pipeline import process_meeting
    process_meeting(str(req.meeting_id))

    return {"status": "processing", "meeting_id": str(req.meeting_id)}
