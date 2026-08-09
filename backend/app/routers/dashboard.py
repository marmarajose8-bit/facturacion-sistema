from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import decode_token
from app.models.factura import Factura, EstadoFactura
from app.models.pago import Pago
from app.models.cliente import Cliente

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"], dependencies=[Depends(decode_token)])


@router.get("/totales")
def totales_generales(db: Session = Depends(get_db)):
    total_facturado = db.query(func.coalesce(func.sum(Factura.total), 0)).filter(
        Factura.estado != EstadoFactura.anulada
    ).scalar()

    total_cobrado = db.query(func.coalesce(func.sum(Pago.monto_total), 0)).scalar()

    total_pendiente = db.query(
        func.coalesce(func.sum(Factura.saldo_capital + Factura.interes_acumulado + Factura.recargo_mora), 0)
    ).filter(Factura.estado.notin_([EstadoFactura.pagada, EstadoFactura.anulada])).scalar()

    total_clientes_activos = db.query(func.count(Cliente.id)).filter(Cliente.activo.is_(True)).scalar()

    facturas_vencidas = db.query(func.count(Factura.id)).filter(
        Factura.estado == EstadoFactura.vencida
    ).scalar()

    return {
        "total_facturado": float(total_facturado),
        "total_cobrado": float(total_cobrado),
        "total_pendiente": float(total_pendiente),
        "clientes_activos": total_clientes_activos,
        "facturas_vencidas": facturas_vencidas,
        "fecha_corte": date.today().isoformat(),
    }


@router.get("/facturado-mensual")
def facturado_por_mes(db: Session = Depends(get_db)):
    """Serie mensual de facturación y cobros para gráficos del dashboard."""
    resultados_facturado = db.query(
        func.to_char(Factura.fecha_emision, "YYYY-MM").label("mes"),
        func.sum(Factura.total).label("monto"),
    ).filter(Factura.estado != EstadoFactura.anulada).group_by("mes").order_by("mes").all()

    resultados_cobrado = db.query(
        func.to_char(Pago.fecha_pago, "YYYY-MM").label("mes"),
        func.sum(Pago.monto_total).label("monto"),
    ).group_by("mes").order_by("mes").all()

    return {
        "facturado": [{"mes": r.mes, "monto": float(r.monto)} for r in resultados_facturado],
        "cobrado": [{"mes": r.mes, "monto": float(r.monto)} for r in resultados_cobrado],
    }
