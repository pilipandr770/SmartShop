"""Add custom_domain fields to stores

Revision ID: 5e9a2c7f4b81
Revises: 3b6f8d1a94c2
Create Date: 2026-07-29

Lets a store owner point their own domain at the platform. verified=False
by default - resolve_current_store() must never trust an unverified
custom_domain, since anyone could otherwise type in a domain they don't
actually control.
"""
from alembic import op


revision = '5e9a2c7f4b81'
down_revision = '3b6f8d1a94c2'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS custom_domain VARCHAR(255)")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS custom_domain_verified BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE stores ADD COLUMN IF NOT EXISTS custom_domain_verified_at TIMESTAMP")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_stores_custom_domain_unique ON stores (custom_domain) WHERE custom_domain IS NOT NULL")


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_stores_custom_domain_unique")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS custom_domain_verified_at")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS custom_domain_verified")
    op.execute("ALTER TABLE stores DROP COLUMN IF EXISTS custom_domain")
