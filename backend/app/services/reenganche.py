"""
Lógica de negocio para el "reenganche" (ampliación) de un préstamo activo.

Reenganchar consiste en:
  1. Verificar que el cliente ya amortizó al menos el porcentaje mínimo de
     capital configurado (REENGANCHE_PORCENTAJE_MINIMO) sobre su préstamo activo.
  2. Consolidar en una factura NUEVA el saldo pendiente (capital + interés +
     recargo de mora acumulados) de la factura anterior, sumado al monto
     adicional que se le entrega al cliente.
  3. Cerrar la factura anterior con estado 'reenganchada' (no se borra ni se
     pierde su historial de pagos: queda enlazada vía factura_origen_id).

Esto evita el error común de "sumar" saldos a mano y deja rastro claro en
cartera de qué factura reemplazó a cuál.
"""
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.factura import Factura, FacturaItem, EstadoFactura
from app.services.mora import actualizar_estado_mora_factura
from app.services.numeracion import generar_numero_factura


def _capital_pagado(factura: Factura) -> Decimal:
    """Capital ya amortizado = capital original (factura.total) - saldo_capital vivo.
    Nota: usa factura.total (el capital que se entregó originalmente), no el
    saldo total exigible, porque el % de reenganche se calcula sobre CAPITAL,
    no sobre intereses/recargos.
    """
    total_original = Decimal(factura.total)
    if total_original <= 0:
        return Decimal("0")
    pagado = total_original - Decimal(factura.saldo_capital)
    return max(pagado, Decimal("0"))


def calcular_elegibilidad(factura: Factura) -> dict:
    """Devuelve los datos de elegibilidad de reenganche para una factura activa."""
    total_original = Decimal(factura.total)
    capital_pagado = _capital_pagado(factura)
    porcentaje_pagado = (capital_pagado / total_original) if total_original > 0 else Decimal("0")
    minimo = Decimal(str(settings.REENGANCHE_PORCENTAJE_MINIMO))

    saldo_a_consolidar = (
        Decimal(factura.saldo_capital) + Decimal(factura.interes_acumulado) + Decimal(factura.recargo_mora)
    )

    return {
        "factura_id": factura.id,
        "numero_factura": factura.numero_factura,
        "capital_original": float(total_original),
        "capital_pagado": float(capital_pagado.quantize(Decimal("0.01"))),
        "porcentaje_pagado": float((porcentaje_pagado * 100).quantize(Decimal("0.01"))),
        "porcentaje_minimo_requerido": float((minimo * 100).quantize(Decimal("0.01"))),
        "elegible": porcentaje_pagado >= minimo,
        "saldo_a_consolidar": float(saldo_a_consolidar.quantize(Decimal("0.01"))),
    }


def ejecutar_reenganche(
    db: Session,
    factura: Factura,
    monto_adicional: Decimal,
    fecha_vencimiento,
    numero_cuotas: int,
    frecuencia_pago: str | None,
    descripcion: str | None,
    generar_plan_cuotas_fn,
) -> Factura:
    """Ejecuta el reenganche: valida elegibilidad, cierra la factura vieja y
    crea la nueva factura consolidada. No hace commit (lo hace el router,
    para poder controlar la transacción junto con el resto de la vista)."""

    if factura.estado in (EstadoFactura.anulada, EstadoFactura.reenganchada):
        raise HTTPException(400, "Esta factura ya está anulada o ya fue reenganchada anteriormente")
    if factura.estado == EstadoFactura.pagada:
        raise HTTPException(400, "Esta factura ya está saldada; puedes emitir un préstamo nuevo en su lugar")

    if monto_adicional <= 0:
        raise HTTPException(400, "El monto adicional del reenganche debe ser mayor a cero")

    # Recalcula mora/interés a la fecha de hoy antes de decidir elegibilidad,
    # para no consolidar un saldo desactualizado.
    actualizar_estado_mora_factura(factura)

    info = calcular_elegibilidad(factura)
    if not info["elegible"]:
        raise HTTPException(
            400,
            f"El cliente ha amortizado {info['porcentaje_pagado']:.2f}% del capital, pero se requiere "
            f"al menos {info['porcentaje_minimo_requerido']:.2f}% para poder reenganchar.",
        )

    saldo_arrastrado = (
        Decimal(factura.saldo_capital) + Decimal(factura.interes_acumulado) + Decimal(factura.recargo_mora)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    nuevo_total = (saldo_arrastrado + monto_adicional).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    items_nueva = []
    if saldo_arrastrado > 0:
        items_nueva.append(FacturaItem(
            descripcion=f"Saldo pendiente de factura {factura.numero_factura}",
            cantidad=1,
            precio_unitario=saldo_arrastrado,
            porcentaje_impuesto=0,
            subtotal_linea=saldo_arrastrado,
        ))
    items_nueva.append(FacturaItem(
        descripcion=descripcion or settings.REENGANCHE_DESCRIPCION_DEFECTO,
        cantidad=1,
        precio_unitario=monto_adicional,
        porcentaje_impuesto=0,
        subtotal_linea=monto_adicional,
    ))

    nueva_factura = Factura(
        numero_factura=generar_numero_factura(db),
        cliente_id=factura.cliente_id,
        factura_origen_id=factura.id,
        fecha_vencimiento=fecha_vencimiento,
        frecuencia_pago=frecuencia_pago or factura.frecuencia_pago,
        subtotal=nuevo_total,
        impuestos=Decimal("0"),
        descuento=Decimal("0"),
        total=nuevo_total,
        saldo_capital=nuevo_total,
        estado=EstadoFactura.pendiente,
        notas=f"Reenganche de la factura {factura.numero_factura} "
              f"(saldo consolidado: {saldo_arrastrado}, monto adicional: {monto_adicional}).",
        items=items_nueva,
    )
    nueva_factura.cuotas = generar_plan_cuotas_fn(nuevo_total, fecha_vencimiento, numero_cuotas, nueva_factura.frecuencia_pago)

    # Cierra la factura anterior: su saldo ya vive en la nueva, así que no debe
    # seguir generando mora ni aparecer como deuda activa en cartera. Su
    # historial de pagos permanece intacto y consultable.
    factura.estado = EstadoFactura.reenganchada
    factura.saldo_capital = Decimal("0")
    factura.interes_acumulado = Decimal("0")
    factura.recargo_mora = Decimal("0")
    factura.dias_atraso = 0

    db.add(nueva_factura)
    return nueva_factura
