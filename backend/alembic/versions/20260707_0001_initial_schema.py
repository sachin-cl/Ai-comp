"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-07-07
"""

from alembic import op
from app.infrastructure.db.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # All tables are declared once in app.infrastructure.db.models; the initial
    # migration materializes that metadata rather than duplicating ~15 tables here.
    Base.metadata.create_all(bind=bind)

    if is_postgres:
        # Monotonic per-deployment event sequence for agent_messages.seq
        op.execute("CREATE SEQUENCE IF NOT EXISTS event_seq")
        # Native pgvector column + HNSW index for semantic memory (the ORM keeps a
        # portable JSON copy in `embedding`; queries use `embedding_vec`).
        op.execute(
            "ALTER TABLE memory_embeddings "
            "ADD COLUMN IF NOT EXISTS embedding_vec vector(1536)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_membed_hnsw ON memory_embeddings "
            "USING hnsw (embedding_vec vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_notif_user_unread ON notifications (user_id) "
            "WHERE read_at IS NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    if bind.dialect.name == "postgresql":
        op.execute("DROP SEQUENCE IF EXISTS event_seq")
