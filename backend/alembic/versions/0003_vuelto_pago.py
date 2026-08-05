"""agrega vuelto a pagos (cambio entregado al cliente en efectivo)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "pagos",
        sa.Column("vuelto", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("pagos", "vuelto")
