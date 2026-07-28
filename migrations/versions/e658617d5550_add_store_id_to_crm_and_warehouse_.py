"""Add store_id to CRM (Company/VerificationLog/AdminAlert) and warehouse tables

Revision ID: e658617d5550
Revises: 45a6a1913a89
Create Date: 2026-07-28

Phase 2 of multi-tenancy: tenant-scope the B2B/CRM and warehouse modules,
which Phase 1 (45a6a1913a89) deliberately left global. Same idempotent
approach as Phase 1 (IF NOT EXISTS / IF EXISTS) for the same reason: app.py's
init_db() calls db.create_all() on every process start, including the one
triggered by `flask db upgrade` importing app.py itself.
"""
from alembic import op


revision = 'e658617d5550'
down_revision = '45a6a1913a89'
branch_labels = None
depends_on = None


TABLES_WITH_STORE_ID = [
    "companies",
    "verification_logs",
    "admin_alerts",
    "warehouse_tasks",
    "stock_movements",
    "replenishment_orders",
    "replenishment_items",
    "warehouse_expenses",
    "low_stock_alerts",
]


def upgrade():
    for table in TABLES_WITH_STORE_ID:
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS store_id INTEGER")
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_store_id ON {table} (store_id)")
        op.execute(f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_{table}_store_id_stores'
                      AND conrelid = '{table}'::regclass
                ) THEN
                    ALTER TABLE {table}
                        ADD CONSTRAINT fk_{table}_store_id_stores
                        FOREIGN KEY (store_id) REFERENCES stores (id);
                END IF;
            END $$;
        """)


def downgrade():
    for table in TABLES_WITH_STORE_ID:
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS fk_{table}_store_id_stores")
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_store_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS store_id")
