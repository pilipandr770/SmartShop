"""Add privacy_policy_text/terms_text to site_settings

Revision ID: 9f1c3d7b2e46
Revises: 7a2b4c8e1f30
Create Date: 2026-07-28

Backs the new per-store Datenschutz/AGB pages - store owners can override
the generic placeholder text with their own. Impressum needs no dedicated
text field since it's assembled from the existing admin_company_* columns.
"""
from alembic import op


revision = '9f1c3d7b2e46'
down_revision = '7a2b4c8e1f30'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS privacy_policy_text TEXT")
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS terms_text TEXT")


def downgrade():
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS terms_text")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS privacy_policy_text")
