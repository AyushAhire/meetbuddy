from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from config import settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"
REFRESH_EXPIRE_DAYS = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "type": token_type, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str) -> str:
    return create_token(user_id, ACCESS_TOKEN_TYPE, timedelta(minutes=settings.jwt_expire_minutes))


def create_refresh_token(user_id: str) -> str:
    return create_token(user_id, REFRESH_TOKEN_TYPE, timedelta(days=REFRESH_EXPIRE_DAYS))


def decode_token(token: str) -> dict:
    """Raises JWTError if invalid."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
