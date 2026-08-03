"""Generación de números correlativos para facturas y recibos."""
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.factura import Factura
from app.models.pago import Recibo


def generar_numero_factura(db: Session) -> str:
    total = db.query(func.count(Factura.id)).scalar() or 0
    return f"FAC-{total + 1:06d}"


def generar_numero_recibo(db: Session) -> str:
    total = db.query(func.count(Recibo.id)).scalar() or 0
    return f"REC-{total + 1:06d}"
