"""agrega cuota_desde/cuota_hasta a pagos (rango de cuotas cubiertas)

Antes, un Pago no guardaba a qué cuotas afectó: si un cliente pagaba varias
cuotas juntas, el recibo de ESE pago no tenía forma de mostrar el rango real
(mostraba solo el estado actual de la factura completa). Esta migración
agrega dos columnas nullable para guardarlo desde ahora en adelante; los
pagos históricos quedan en NULL (no se puede reconstruir con certeza qué
cuotas cubrió cada uno retroactivamente sin arriesgar datos incorrectos).

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-09
"""
from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("pagos", sa.Column("cuota_desde", sa.Integer(), nullable=True))
    op.add_column("pagos", sa.Column("cuota_hasta", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("pagos", "cuota_hasta")
    op.drop_column("pagos", "cuota_desde")
