import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str | None] = mapped_column(String)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_secs: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, nullable=False, default="recording")
    audio_url: Mapped[str | None] = mapped_column(String)
    transcript_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    speakers: Mapped[list["Speaker"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="meeting", cascade="all, delete-orphan")
    insights: Mapped["MeetingInsights | None"] = relationship(back_populates="meeting", uselist=False, cascade="all, delete-orphan")


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship(back_populates="speakers")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"))
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("speakers.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(768))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship(back_populates="chunks")


class MeetingInsights(Base):
    __tablename__ = "meeting_insights"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    action_items: Mapped[list] = mapped_column(JSONB, default=list)
    decisions: Mapped[list] = mapped_column(JSONB, default=list)
    topics: Mapped[list] = mapped_column(JSONB, default=list)
    participants: Mapped[list] = mapped_column(JSONB, default=list)
    raw_llm_output: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship(back_populates="insights")
