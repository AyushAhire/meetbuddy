import sys
from pathlib import Path

# Ensure the api root is on sys.path so worker subprocesses can import local modules
_api_root = str(Path(__file__).resolve().parent.parent)
if _api_root not in sys.path:
    sys.path.insert(0, _api_root)

from celery import Celery

from config import settings

celery_app = Celery(
    "meetbuddy",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["tasks.pipeline"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
