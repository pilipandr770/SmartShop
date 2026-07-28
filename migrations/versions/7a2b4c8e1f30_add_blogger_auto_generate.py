"""Add blogger_auto_generate flag to ai_settings

Revision ID: 7a2b4c8e1f30
Revises: 4d6a01aec893
Create Date: 2026-07-28

Opt-in flag: when enabled, the background scheduler auto-generates blog
posts from due BlogPlan rows without an admin manually clicking "Generate".
Off by default so existing stores don't start incurring OpenAI costs
silently. Same idempotent approach as the prior migrations.
"""
from alembic import op


revision = '7a2b4c8e1f30'
down_revision = '4d6a01aec893'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE ai_settings ADD COLUMN IF NOT EXISTS blogger_auto_generate BOOLEAN DEFAULT FALSE")


def downgrade():
    op.execute("ALTER TABLE ai_settings DROP COLUMN IF EXISTS blogger_auto_generate")
