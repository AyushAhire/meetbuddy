import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from database import CHUNK_VEC_TABLE, pack_vector
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
    vec = pack_vector(query_embedding)

    # Nearest neighbours from the sqlite-vec virtual table. Over-fetch so the
    # subsequent user/meeting filtering still leaves enough results.
    fetch_k = SIMILARITY_LIMIT * 5
    knn = await db.execute(
        text(
            f"SELECT chunk_id, distance FROM {CHUNK_VEC_TABLE} "
            "WHERE embedding MATCH :vec AND k = :k ORDER BY distance"
        ),
        {"vec": vec, "k": fetch_k},
    )
    rank: dict[uuid.UUID, float] = {uuid.UUID(cid): dist for cid, dist in knn.all()}
    if not rank:
        return QueryResponse(answer="I don't have enough information from your meetings to answer that.", sources=[])

    base_query = (
        select(Chunk.id, Chunk.meeting_id, Chunk.text, Chunk.start_time)
        .join(Meeting, Chunk.meeting_id == Meeting.id)
        .where(Meeting.user_id == user_id, Chunk.id.in_(list(rank.keys())))
    )
    if req.meeting_ids:
        base_query = base_query.where(Chunk.meeting_id.in_(req.meeting_ids))

    result = await db.execute(base_query)
    rows = sorted(result.all(), key=lambda r: rank[r.id])[:SIMILARITY_LIMIT]

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
