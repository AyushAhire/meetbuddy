import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
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

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship(back_populates="speakers")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="CASCADE"))
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("speakers.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    # Embeddings live in the sqlite-vec `chunk_vec` virtual table keyed by chunk id.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship(back_populates="chunks")


class MeetingInsights(Base):
    __tablename__ = "meeting_insights"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("meetings.id", ondelete="CASCADE"), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    participants: Mapped[list] = mapped_column(JSON, default=list)
    raw_llm_output: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    meeting: Mapped["Meeting"] = relationship(back_populates="insights")
