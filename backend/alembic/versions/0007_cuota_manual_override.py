"""agrega cuota_manual_override a facturas (forzar numero de cuota a mano)

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "facturas",
        sa.Column("cuota_manual_override", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("facturas", "cuota_manual_override")
