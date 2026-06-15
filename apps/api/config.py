import secrets
from pathlib import Path

import platformdirs
from pydantic_settings import BaseSettings

# ── App-data directory ────────────────────────────────────────────────────────
# Single home for the local desktop app: SQLite DB, blob storage, model cache,
# generated secrets. ~/.local/share/MeetBuddy (Linux), ~/Library/Application
# Support/MeetBuddy (macOS). Overridable via MEETBUDDY_DATA_DIR for tests/dev.
import os

APP_DATA_DIR = Path(
    os.environ.get("MEETBUDDY_DATA_DIR") or platformdirs.user_data_dir("MeetBuddy", "MeetBuddy")
)
APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

BLOB_DIR = APP_DATA_DIR / "blobs"
BLOB_DIR.mkdir(parents=True, exist_ok=True)


def _local_jwt_secret() -> str:
    """Read (or generate + persist) a per-install JWT secret.

    The desktop app is single-user and bound to 127.0.0.1, so the secret only
    needs to be stable across restarts, not shared. Generated once on first run.
    """
    key_file = APP_DATA_DIR / "secret.key"
    if key_file.exists():
        return key_file.read_text().strip()
    secret = secrets.token_urlsafe(48)
    key_file.write_text(secret)
    try:
        key_file.chmod(0o600)
    except OSError:
        pass
    return secret


class Settings(BaseSettings):
    # Database — defaults to a local SQLite file; override with DATABASE_URL
    # (e.g. postgresql+asyncpg://…) for the dev/server build.
    database_url: str = f"sqlite+aiosqlite:///{APP_DATA_DIR / 'meetbuddy.db'}"
    redis_url: str = "redis://localhost:6379/0"

    # Storage — local filesystem for the desktop app. The S3/MinIO fields are
    # only consulted by the dev/server build (utils/storage.py uses BLOB_DIR).
    storage_endpoint: str = "http://localhost:9000"
    storage_access_key: str = "meetbuddy"
    storage_secret_key: str = "meetbuddy123"
    storage_bucket: str = "meetbuddy"

    jwt_secret: str = ""  # empty → auto-generated local secret (see __init__)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # Single-user local mode — when true, auth is bypassed and every request is
    # served as the local profile (no login, no token). Set false for the
    # multi-user dev/server build.
    single_user_mode: bool = True
    local_user_email: str = "local@meetbuddy.app"

    llm_provider: str = "ollama"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Transcription — set TRANSCRIPTION_PROVIDER=groq and add GROQ_API_KEY to use Groq
    transcription_provider: str = "local"   # "groq" | "local"
    groq_api_key: str = ""
    groq_whisper_model: str = "whisper-large-v3-turbo"
    whisper_model: str = "base"
    hf_token: str = ""

    next_public_api_url: str = "http://localhost:8000"

    # Static dashboard (Next.js export) served by FastAPI. Defaults to the
    # repo's apps/web/out; the packaged app sets MEETBUDDY_WEB_DIR.
    web_dir: str = str((Path(__file__).resolve().parent.parent / "web" / "out"))

    class Config:
        env_file = ".env"
        extra = "ignore"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.jwt_secret:
            self.jwt_secret = _local_jwt_secret()

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
