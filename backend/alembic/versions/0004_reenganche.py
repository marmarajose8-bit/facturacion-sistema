"""agrega reenganche: nuevo estado 'reenganchada' y factura_origen_id

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    # Los tipos ENUM de Postgres requieren agregar el valor fuera de una
    # transacción implícita de bloque; Alembic maneja esto con autocommit.
    op.execute("ALTER TYPE estado_factura ADD VALUE IF NOT EXISTS 'reenganchada'")

    op.add_column(
        "facturas",
        sa.Column("factura_origen_id", sa.Integer(), sa.ForeignKey("facturas.id"), nullable=True),
    )
    op.create_index(
        "ix_facturas_factura_origen_id", "facturas", ["factura_origen_id"]
    )


def downgrade():
    op.drop_index("ix_facturas_factura_origen_id", table_name="facturas")
    op.drop_column("facturas", "factura_origen_id")
    # Nota: Postgres no permite quitar un valor de un ENUM fácilmente;
    # el downgrade deja 'reenganchada' definido pero sin uso.
