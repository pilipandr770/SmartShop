"""Add terms_accepted_at / business_purpose_confirmed_at to stores (B2B Widerrufsrecht exclusion evidence)

Revision ID: c1a9f4e7d305
Revises: 9f4a1d6c3b52
Create Date: 2026-07-31 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "c1a9f4e7d305"
down_revision = "9f4a1d6c3b52"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS terms_accepted_at TIMESTAMP"
    ))
    conn.execute(sa.text(
        "ALTER TABLE stores ADD COLUMN IF NOT EXISTS business_purpose_confirmed_at TIMESTAMP"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE stores DROP COLUMN IF EXISTS terms_accepted_at"))
    conn.execute(sa.text("ALTER TABLE stores DROP COLUMN IF EXISTS business_purpose_confirmed_at"))
