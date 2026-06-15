"""Local-filesystem blob storage for the desktop app.

Keeps the same interface the rest of the codebase already calls
(upload_file / download_file / file_exists / get_presigned_url) but stores
objects as plain files under the app-data blob directory. Keys may contain
slashes (e.g. "audio/<meeting_id>/tab.webm"); they map to nested paths.

The dev/server build can still use S3/MinIO by setting
MEETBUDDY_STORAGE_BACKEND=s3, which falls back to the boto3 implementation.
"""
import os
from pathlib import Path

from config import BLOB_DIR, settings

_BACKEND = os.environ.get("MEETBUDDY_STORAGE_BACKEND", "local")


def _safe_path(key: str) -> Path:
    """Resolve a storage key to a path inside BLOB_DIR, rejecting traversal."""
    root = BLOB_DIR.resolve()
    target = (root / key).resolve()
    if root != target and root not in target.parents:
        raise ValueError(f"Invalid storage key: {key!r}")
    return target


# ── S3/MinIO backend (dev/server build) ───────────────────────────────────────

_client = None


def _s3_client():
    global _client
    if _client is None:
        import boto3
        from botocore.config import Config
        _client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            config=Config(signature_version="s3v4"),
        )
    return _client


# ── Public interface ──────────────────────────────────────────────────────────

def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Store bytes under ``key`` and return the key."""
    if _BACKEND == "local":
        path = _safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key
    _s3_client().put_object(Bucket=settings.storage_bucket, Key=key, Body=data, ContentType=content_type)
    return key


def download_file(key: str) -> bytes:
    if _BACKEND == "local":
        return _safe_path(key).read_bytes()
    return _s3_client().get_object(Bucket=settings.storage_bucket, Key=key)["Body"].read()


def file_exists(key: str) -> bool:
    if _BACKEND == "local":
        return _safe_path(key).is_file()
    from botocore.exceptions import ClientError
    try:
        _s3_client().head_object(Bucket=settings.storage_bucket, Key=key)
        return True
    except ClientError:
        return False


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    if _BACKEND == "local":
        # Served by FastAPI's GET /files/{key} route from the same local origin.
        return f"/files/{key}"
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.storage_bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def open_file_path(key: str) -> Path:
    """Local-only: absolute path to a stored object (used by the /files route)."""
    return _safe_path(key)
