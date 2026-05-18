from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserResponse
from services.auth import get_current_user, login_user, refresh_tokens, register_user
from models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    return await register_user(req, db)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    return await login_user(req, db)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    return await refresh_tokens(req.refresh_token, db)


@router.delete("/logout", status_code=204)
async def logout(current_user: User = Depends(get_current_user)):
    # JWT is stateless; client drops the token. For token revocation, add a blocklist here.
    return None


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return current_user
