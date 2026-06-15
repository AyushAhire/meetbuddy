import struct

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"timeout": 30} if settings.is_sqlite else {},
)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

# ── Vector store (sqlite-vec) ─────────────────────────────────────────────────
VECTOR_DIM = 768
CHUNK_VEC_TABLE = "chunk_vec"


def pack_vector(values: list[float]) -> bytes:
    """Pack a float vector into the little-endian float32 blob sqlite-vec wants."""
    return struct.pack(f"{len(values)}f", *values)


if settings.is_sqlite:
    import sqlite_vec
    from sqlalchemy.util import await_only

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_conn, _record):
        """Load the sqlite-vec extension and set sane PRAGMAs on each connection.

        The aiosqlite driver exposes enable_load_extension/load_extension as
        coroutines; the connect event runs inside SQLAlchemy's greenlet, so we
        drive them with await_only.
        """
        aioconn = dbapi_conn._connection
        await_only(aioconn.enable_load_extension(True))
        await_only(aioconn.load_extension(sqlite_vec.loadable_path()))
        await_only(aioconn.enable_load_extension(False))
        await_only(aioconn.execute("PRAGMA journal_mode=WAL"))
        await_only(aioconn.execute("PRAGMA busy_timeout=5000"))


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables and the sqlite-vec virtual table. Idempotent."""
    # Import models so metadata is fully populated before create_all.
    import models.user  # noqa: F401
    import models.meeting  # noqa: F401
    import models.memory  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if settings.is_sqlite:
            await conn.execute(text(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {CHUNK_VEC_TABLE} "
                f"USING vec0(chunk_id TEXT PRIMARY KEY, embedding FLOAT[{VECTOR_DIM}])"
            ))


async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
