"""Add optional TOTP 2FA fields to users

Revision ID: f209a3c8e412
Revises: e658617d5551
Create Date: 2026-08-02 20:05:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "f209a3c8e412"
down_revision = "e658617d5551"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_secret_encrypted TEXT"
    ))
    conn.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_enabled BOOLEAN NOT NULL DEFAULT FALSE"
    ))
    conn.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS totp_backup_codes TEXT"
    ))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS totp_secret_encrypted"))
    conn.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS totp_enabled"))
    conn.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS totp_backup_codes"))
