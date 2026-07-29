"""add stripe connect fields to stores

Revision ID: 6c3d8f0a219e
Revises: 5e9a2c7f4b81
Create Date: 2026-07-29 00:00:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '6c3d8f0a219e'
down_revision = '5e9a2c7f4b81'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS stripe_connect_account_id VARCHAR(255)")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS stripe_connect_charges_enabled BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS stripe_connect_onboarded_at TIMESTAMP")


def downgrade():
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS stripe_connect_onboarded_at")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS stripe_connect_charges_enabled")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS stripe_connect_account_id")
