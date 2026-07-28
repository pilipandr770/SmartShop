"""Add shipping carrier integration (CarrierAccount, Product.weight_kg, WarehouseTask.label_url)

Revision ID: 69368175a9f0
Revises: e658617d5550
Create Date: 2026-07-28

Adds the DHL/UPS carrier integration: a new per-store carrier_accounts
table, Product.weight_kg (for rate/label package weight), and
WarehouseTask.label_url (auto-generated shipping label link). Same
idempotent (IF NOT EXISTS) approach as the two prior migrations, for the
same reason: app.py's init_db() calls db.create_all() on every process
start, including the one triggered by `flask db upgrade` importing app.py.
"""
from alembic import op


revision = '69368175a9f0'
down_revision = 'e658617d5550'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS carrier_accounts (
            id SERIAL PRIMARY KEY,
            store_id INTEGER NOT NULL REFERENCES stores (id),
            carrier VARCHAR(20) NOT NULL,
            is_enabled BOOLEAN DEFAULT TRUE,
            is_sandbox BOOLEAN DEFAULT TRUE,
            credentials JSON,
            origin_name VARCHAR(200),
            origin_phone VARCHAR(50),
            origin_street VARCHAR(255),
            origin_city VARCHAR(100),
            origin_postal_code VARCHAR(20),
            origin_country_code VARCHAR(2),
            created_at TIMESTAMP,
            updated_at TIMESTAMP,
            CONSTRAINT uq_carrier_accounts_store_carrier UNIQUE (store_id, carrier)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_carrier_accounts_store_id ON carrier_accounts (store_id)")

    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS weight_kg FLOAT")
    op.execute("ALTER TABLE warehouse_tasks ADD COLUMN IF NOT EXISTS label_url VARCHAR(1000)")


def downgrade():
    op.execute("ALTER TABLE warehouse_tasks DROP COLUMN IF EXISTS label_url")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS weight_kg")
    op.execute("DROP TABLE IF EXISTS carrier_accounts")
