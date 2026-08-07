"""agrega tasa_interes_prestamo e interes_prestamo a facturas

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "facturas",
        sa.Column("tasa_interes_prestamo", sa.Numeric(5, 2), nullable=True),
    )
    op.add_column(
        "facturas",
        sa.Column("interes_prestamo", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("facturas", "interes_prestamo")
    op.drop_column("facturas", "tasa_interes_prestamo")
