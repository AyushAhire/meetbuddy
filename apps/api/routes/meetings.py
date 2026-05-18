import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from schemas.meeting import MeetingCreate, MeetingResponse, MeetingUpdate, TranscriptChunk
from services.auth import get_current_user
from services.meeting import (
    create_meeting,
    delete_meeting,
    get_meeting,
    get_transcript,
    list_meetings,
    update_meeting,
)
from utils.storage import get_presigned_url

router = APIRouter(prefix="/meetings", tags=["meetings"])


@router.get("", response_model=list[MeetingResponse])
async def list_all(
    status: str | None = Query(None),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_meetings(current_user.id, db, status_filter=status, limit=limit, offset=offset)


@router.post("", response_model=MeetingResponse, status_code=201)
async def create(
    req: MeetingCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await create_meeting(current_user.id, req, db)


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_one(
    meeting_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_meeting(meeting_id, current_user.id, db)


@router.patch("/{meeting_id}", response_model=MeetingResponse)
async def update(
    meeting_id: uuid.UUID,
    req: MeetingUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_meeting(meeting_id, current_user.id, req, db)


@router.delete("/{meeting_id}", status_code=204)
async def delete(
    meeting_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_meeting(meeting_id, current_user.id, db)


@router.get("/{meeting_id}/transcript", response_model=list[TranscriptChunk])
async def transcript(
    meeting_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_transcript(meeting_id, current_user.id, db)


@router.get("/{meeting_id}/audio")
async def audio_url(
    meeting_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    meeting = await get_meeting(meeting_id, current_user.id, db)
    if not meeting.audio_url:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No audio available")
    url = get_presigned_url(meeting.audio_url)
    return {"url": url}
