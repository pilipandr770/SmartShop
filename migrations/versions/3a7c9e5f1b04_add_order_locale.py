"""add locale to orders (send confirmation emails in customer's language)

Revision ID: 3a7c9e5f1b04
Revises: 8f1a4e6d2c93
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '3a7c9e5f1b04'
down_revision = '8f1a4e6d2c93'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS locale VARCHAR(5) DEFAULT 'uk'")


def downgrade():
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS locale")
