from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import decode_token
from app.models.factura import Factura, EstadoMora, EstadoFactura
from app.services.mora import actualizar_estado_mora_factura

router = APIRouter(prefix="/api/cartera", tags=["Cartera y Mora"], dependencies=[Depends(decode_token)])


def _factura_a_resumen(f: Factura) -> dict:
    """Resumen de cuenta de una factura/préstamo: historial de abonos,
    saldo restante y control de cuotas, listo para mostrar en el frontend."""
    return {
        "factura_id": f.id,
        "numero_factura": f.numero_factura,
        "cliente": f.cliente.razon_social if f.cliente else None,
        "cliente_id": f.cliente_id,
        "estado": f.estado.value,
        "dias_atraso": f.dias_atraso,
        "estado_mora": f.estado_mora.value,
        "total": float(f.total),
        "saldo_capital": float(f.saldo_capital),
        "interes_acumulado": float(f.interes_acumulado),
        "recargo_mora": float(f.recargo_mora),
        # Historial y monto abonado hasta la fecha
        "total_abonado": float(f.total_abonado),
        # Saldo restante exacto (capital + interés + mora vigentes)
        "saldo_pendiente": float(f.saldo_pendiente),
        # Control de cuotas: en qué número de cuota va vs. el plazo total
        "total_cuotas": f.total_cuotas,
        "cuotas_pagadas": f.cuotas_pagadas,
        "cuota_actual": f.cuota_actual,
        "texto_cuota": f.texto_cuota,
    }


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


@router.get("/activas")
def facturas_activas(db: Session = Depends(get_db), cliente_id: int | None = None):
    """Resumen de cuenta de TODOS los préstamos activos (estén o no en mora):
    monto abonado hasta la fecha, saldo restante y en qué cuota va cada uno.
    Pensado para el módulo de cartera / resumen de cuenta por cliente."""
    query = db.query(Factura).options(
        joinedload(Factura.cliente), joinedload(Factura.cuotas), joinedload(Factura.pagos)
    ).filter(
        Factura.estado.notin_([EstadoFactura.pagada, EstadoFactura.anulada, EstadoFactura.reenganchada])
    )
    if cliente_id:
        query = query.filter(Factura.cliente_id == cliente_id)

    facturas = query.all()
    for f in facturas:
        actualizar_estado_mora_factura(f)
    db.commit()

    facturas.sort(key=lambda f: f.dias_atraso, reverse=True)
    return [_factura_a_resumen(f) for f in facturas]


@router.get("/vencidas")
def facturas_vencidas(db: Session = Depends(get_db), estado_mora: str | None = None):
    query = db.query(Factura).options(
        joinedload(Factura.cliente), joinedload(Factura.cuotas), joinedload(Factura.pagos)
    ).filter(
        Factura.estado.notin_([EstadoFactura.pagada, EstadoFactura.anulada])
    )
    facturas = query.all()
    for f in facturas:
        actualizar_estado_mora_factura(f)
    db.commit()

    if estado_mora:
        facturas = [f for f in facturas if f.estado_mora.value == estado_mora]

    facturas.sort(key=lambda f: f.dias_atraso, reverse=True)

    return [_factura_a_resumen(f) for f in facturas if f.dias_atraso > 0]
