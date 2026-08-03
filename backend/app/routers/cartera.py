from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import decode_token
from app.models.factura import Factura, EstadoMora, EstadoFactura
from app.services.mora import actualizar_estado_mora_factura

router = APIRouter(prefix="/api/cartera", tags=["Cartera y Mora"], dependencies=[Depends(decode_token)])


@router.get("/resumen")
def resumen_cartera(db: Session = Depends(get_db)):
    """Totales de cartera agrupados por clasificación de mora, para alertas tempranas."""
    facturas = db.query(Factura).filter(
        Factura.estado.notin_([EstadoFactura.pagada, EstadoFactura.anulada])
    ).all()

    for f in facturas:
        actualizar_estado_mora_factura(f)
    db.commit()

    resumen = {estado.value: {"cantidad": 0, "monto": 0.0} for estado in EstadoMora}
    for f in facturas:
        saldo = float(f.saldo_capital) + float(f.interes_acumulado) + float(f.recargo_mora)
        resumen[f.estado_mora.value]["cantidad"] += 1
        resumen[f.estado_mora.value]["monto"] += saldo

    return resumen


@router.get("/vencidas")
def facturas_vencidas(db: Session = Depends(get_db), estado_mora: str | None = None):
    query = db.query(Factura).options(joinedload(Factura.cliente)).filter(
        Factura.estado.notin_([EstadoFactura.pagada, EstadoFactura.anulada])
    )
    facturas = query.all()
    for f in facturas:
        actualizar_estado_mora_factura(f)
    db.commit()

    if estado_mora:
        facturas = [f for f in facturas if f.estado_mora.value == estado_mora]

    facturas.sort(key=lambda f: f.dias_atraso, reverse=True)

    return [
        {
            "factura_id": f.id,
            "numero_factura": f.numero_factura,
            "cliente": f.cliente.razon_social,
            "dias_atraso": f.dias_atraso,
            "estado_mora": f.estado_mora.value,
            "saldo_capital": float(f.saldo_capital),
            "interes_acumulado": float(f.interes_acumulado),
            "recargo_mora": float(f.recargo_mora),
        }
        for f in facturas if f.dias_atraso > 0
    ]
