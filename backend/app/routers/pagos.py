from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.factura import Factura, Cuota, EstadoFactura
from app.models.pago import Pago, Recibo
from app.schemas.pago import PagoCreate, PagoOut, ReciboOut
from app.services.numeracion import generar_numero_recibo
from app.services.mora import actualizar_estado_mora_factura
from app.routers.auth import obtener_usuario_actual
from app.models.usuario import Usuario

router = APIRouter(prefix="/api/pagos", tags=["Pagos y Cobros"], dependencies=[Depends(decode_token)])


@router.get("", response_model=List[PagoOut])
def listar_pagos(db: Session = Depends(get_db), factura_id: Optional[int] = None):
    query = db.query(Pago)
    if factura_id:
        query = query.filter(Pago.factura_id == factura_id)
    return query.order_by(Pago.fecha_pago.desc()).all()


@router.post("", response_model=PagoOut, status_code=201)
def registrar_pago(
    payload: PagoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    factura = db.query(Factura).get(payload.factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    if factura.estado in (EstadoFactura.pagada, EstadoFactura.anulada):
        raise HTTPException(400, "La factura ya está pagada o anulada")

    # Recalcular mora/interés antes de aplicar el pago
    actualizar_estado_mora_factura(factura)

    monto = Decimal(str(payload.monto))
    if monto <= 0:
        raise HTTPException(400, "El monto del pago debe ser mayor a cero")

    saldo_total_exigible = (
        Decimal(factura.saldo_capital) + Decimal(factura.interes_acumulado) + Decimal(factura.recargo_mora)
    )
    if monto > saldo_total_exigible:
        raise HTTPException(400, f"El monto excede el saldo pendiente ({saldo_total_exigible})")

    # Orden de aplicación del pago: primero recargos, luego intereses, luego capital
    restante = monto
    aplicado_recargo = min(restante, Decimal(factura.recargo_mora))
    restante -= aplicado_recargo
    aplicado_interes = min(restante, Decimal(factura.interes_acumulado))
    restante -= aplicado_interes
    aplicado_capital = min(restante, Decimal(factura.saldo_capital))
    restante -= aplicado_capital

    factura.recargo_mora -= aplicado_recargo
    factura.interes_acumulado -= aplicado_interes
    factura.saldo_capital -= aplicado_capital

    cuota = None
    if payload.cuota_id:
        cuota = db.query(Cuota).get(payload.cuota_id)
        if cuota:
            cuota.monto_pagado = Decimal(cuota.monto_pagado) + aplicado_capital
            if cuota.monto_pagado >= cuota.monto_capital:
                cuota.estado = EstadoFactura.pagada

    if factura.saldo_capital <= 0:
        factura.estado = EstadoFactura.pagada
        factura.saldo_capital = 0
    else:
        factura.estado = EstadoFactura.parcial

    pago = Pago(
        factura_id=factura.id,
        cuota_id=payload.cuota_id,
        usuario_id=usuario.id,
        tipo_pago=payload.tipo_pago,
        metodo_pago=payload.metodo_pago,
        monto_capital=aplicado_capital,
        monto_interes=aplicado_interes,
        monto_recargo=aplicado_recargo,
        monto_total=monto,
        referencia=payload.referencia,
        notas=payload.notas,
    )
    db.add(pago)
    db.flush()  # para obtener pago.id antes del commit

    recibo = Recibo(
        numero_recibo=generar_numero_recibo(db),
        pago_id=pago.id,
        monto_total=monto,
    )
    db.add(recibo)

    db.commit()
    db.refresh(pago)
    return pago


@router.get("/{pago_id}/recibo", response_model=ReciboOut)
def obtener_recibo(pago_id: int, db: Session = Depends(get_db)):
    recibo = db.query(Recibo).filter(Recibo.pago_id == pago_id).first()
    if not recibo:
        raise HTTPException(404, "Recibo no encontrado para este pago")
    return recibo
