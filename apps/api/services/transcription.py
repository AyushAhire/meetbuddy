import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from config import settings
from utils.storage import download_file, upload_file

_whisper_model = None
_embed_model = None


# ── Local faster-whisper ──────────────────────────────────────────────────────

def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _whisper_model


def _run_local_whisper(path: str) -> list[dict]:
    model = _get_whisper()
    segments, _ = model.transcribe(
        path,
        beam_size=5,
        condition_on_previous_text=False,
        no_speech_threshold=0.7,
        task="transcribe",
    )
    return [
        {"text": seg.text.strip(), "start": seg.start, "end": seg.end}
        for seg in segments
        if seg.text.strip()
    ]


# ── Groq Whisper (OpenAI-compatible API) ─────────────────────────────────────

async def _transcribe_with_groq(audio_bytes: bytes, suffix: str) -> list[dict]:
    """Send audio to Groq's Whisper API and return segment dicts."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )

    # Groq has a 25 MB file size limit
    size_mb = len(audio_bytes) / (1024 * 1024)
    if size_mb > 24:
        raise ValueError(f"Audio file is {size_mb:.1f} MB — exceeds Groq's 25 MB limit. "
                         "Split the recording or use a local model.")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            response = await client.audio.transcriptions.create(
                model=settings.groq_whisper_model,
                file=(Path(tmp_path).name, f, "audio/webm"),
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                text = (seg.text if isinstance(seg.text, str) else "").strip()
                if text:
                    segments.append({
                        "text": text,
                        "start": float(seg.start),
                        "end": float(seg.end),
                    })
        elif hasattr(response, "text") and response.text:
            # Fallback: no segment timestamps, put everything at t=0
            segments = [{"text": response.text.strip(), "start": 0.0, "end": 0.0}]

        return segments
    finally:
        Path(tmp_path).unlink(missing_ok=True)


# ── Public interface ──────────────────────────────────────────────────────────

async def transcribe_audio_file(audio_key: str) -> list[dict]:
    """Download audio from storage, transcribe, return list of segment dicts."""
    import logging
    logger = logging.getLogger(__name__)

    audio_bytes = await asyncio.to_thread(download_file, audio_key)
    suffix = Path(audio_key).suffix or ".webm"

    if settings.transcription_provider == "groq":
        logger.info("Transcribing %s with Groq (%s)", audio_key, settings.groq_whisper_model)
        return await _transcribe_with_groq(audio_bytes, suffix)

    # Local faster-whisper fallback
    logger.info("Transcribing %s with local Whisper (%s)", audio_key, settings.whisper_model)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    segments = await asyncio.to_thread(_run_local_whisper, tmp_path)
    Path(tmp_path).unlink(missing_ok=True)
    return segments


# ── Embeddings ────────────────────────────────────────────────────────────────

def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
    return _embed_model


async def embed_text(text: str) -> list[float]:
    def _embed(t: str) -> list[float]:
        return _get_embed_model().encode(t, normalize_embeddings=True).tolist()
    return await asyncio.to_thread(_embed, text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    def _embed_batch(ts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in _get_embed_model().encode(ts, normalize_embeddings=True, batch_size=32)]
    return await asyncio.to_thread(_embed_batch, texts)


async def store_transcript(meeting_id: uuid.UUID, segments: list[dict]) -> str:
    key = f"transcripts/{meeting_id}/transcript.json"
    data = json.dumps(segments).encode()
    await asyncio.to_thread(upload_file, key, data, "application/json")
    return key
