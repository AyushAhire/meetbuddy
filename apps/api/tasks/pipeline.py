"""
Celery processing pipeline: transcribe → store → embed → extract insights → mark done.
Each task is idempotent — safe to retry.
"""
import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from celery import chain
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tasks.celery_app import celery_app

# Import all models so SQLAlchemy metadata is complete and FK references resolve
import models.user  # noqa: F401
import models.meeting  # noqa: F401
import models.memory  # noqa: F401

logger = logging.getLogger(__name__)


def _run(coro):
    """Run async code from a sync Celery task."""
    return asyncio.run(coro)


@asynccontextmanager
async def task_db():
    """Fresh DB session per Celery task.

    asyncio.run() creates a new event loop for every task, which invalidates
    any connection pool bound to a previous loop. NullPool avoids pooling
    entirely so there are no cross-loop futures.
    """
    from config import settings
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


def process_meeting(meeting_id: str) -> None:
    """Entry point — kick off the full pipeline as a Celery chain."""
    pipeline = chain(
        transcribe_audio.si(meeting_id),
        store_and_embed_chunks.si(meeting_id),
        extract_insights_task.si(meeting_id),
        mark_complete.si(meeting_id),
    )
    pipeline.delay()


@celery_app.task(name="tasks.transcribe_audio", bind=True, max_retries=3)
def transcribe_audio(self, meeting_id: str) -> None:
    """Download audio, run faster-whisper, persist segments to DB."""
    from models.meeting import Meeting
    from services.transcription import store_transcript, transcribe_audio_file

    async def _run_async():
        async with task_db() as db:
            meeting = await db.get(Meeting, uuid.UUID(meeting_id))
            if not meeting or not meeting.audio_url:
                logger.warning("Meeting %s has no audio_url, skipping transcription", meeting_id)
                return

            meeting.status = "processing"
            await db.commit()

            tab_segments = await transcribe_audio_file(meeting.audio_url)
            logger.info("Tab transcription: %d segments", len(tab_segments))

            mic_key = meeting.audio_url.replace("/tab.webm", "/mic.webm")
            mic_segments: list[dict] = []
            try:
                from utils.storage import file_exists
                if await asyncio.to_thread(file_exists, mic_key):
                    mic_segments = await transcribe_audio_file(mic_key)
                    logger.info("Mic transcription: %d segments", len(mic_segments))
            except Exception:
                pass

            all_segments = sorted(tab_segments + mic_segments, key=lambda s: s["start"])

            transcript_key = await store_transcript(uuid.UUID(meeting_id), all_segments)
            meeting.transcript_url = transcript_key
            await db.commit()
            logger.info("Transcription done for meeting %s — %d total segments", meeting_id, len(all_segments))

    try:
        _run(_run_async())
    except Exception as exc:
        logger.exception("transcribe_audio failed for %s", meeting_id)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.store_and_embed_chunks", bind=True, max_retries=3)
def store_and_embed_chunks(self, meeting_id: str) -> None:
    """Load transcript from storage, create Chunk rows with embeddings."""
    import json

    from models.meeting import Chunk, Meeting
    from services.transcription import embed_texts
    from utils.storage import download_file

    async def _run_async():
        async with task_db() as db:
            meeting = await db.get(Meeting, uuid.UUID(meeting_id))
            if not meeting or not meeting.transcript_url:
                return

            raw = await asyncio.to_thread(download_file, meeting.transcript_url)
            segments = json.loads(raw)
            if not segments:
                return

            texts = [seg["text"] for seg in segments]
            embeddings = await embed_texts(texts)

            for seg, emb in zip(segments, embeddings):
                chunk = Chunk(
                    meeting_id=uuid.UUID(meeting_id),
                    text=seg["text"],
                    start_time=seg["start"],
                    end_time=seg["end"],
                    embedding=emb,
                )
                db.add(chunk)
            await db.commit()
            logger.info("Stored %d chunks for meeting %s", len(segments), meeting_id)

    try:
        _run(_run_async())
    except Exception as exc:
        logger.exception("store_and_embed_chunks failed for %s", meeting_id)
        raise self.retry(exc=exc, countdown=30)


@celery_app.task(name="tasks.extract_insights_task", bind=True, max_retries=3)
def extract_insights_task(self, meeting_id: str) -> None:
    """Run LLM extraction and store results in meeting_insights table."""
    import json

    from models.meeting import Meeting, MeetingInsights
    from services.llm import extract_insights
    from utils.storage import download_file

    async def _run_async():
        async with task_db() as db:
            meeting = await db.get(Meeting, uuid.UUID(meeting_id))
            if not meeting or not meeting.transcript_url:
                return

            raw = await asyncio.to_thread(download_file, meeting.transcript_url)
            segments = json.loads(raw)
            transcript_text = " ".join(seg["text"] for seg in segments).strip()

            if len(transcript_text.split()) < 10:
                logger.warning("Transcript too short for insights (%d words), skipping LLM", len(transcript_text.split()))
                insights_data = {"summary": None, "action_items": [], "decisions": [], "topics": []}
            else:
                insights_data = await extract_insights(transcript_text)

            insights = MeetingInsights(
                meeting_id=uuid.UUID(meeting_id),
                summary=insights_data.get("summary"),
                action_items=insights_data.get("action_items", []),
                decisions=insights_data.get("decisions", []),
                topics=insights_data.get("topics", []),
                raw_llm_output=insights_data,
            )
            db.add(insights)
            await db.commit()
            logger.info("Insights extracted for meeting %s", meeting_id)

    try:
        _run(_run_async())
    except Exception as exc:
        logger.exception("extract_insights_task failed for %s", meeting_id)
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="tasks.mark_complete", bind=True, max_retries=3)
def mark_complete(self, meeting_id: str) -> None:
    """Set meeting status to 'done'."""
    from models.meeting import Meeting

    async def _run_async():
        async with task_db() as db:
            meeting = await db.get(Meeting, uuid.UUID(meeting_id))
            if meeting:
                meeting.status = "done"
                await db.commit()
                logger.info("Meeting %s marked as done", meeting_id)

    try:
        _run(_run_async())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=10)


import asyncio  # noqa: E402 — needed inside sync Celery tasks
