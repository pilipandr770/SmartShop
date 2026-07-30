"""Encrypt CarrierAccount.credentials at rest (Fernet)

Revision ID: 7d2b5c8e1a94
Revises: 4b8d1e6a9c72
Create Date: 2026-07-30 19:15:00.000000
"""
import json
import os

from alembic import op
import sqlalchemy as sa

revision = "7d2b5c8e1a94"
down_revision = "4b8d1e6a9c72"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE carrier_accounts ADD COLUMN IF NOT EXISTS credentials_encrypted TEXT"
    ))

    # Мігруємо існуючі відкриті credentials (JSON) у зашифровану колонку.
    # Якщо колонки credentials вже нема (свіжа БД) або рядків нема - нічого
    # робити не потрібно; якщо є дані, але ключ не налаштовано - явно
    # падаємо, а не тихо лишаємо дані незашифрованими.
    has_old_column = conn.execute(sa.text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'carrier_accounts' AND column_name = 'credentials'"
    )).first()

    if has_old_column:
        rows = conn.execute(sa.text(
            "SELECT id, credentials FROM carrier_accounts WHERE credentials IS NOT NULL"
        )).fetchall()

        if rows:
            key = os.environ.get("CARRIER_CREDENTIALS_KEY")
            if not key:
                raise RuntimeError(
                    "CARRIER_CREDENTIALS_KEY не налаштовано - неможливо мігрувати "
                    "існуючі carrier_accounts.credentials у зашифрований формат."
                )
            from cryptography.fernet import Fernet
            fernet = Fernet(key.encode() if isinstance(key, str) else key)

            for row in rows:
                raw = row.credentials if not isinstance(row.credentials, str) else json.loads(row.credentials)
                encrypted = fernet.encrypt(json.dumps(raw).encode()).decode()
                conn.execute(
                    sa.text("UPDATE carrier_accounts SET credentials_encrypted = :enc WHERE id = :id"),
                    {"enc": encrypted, "id": row.id},
                )

        conn.execute(sa.text("ALTER TABLE carrier_accounts DROP COLUMN credentials"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text(
        "ALTER TABLE carrier_accounts ADD COLUMN IF NOT EXISTS credentials JSON"
    ))
    conn.execute(sa.text("ALTER TABLE carrier_accounts DROP COLUMN IF EXISTS credentials_encrypted"))
