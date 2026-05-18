import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from config import settings
from utils.storage import download_file, upload_file

_whisper_model = None
_embed_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        _whisper_model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    return _whisper_model


def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("nomic-ai/nomic-embed-text-v1", trust_remote_code=True)
    return _embed_model


async def transcribe_audio_file(audio_key: str) -> list[dict]:
    """Download audio from storage, run faster-whisper, return list of segment dicts."""
    audio_bytes = await asyncio.to_thread(download_file, audio_key)

    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    def _run_whisper(path: str) -> list[dict]:
        model = _get_whisper()
        segments, _ = model.transcribe(
            path,
            beam_size=5,
            condition_on_previous_text=False,
            no_speech_threshold=0.7,
            language="hi",
            task="transcribe",
            initial_prompt="यह एक बातचीत है जिसमें हिंदी, अंग्रेज़ी, या दोनों का मिश्रण हो सकता है।",
        )
        return [
            {"text": seg.text.strip(), "start": seg.start, "end": seg.end}
            for seg in segments
            if seg.text.strip()
        ]

    segments = await asyncio.to_thread(_run_whisper, tmp_path)
    Path(tmp_path).unlink(missing_ok=True)
    return segments


async def embed_text(text: str) -> list[float]:
    """Embed a single string using sentence-transformers."""
    def _embed(t: str) -> list[float]:
        model = _get_embed_model()
        vec = model.encode(t, normalize_embeddings=True)
        return vec.tolist()

    return await asyncio.to_thread(_embed, text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed a list of strings."""
    def _embed_batch(ts: list[str]) -> list[list[float]]:
        model = _get_embed_model()
        vecs = model.encode(ts, normalize_embeddings=True, batch_size=32)
        return [v.tolist() for v in vecs]

    return await asyncio.to_thread(_embed_batch, texts)


async def store_transcript(meeting_id: uuid.UUID, segments: list[dict]) -> str:
    """Upload transcript JSON to storage and return the key."""
    key = f"transcripts/{meeting_id}/transcript.json"
    data = json.dumps(segments).encode()
    await asyncio.to_thread(upload_file, key, data, "application/json")
    return key
