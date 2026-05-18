import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.meeting import Chunk, Meeting, MeetingInsights, Speaker
from schemas.meeting import MeetingCreate, MeetingResponse, MeetingUpdate, TranscriptChunk


async def create_meeting(user_id: uuid.UUID, req: MeetingCreate, db: AsyncSession) -> Meeting:
    meeting = Meeting(
        user_id=user_id,
        title=req.title,
        platform=req.platform,
        started_at=req.started_at,
        status="recording",
    )
    db.add(meeting)
    await db.flush()
    return await db.scalar(
        select(Meeting)
        .where(Meeting.id == meeting.id)
        .options(selectinload(Meeting.insights))
    )


async def list_meetings(
    user_id: uuid.UUID,
    db: AsyncSession,
    status_filter: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Meeting]:
    query = (
        select(Meeting)
        .where(Meeting.user_id == user_id)
        .options(selectinload(Meeting.insights))
        .order_by(Meeting.started_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter:
        query = query.where(Meeting.status == status_filter)
    result = await db.execute(query)
    return list(result.scalars())


async def get_meeting(meeting_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> Meeting:
    meeting = await db.scalar(
        select(Meeting)
        .where(Meeting.id == meeting_id, Meeting.user_id == user_id)
        .options(selectinload(Meeting.insights))
    )
    if not meeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found")
    return meeting


async def update_meeting(
    meeting_id: uuid.UUID, user_id: uuid.UUID, req: MeetingUpdate, db: AsyncSession
) -> Meeting:
    meeting = await get_meeting(meeting_id, user_id, db)
    for field, value in req.model_dump(exclude_none=True).items():
        setattr(meeting, field, value)
    if req.ended_at and meeting.started_at:
        meeting.duration_secs = int((req.ended_at - meeting.started_at).total_seconds())
    return meeting


async def delete_meeting(meeting_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> None:
    meeting = await get_meeting(meeting_id, user_id, db)
    await db.delete(meeting)


async def get_transcript(meeting_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession) -> list[TranscriptChunk]:
    await get_meeting(meeting_id, user_id, db)

    result = await db.execute(
        select(Chunk, Speaker)
        .outerjoin(Speaker, Chunk.speaker_id == Speaker.id)
        .where(Chunk.meeting_id == meeting_id)
        .order_by(Chunk.start_time)
    )
    rows = result.all()

    return [
        TranscriptChunk(
            id=chunk.id,
            text=chunk.text,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
            speaker_label=speaker.label if speaker else None,
            speaker_name=speaker.name if speaker else None,
        )
        for chunk, speaker in rows
    ]
