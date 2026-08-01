"""Add homepage_blocks table (customizable homepage feature cards)

Revision ID: d4e8b1f6a930
Revises: c1a9f4e7d305
Create Date: 2026-08-01 12:15:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "d4e8b1f6a930"
down_revision = "c1a9f4e7d305"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS homepage_blocks (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL REFERENCES stores(id),
            title VARCHAR(100) NOT NULL,
            subtitle VARCHAR(100),
            image_url VARCHAR(500),
            link_type VARCHAR(20) NOT NULL DEFAULT 'custom',
            link_value VARCHAR(500),
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_homepage_blocks_store_id ON homepage_blocks (store_id)"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS homepage_blocks"))
