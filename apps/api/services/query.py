import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from models.meeting import Chunk, Meeting
from schemas.meeting import QueryRequest, QueryResponse, QuerySource
from services.llm import answer_query
from services.transcription import embed_text

SIMILARITY_LIMIT = 8


async def semantic_search(
    req: QueryRequest,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> QueryResponse:
    query_embedding = await embed_text(req.q)
    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    base_query = (
        select(
            Chunk.id,
            Chunk.meeting_id,
            Chunk.text,
            Chunk.start_time,
        )
        .join(Meeting, Chunk.meeting_id == Meeting.id)
        .where(Meeting.user_id == user_id)
        .order_by(text(f"embedding <=> '{embedding_str}'::vector"))
        .limit(SIMILARITY_LIMIT)
    )

    if req.meeting_ids:
        base_query = base_query.where(Chunk.meeting_id.in_(req.meeting_ids))

    result = await db.execute(base_query)
    rows = result.all()

    if not rows:
        return QueryResponse(answer="I don't have enough information from your meetings to answer that.", sources=[])

    context_parts = []
    sources = []
    for row in rows:
        context_parts.append(f"[Meeting {row.meeting_id}, t={row.start_time:.1f}s]: {row.text}")
        sources.append(QuerySource(
            chunk_id=row.id,
            meeting_id=row.meeting_id,
            text=row.text,
            start_time=row.start_time,
        ))

    answer = await answer_query(req.q, "\n".join(context_parts))
    return QueryResponse(answer=answer, sources=sources)
