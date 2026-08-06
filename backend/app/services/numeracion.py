"""Generación de números correlativos para facturas y recibos."""
from sqlalchemy.orm import Session

from app.models.factura import Factura
from app.models.pago import Recibo


def generar_numero_factura(db: Session) -> str:
    """Usa el número más alto YA EMITIDO (no un conteo de filas), para que
    borrar una factura nunca provoque que se repita un número ya usado."""
    ultimo = db.query(Factura.numero_factura).order_by(Factura.numero_factura.desc()).first()
    siguiente = 1
    if ultimo and ultimo[0]:
        try:
            siguiente = int(ultimo[0].split("-")[-1]) + 1
        except (ValueError, IndexError):
            pass
    return f"FAC-{siguiente:06d}"


def generar_numero_recibo(db: Session) -> str:
    ultimo = db.query(Recibo.numero_recibo).order_by(Recibo.numero_recibo.desc()).first()
    siguiente = 1
    if ultimo and ultimo[0]:
        try:
            siguiente = int(ultimo[0].split("-")[-1]) + 1
        except (ValueError, IndexError):
            pass
    return f"REC-{siguiente:06d}"
