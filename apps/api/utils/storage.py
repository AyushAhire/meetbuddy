import boto3
from botocore.config import Config

from config import settings

_client = None


def get_storage_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key,
            aws_secret_access_key=settings.storage_secret_key,
            config=Config(signature_version="s3v4"),
        )
    return _client


def upload_file(key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    """Upload bytes to storage and return the object key."""
    client = get_storage_client()
    client.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return key


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    client = get_storage_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.storage_bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def download_file(key: str) -> bytes:
    client = get_storage_client()
    response = client.get_object(Bucket=settings.storage_bucket, Key=key)
    return response["Body"].read()


def file_exists(key: str) -> bool:
    from botocore.exceptions import ClientError
    client = get_storage_client()
    try:
        client.head_object(Bucket=settings.storage_bucket, Key=key)
        return True
    except ClientError:
        return False
