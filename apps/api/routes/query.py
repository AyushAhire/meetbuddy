from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.user import User
from schemas.meeting import QueryRequest, QueryResponse
from services.auth import get_current_user
from services.query import semantic_search

router = APIRouter(prefix="/query", tags=["query"])


@router.post("", response_model=QueryResponse)
async def query_meetings(
    req: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await semantic_search(req, current_user.id, db)
