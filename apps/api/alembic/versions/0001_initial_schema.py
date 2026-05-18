"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
import pgvector.sqlalchemy

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text, unique=True, nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("avatar_url", sa.Text),
        sa.Column("hashed_password", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "meetings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("title", sa.Text),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_secs", sa.Integer),
        sa.Column("status", sa.Text, nullable=False, server_default="recording"),
        sa.Column("audio_url", sa.Text),
        sa.Column("transcript_url", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "speakers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE")),
        sa.Column("speaker_id", UUID(as_uuid=True), sa.ForeignKey("speakers.id")),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("start_time", sa.Float, nullable=False),
        sa.Column("end_time", sa.Float, nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(768)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.execute("CREATE INDEX ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")

    op.create_table(
        "meeting_insights",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("meeting_id", UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE"), unique=True),
        sa.Column("summary", sa.Text),
        sa.Column("action_items", JSONB, server_default="[]"),
        sa.Column("decisions", JSONB, server_default="[]"),
        sa.Column("topics", JSONB, server_default="[]"),
        sa.Column("participants", JSONB, server_default="[]"),
        sa.Column("raw_llm_output", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_table(
        "memory_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("facts", JSONB, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "name", "type"),
    )


def downgrade() -> None:
    op.drop_table("memory_entities")
    op.drop_table("meeting_insights")
    op.drop_table("chunks")
    op.drop_table("speakers")
    op.drop_table("meetings")
    op.drop_table("users")
