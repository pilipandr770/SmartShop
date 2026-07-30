"""Add storefront design preset fields to site_settings

Revision ID: 4b8d1e6a9c72
Revises: 3a7c9e5f1b04
Create Date: 2026-07-30 16:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "4b8d1e6a9c72"
down_revision = "3a7c9e5f1b04"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS theme_preset VARCHAR(30) DEFAULT 'emerald_dark'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS font_preset VARCHAR(30) DEFAULT 'system_sans'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS homepage_layout VARCHAR(30) DEFAULT 'hero_grid'"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE site_settings DROP COLUMN IF EXISTS theme_preset"))
    conn.execute(sa.text("ALTER TABLE site_settings DROP COLUMN IF EXISTS font_preset"))
    conn.execute(sa.text("ALTER TABLE site_settings DROP COLUMN IF EXISTS homepage_layout"))
