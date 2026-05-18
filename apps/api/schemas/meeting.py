import uuid
from datetime import datetime

from pydantic import BaseModel


class MeetingCreate(BaseModel):
    platform: str
    started_at: datetime
    title: str | None = None


class MeetingUpdate(BaseModel):
    title: str | None = None
    status: str | None = None
    ended_at: datetime | None = None
    duration_secs: int | None = None


class ActionItem(BaseModel):
    text: str
    owner: str | None = None
    due_date: str | None = None


class Decision(BaseModel):
    text: str
    context: str | None = None


class Topic(BaseModel):
    name: str
    duration_secs: int | None = None


class InsightsResponse(BaseModel):
    summary: str | None
    action_items: list[ActionItem]
    decisions: list[Decision]
    topics: list[Topic]
    participants: list[dict]


class MeetingResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    platform: str
    started_at: datetime
    ended_at: datetime | None
    duration_secs: int | None
    status: str
    audio_url: str | None = None
    created_at: datetime
    insights: InsightsResponse | None = None

    class Config:
        from_attributes = True


class TranscriptChunk(BaseModel):
    id: uuid.UUID
    text: str
    start_time: float
    end_time: float
    speaker_label: str | None = None
    speaker_name: str | None = None


class QueryRequest(BaseModel):
    q: str
    meeting_ids: list[uuid.UUID] = []


class QuerySource(BaseModel):
    chunk_id: uuid.UUID
    meeting_id: uuid.UUID
    text: str
    start_time: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[QuerySource]
