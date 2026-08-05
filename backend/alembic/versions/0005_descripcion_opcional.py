"""hace opcional factura_items.descripcion (con default aplicado en backend)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "factura_items", "descripcion",
        existing_type=sa.String(300),
        nullable=True,
    )


def downgrade():
    op.execute("UPDATE factura_items SET descripcion = 'Préstamo personal' WHERE descripcion IS NULL")
    op.alter_column(
        "factura_items", "descripcion",
        existing_type=sa.String(300),
        nullable=False,
    )
