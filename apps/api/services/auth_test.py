import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from schemas.auth import RegisterRequest, LoginRequest


@pytest.mark.asyncio
async def test_register_new_user():
    from services.auth import register_user

    db = AsyncMock()
    db.scalar.return_value = None
    db.flush = AsyncMock()

    req = RegisterRequest(email="test@example.com", password="secret123", name="Test")
    result = await register_user(req, db)

    assert result.access_token
    assert result.refresh_token
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_register_duplicate_email_raises():
    from fastapi import HTTPException
    from services.auth import register_user

    db = AsyncMock()
    db.scalar.return_value = MagicMock()  # existing user

    req = RegisterRequest(email="dup@example.com", password="secret123")
    with pytest.raises(HTTPException) as exc_info:
        await register_user(req, db)
    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_login_invalid_credentials_raises():
    from fastapi import HTTPException
    from services.auth import login_user

    db = AsyncMock()
    db.scalar.return_value = None

    req = LoginRequest(email="nobody@example.com", password="wrong")
    with pytest.raises(HTTPException) as exc_info:
        await login_user(req, db)
    assert exc_info.value.status_code == 401
