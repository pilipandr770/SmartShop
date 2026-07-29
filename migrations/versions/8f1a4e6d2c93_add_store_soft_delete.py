"""add store soft-delete fields (GDPR account deletion)

Revision ID: 8f1a4e6d2c93
Revises: 6c3d8f0a219e
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '8f1a4e6d2c93'
down_revision = '6c3d8f0a219e'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP")


def downgrade():
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS is_deleted")
