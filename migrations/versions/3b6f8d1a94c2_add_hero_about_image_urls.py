"""Add hero_image_url/about_image_url to site_settings

Revision ID: 3b6f8d1a94c2
Revises: 9f1c3d7b2e46
Create Date: 2026-07-29

Lets store owners upload a homepage banner image and an "About us"
photo (previously logo/favicon existed as URL-only fields, and the
about-page photo was a hardcoded stock URL). Same idempotent style as
prior migrations.
"""
from alembic import op


revision = '3b6f8d1a94c2'
down_revision = '9f1c3d7b2e46'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS hero_image_url VARCHAR(500)")
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS about_image_url VARCHAR(500)")


def downgrade():
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS about_image_url")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS hero_image_url")
