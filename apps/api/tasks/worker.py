"""In-process meeting pipeline for the local desktop build.

Replaces the Redis/Celery chain with a single background task fed by an
asyncio.Queue. Jobs run sequentially in the app's own event loop:

    transcribe → embed + store chunks → extract insights → mark done

Reuses the same service functions the Celery tasks used. For a single-user
local app this is simpler and removes the Redis dependency entirely.
"""
import asyncio
import json
import logging
import uuid

from sqlalchemy import text

from database import CHUNK_VEC_TABLE, AsyncSessionFactory, pack_vector

logger = logging.getLogger(__name__)

_queue: asyncio.Queue[str] | None = None
_task: asyncio.Task | None = None


def enqueue(meeting_id: str) -> None:
    """Schedule a meeting for processing. Safe to call from request handlers."""
    if _queue is None:
        raise RuntimeError("worker not started; call start_worker() in app lifespan")
    _queue.put_nowait(meeting_id)


def start_worker() -> None:
    global _queue, _task
    if _task is not None:
        return
    _queue = asyncio.Queue()
    _task = asyncio.create_task(_run_loop(), name="meetbuddy-pipeline-worker")


async def stop_worker() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None


async def _run_loop() -> None:
    assert _queue is not None
    while True:
        meeting_id = await _queue.get()
        try:
            await _process(meeting_id)
        except Exception:
            logger.exception("pipeline failed for meeting %s", meeting_id)
            await _mark_failed(meeting_id)
        finally:
            _queue.task_done()


# ── Pipeline steps ────────────────────────────────────────────────────────────

async def _process(meeting_id: str) -> None:
    await _transcribe(meeting_id)
    await _embed_and_store(meeting_id)
    await _extract_insights(meeting_id)
    await _mark_done(meeting_id)
    logger.info("pipeline complete for meeting %s", meeting_id)


async def _transcribe(meeting_id: str) -> None:
    from models.meeting import Meeting
    from services.transcription import store_transcript, transcribe_audio_file
    from utils.storage import file_exists

    async with AsyncSessionFactory() as db:
        meeting = await db.get(Meeting, uuid.UUID(meeting_id))
        if not meeting or not meeting.audio_url:
            logger.warning("meeting %s has no audio_url, skipping", meeting_id)
            return
        meeting.status = "processing"
        await db.commit()

        tab_segments = await transcribe_audio_file(meeting.audio_url)
        mic_key = meeting.audio_url.replace("/tab.webm", "/mic.webm")
        mic_segments: list[dict] = []
        if mic_key != meeting.audio_url and await asyncio.to_thread(file_exists, mic_key):
            try:
                mic_segments = await transcribe_audio_file(mic_key)
            except Exception:
                logger.exception("mic transcription failed for %s", meeting_id)

        all_segments = sorted(tab_segments + mic_segments, key=lambda s: s["start"])
        transcript_key = await store_transcript(uuid.UUID(meeting_id), all_segments)
        meeting.transcript_url = transcript_key
        await db.commit()
        logger.info("transcribed meeting %s — %d segments", meeting_id, len(all_segments))


async def _embed_and_store(meeting_id: str) -> None:
    from models.meeting import Chunk, Meeting
    from services.transcription import embed_texts
    from utils.storage import download_file

    async with AsyncSessionFactory() as db:
        meeting = await db.get(Meeting, uuid.UUID(meeting_id))
        if not meeting or not meeting.transcript_url:
            return
        raw = await asyncio.to_thread(download_file, meeting.transcript_url)
        segments = json.loads(raw)
        if not segments:
            return

        embeddings = await embed_texts([seg["text"] for seg in segments])
        for seg, emb in zip(segments, embeddings):
            chunk = Chunk(
                meeting_id=uuid.UUID(meeting_id),
                text=seg["text"],
                start_time=seg["start"],
                end_time=seg["end"],
            )
            db.add(chunk)
            await db.flush()  # populate chunk.id
            await db.execute(
                text(f"INSERT INTO {CHUNK_VEC_TABLE}(chunk_id, embedding) VALUES (:c, :e)"),
                {"c": str(chunk.id), "e": pack_vector(emb)},
            )
        await db.commit()
        logger.info("stored %d chunks for meeting %s", len(segments), meeting_id)


async def _extract_insights(meeting_id: str) -> None:
    from models.meeting import Meeting, MeetingInsights
    from services.llm import extract_insights
    from utils.storage import download_file

    async with AsyncSessionFactory() as db:
        meeting = await db.get(Meeting, uuid.UUID(meeting_id))
        if not meeting or not meeting.transcript_url:
            return
        raw = await asyncio.to_thread(download_file, meeting.transcript_url)
        segments = json.loads(raw)
        transcript_text = " ".join(seg["text"] for seg in segments).strip()

        if len(transcript_text.split()) < 10:
            logger.warning("transcript too short for insights (%d words)", len(transcript_text.split()))
            data = {"summary": None, "action_items": [], "decisions": [], "topics": []}
        else:
            data = await extract_insights(transcript_text)

        db.add(MeetingInsights(
            meeting_id=uuid.UUID(meeting_id),
            summary=data.get("summary"),
            action_items=data.get("action_items", []),
            decisions=data.get("decisions", []),
            topics=data.get("topics", []),
            raw_llm_output=data,
        ))
        await db.commit()
        logger.info("insights extracted for meeting %s", meeting_id)


async def _mark_done(meeting_id: str) -> None:
    await _set_status(meeting_id, "done")


async def _mark_failed(meeting_id: str) -> None:
    try:
        await _set_status(meeting_id, "failed")
    except Exception:
        logger.exception("could not mark meeting %s failed", meeting_id)


async def _set_status(meeting_id: str, status: str) -> None:
    from models.meeting import Meeting

    async with AsyncSessionFactory() as db:
        meeting = await db.get(Meeting, uuid.UUID(meeting_id))
        if meeting:
            meeting.status = status
            await db.commit()
