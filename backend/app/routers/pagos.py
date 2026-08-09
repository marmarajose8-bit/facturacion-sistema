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

# Centavo de tolerancia: evita que un residuo de redondeo binario dado por
# Decimal(float) dispare comparaciones falsas al aplicar abonos.
CENTAVO = Decimal("0.01")


def _marcar_estado_cuota(c: Cuota) -> None:
    """Recalcula el estado de una cuota según lo abonado hasta ahora:
    pendiente (nada abonado), parcial (algo pero no todo) o pagada
    (cubre el capital completo, con tolerancia de redondeo)."""
    pagado = Decimal(c.monto_pagado).quantize(CENTAVO)
    capital = Decimal(c.monto_capital).quantize(CENTAVO)
    if pagado <= 0:
        c.estado = EstadoFactura.pendiente
    elif pagado >= capital:
        c.estado = EstadoFactura.pagada
    else:
        c.estado = EstadoFactura.parcial


def _aplicar_capital_secuencial(factura: Factura, monto_capital: Decimal, cuota_inicio: Optional[Cuota] = None) -> None:
    """Reparte `monto_capital` estrictamente en orden de calendario (número
    de cuota ascendente), llenando primero la cuota más antigua que aún
    tenga saldo antes de tocar la siguiente. Nunca deja un residuo "flotando"
    fuera de las cuotas: si el pago alcanza para más de una, se derrama en
    cascada hacia adelante.

    Si se indica `cuota_inicio`, el reparto arranca en esa cuota puntual (por
    si el usuario/UI señaló explícitamente cuál cobrar) pero SIGUE derramando
    el sobrante hacia las cuotas siguientes en vez de perderlo — así el
    resultado es idéntico sin importar si el pago llegó con o sin cuota_id.
    """
    numero_desde = cuota_inicio.numero_cuota if cuota_inicio else 0
    cuotas_pendientes = sorted(
        (c for c in factura.cuotas if c.estado != EstadoFactura.pagada and c.numero_cuota >= numero_desde),
        key=lambda c: c.numero_cuota,
    )
    restante = monto_capital
    for c in cuotas_pendientes:
        if restante <= 0:
            break
        falta_en_cuota = (
            Decimal(c.monto_capital).quantize(CENTAVO) - Decimal(c.monto_pagado).quantize(CENTAVO)
        )
        if falta_en_cuota <= 0:
            continue
        aplicado_a_esta = min(restante, falta_en_cuota)
        c.monto_pagado = (Decimal(c.monto_pagado) + aplicado_a_esta).quantize(CENTAVO)
        _marcar_estado_cuota(c)
        restante -= aplicado_a_esta


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

    cuota_seleccionada = None
    if payload.cuota_id:
        cuota_seleccionada = db.query(Cuota).get(payload.cuota_id)
        if not cuota_seleccionada:
            raise HTTPException(404, "Cuota no encontrada")
        if cuota_seleccionada.factura_id != factura.id:
            raise HTTPException(400, "Esa cuota no pertenece a esta factura")

    saldo_total_exigible = (
        Decimal(factura.saldo_capital) + Decimal(factura.interes_acumulado) + Decimal(factura.recargo_mora)
    )

    vuelto = Decimal("0")
    if monto > saldo_total_exigible:
        if payload.metodo_pago != "efectivo":
            raise HTTPException(
                400,
                f"El monto excede el saldo pendiente ({saldo_total_exigible}). "
                "Solo se puede recibir de más — y dar vuelto — cuando el método es efectivo.",
            )
        # Cliente pagó con un billete más grande: se aplica solo lo que debía y el resto es vuelto
        vuelto = monto - saldo_total_exigible
        monto_aplicado = saldo_total_exigible
    else:
        monto_aplicado = monto

    # Orden de aplicación del pago: primero recargos, luego intereses, luego capital
    restante = monto_aplicado
    aplicado_recargo = min(restante, Decimal(factura.recargo_mora))
    restante -= aplicado_recargo
    aplicado_interes = min(restante, Decimal(factura.interes_acumulado))
    restante -= aplicado_interes
    aplicado_capital = min(restante, Decimal(factura.saldo_capital))
    restante -= aplicado_capital

    factura.recargo_mora -= aplicado_recargo
    factura.interes_acumulado -= aplicado_interes
    factura.saldo_capital -= aplicado_capital

    # Reparto del capital: estrictamente secuencial por número de cuota,
    # sin perder centavos y sin saltar cuotas — igual haya llegado o no un
    # cuota_id explícito (ver _aplicar_capital_secuencial).
    _aplicar_capital_secuencial(factura, aplicado_capital, cuota_inicio=cuota_seleccionada)

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
        monto_total=monto_aplicado,
        vuelto=vuelto,
        referencia=payload.referencia,
        notas=payload.notas,
    )
    db.add(pago)
    db.flush()  # para obtener pago.id antes del commit

    recibo = Recibo(
        numero_recibo=generar_numero_recibo(db),
        pago_id=pago.id,
        monto_total=monto_aplicado,
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
