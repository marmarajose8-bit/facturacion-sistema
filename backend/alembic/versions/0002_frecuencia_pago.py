"""agrega frecuencia_pago a facturas (diario / quincenal / mensual)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "facturas",
        sa.Column("frecuencia_pago", sa.String(20), nullable=False, server_default="mensual"),
    )


def downgrade():
    op.drop_column("facturas", "frecuencia_pago")
