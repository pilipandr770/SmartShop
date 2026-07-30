"""Backfill existing users as email-verified (email verification is a new gate)

Revision ID: 9f4a1d6c3b52
Revises: 7d2b5c8e1a94
Create Date: 2026-07-30 19:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "9f4a1d6c3b52"
down_revision = "7d2b5c8e1a94"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # is_verified раніше ніде не перевірявся (крім B2B, де він плутався з
    # VAT-статусом компанії) - тому всі існуючі акаунти вважаються такими,
    # що вже пройшли б підтвердження, якби воно існувало на момент реєстрації.
    # Лише НОВІ реєстрації після цієї міграції реально проходять через лист
    # підтвердження.
    conn.execute(sa.text("UPDATE users SET is_verified = true WHERE is_verified = false"))


def downgrade():
    # Немає безпечного способу відкотити - які саме користувачі раніше мали
    # is_verified=false невідомо після backfill'у.
    pass
