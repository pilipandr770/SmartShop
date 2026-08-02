"""Add accent_color and font_size_preset to site_settings

Revision ID: e658617d5551
Revises: d4e8b1f6a930
Create Date: 2026-08-02 12:50:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "e658617d5551"
down_revision = "d4e8b1f6a930"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS accent_color VARCHAR(7)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS font_size_preset VARCHAR(20) DEFAULT 'medium'"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE site_settings DROP COLUMN IF EXISTS accent_color"))
    conn.execute(sa.text("ALTER TABLE site_settings DROP COLUMN IF EXISTS font_size_preset"))
