"""Add pickup (self-collection) option

Revision ID: 4d6a01aec893
Revises: 69368175a9f0
Create Date: 2026-07-28

Adds a free "pickup" fulfillment alternative to carrier shipping:
SiteSettings.pickup_enabled/pickup_address/pickup_instructions,
Order.is_pickup, WarehouseTask.is_pickup. Same idempotent approach as the
prior three migrations.
"""
from alembic import op


revision = '4d6a01aec893'
down_revision = '69368175a9f0'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS pickup_enabled BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS pickup_address VARCHAR(500)")
    op.execute("ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS pickup_instructions TEXT")
    op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS is_pickup BOOLEAN DEFAULT FALSE")
    op.execute("ALTER TABLE warehouse_tasks ADD COLUMN IF NOT EXISTS is_pickup BOOLEAN DEFAULT FALSE")


def downgrade():
    op.execute("ALTER TABLE warehouse_tasks DROP COLUMN IF EXISTS is_pickup")
    op.execute("ALTER TABLE orders DROP COLUMN IF EXISTS is_pickup")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS pickup_instructions")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS pickup_address")
    op.execute("ALTER TABLE site_settings DROP COLUMN IF EXISTS pickup_enabled")
