from datetime import date
from decimal import Decimal
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import decode_token, requerir_admin
from app.core.config import settings
from app.models.cliente import Cliente
from app.models.factura import Factura, FacturaItem, Cuota, EstadoFactura
from app.models.pago import Pago, Recibo
from app.schemas.factura import (
    FacturaCreate, FacturaUpdate, FacturaOut, FacturaItemCreate, ReenganeCreate, ReenganeElegibilidadOut,
)
from app.services.numeracion import generar_numero_factura
from app.services.mora import actualizar_estado_mora_factura
from app.services.pdf_factura import generar_pdf_factura
from app.services.reenganche import calcular_elegibilidad, ejecutar_reenganche

router = APIRouter(prefix="/api/facturas", tags=["Facturación"], dependencies=[Depends(decode_token)])


def _siguiente_vencimiento(base: date, numero: int, frecuencia: str) -> date:
    """Cada cuánto cae la próxima cuota según la frecuencia de pago."""
    if frecuencia == "semanal":
        return base + relativedelta(weeks=numero - 1)
    if frecuencia == "quincenal":
        return base + relativedelta(days=15 * (numero - 1))
    return base + relativedelta(months=numero - 1)


def _generar_plan_cuotas(total: Decimal, fecha_base: date, numero_cuotas: int, frecuencia: str) -> List[Cuota]:
    """Reparte el total en cuotas iguales (con ajuste de redondeo en la última).
    Se usa tanto al emitir una factura nueva como al crear la factura consolidada
    de un reenganche.
    """
    n_cuotas = max(numero_cuotas, 1)
    monto_por_cuota = (total / n_cuotas).quantize(Decimal("0.01"))
    acumulado = Decimal("0")
    cuotas = []
    for i in range(1, n_cuotas + 1):
        monto = monto_por_cuota
        if i == n_cuotas:
            monto = total - acumulado
        acumulado += monto
        cuotas.append(Cuota(
            numero_cuota=i,
            fecha_vencimiento=_siguiente_vencimiento(fecha_base, i, frecuencia),
            monto_capital=monto,
            estado=EstadoFactura.pendiente,
        ))
    return cuotas


@router.get("", response_model=List[FacturaOut])
def listar_facturas(
    db: Session = Depends(get_db),
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    estado_mora: Optional[str] = None,
    q: Optional[str] = Query(None, description="Buscar por número de factura, nombre o documento del cliente"),
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
):
    query = db.query(Factura).options(
        joinedload(Factura.items), joinedload(Factura.cuotas), joinedload(Factura.cliente), joinedload(Factura.pagos)
    )
    if q:
        like = f"%{q}%"
        query = query.join(Cliente).filter(
            (Factura.numero_factura.ilike(like))
            | (Cliente.razon_social.ilike(like))
            | (Cliente.numero_documento.ilike(like))
        )
    if cliente_id:
        query = query.filter(Factura.cliente_id == cliente_id)
    if estado:
        query = query.filter(Factura.estado == estado)
    if estado_mora:
        query = query.filter(Factura.estado_mora == estado_mora)
    if fecha_desde:
        query = query.filter(Factura.fecha_emision >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Factura.fecha_emision <= fecha_hasta)

    facturas = query.order_by(Factura.fecha_emision.desc()).all()
    for f in facturas:
        actualizar_estado_mora_factura(f)
    db.commit()
    return facturas


@router.post("", response_model=FacturaOut, status_code=201)
def crear_factura(payload: FacturaCreate, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).get(payload.cliente_id)
    if not cliente:
        raise HTTPException(404, "Cliente no encontrado")

    if payload.frecuencia_pago not in ("semanal", "quincenal", "mensual"):
        raise HTTPException(400, "Frecuencia inválida: usa semanal, quincenal o mensual")

    subtotal = Decimal("0")
    impuestos = Decimal("0")
    items_db: List[FacturaItem] = []

    for item in payload.items:
        cant = Decimal(str(item.cantidad))
        precio = Decimal(str(item.precio_unitario))
        pct_imp = Decimal(str(item.porcentaje_impuesto))

        subtotal_linea = (cant * precio).quantize(Decimal("0.01"))
        impuesto_linea = (subtotal_linea * pct_imp / 100).quantize(Decimal("0.01"))

        subtotal += subtotal_linea
        impuestos += impuesto_linea

        items_db.append(FacturaItem(
            descripcion=item.descripcion or settings.PRESTAMO_DESCRIPCION_DEFECTO,
            cantidad=cant,
            precio_unitario=precio,
            porcentaje_impuesto=pct_imp,
            subtotal_linea=subtotal_linea,
        ))

    descuento = Decimal(str(payload.descuento))

    tasa_interes = Decimal(str(payload.tasa_interes_prestamo)) if payload.tasa_interes_prestamo else Decimal("0")
    interes_prestamo = (subtotal * tasa_interes / 100).quantize(Decimal("0.01"))

    total = subtotal + impuestos + interes_prestamo - descuento

    factura = Factura(
        numero_factura=generar_numero_factura(db),
        cliente_id=cliente.id,
        fecha_emision=date.today(),
        fecha_vencimiento=payload.fecha_vencimiento,
        frecuencia_pago=payload.frecuencia_pago,
        subtotal=subtotal,
        impuestos=impuestos,
        descuento=descuento,
        tasa_interes_prestamo=payload.tasa_interes_prestamo,
        interes_prestamo=interes_prestamo,
        total=total,
        saldo_capital=total,
        estado=EstadoFactura.pendiente,
        notas=payload.notas,
        items=items_db,
    )

    factura.cuotas = _generar_plan_cuotas(
        total, payload.fecha_vencimiento, payload.numero_cuotas, payload.frecuencia_pago
    )

    db.add(factura)
    db.commit()
    db.refresh(factura)
    return factura


def _recalcular_totales(
    items_payload: List, descuento_val: float, tasa_interes_val: Optional[float]
):
    """Misma fórmula que crear_factura: recibe los ítems del payload y
    devuelve (subtotal, impuestos, interes_prestamo, total, items_db)."""
    subtotal = Decimal("0")
    impuestos = Decimal("0")
    items_db: List[FacturaItem] = []

    for item in items_payload:
        cant = Decimal(str(item.cantidad))
        precio = Decimal(str(item.precio_unitario))
        pct_imp = Decimal(str(item.porcentaje_impuesto))

        subtotal_linea = (cant * precio).quantize(Decimal("0.01"))
        impuesto_linea = (subtotal_linea * pct_imp / 100).quantize(Decimal("0.01"))

        subtotal += subtotal_linea
        impuestos += impuesto_linea

        items_db.append(FacturaItem(
            descripcion=item.descripcion or settings.PRESTAMO_DESCRIPCION_DEFECTO,
            cantidad=cant,
            precio_unitario=precio,
            porcentaje_impuesto=pct_imp,
            subtotal_linea=subtotal_linea,
        ))

    descuento = Decimal(str(descuento_val))
    tasa_interes = Decimal(str(tasa_interes_val)) if tasa_interes_val else Decimal("0")
    interes_prestamo = (subtotal * tasa_interes / 100).quantize(Decimal("0.01"))
    total = subtotal + impuestos + interes_prestamo - descuento

    return subtotal, impuestos, interes_prestamo, total, items_db


@router.put("/{factura_id}", response_model=FacturaOut)
def editar_factura(factura_id: int, payload: FacturaUpdate, db: Session = Depends(get_db)):
    factura = db.query(Factura).options(
        joinedload(Factura.items), joinedload(Factura.cuotas), joinedload(Factura.pagos)
    ).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    if factura.estado in (EstadoFactura.pagada, EstadoFactura.anulada):
        raise HTTPException(400, "No se puede editar una factura pagada o anulada")

    if payload.frecuencia_pago is not None:
        if payload.frecuencia_pago not in ("semanal", "quincenal", "mensual"):
            raise HTTPException(400, "Frecuencia inválida: usa semanal, quincenal o mensual")
        factura.frecuencia_pago = payload.frecuencia_pago
    if payload.notas is not None:
        factura.notas = payload.notas
    if payload.fecha_vencimiento is not None:
        factura.fecha_vencimiento = payload.fecha_vencimiento

    tiene_pagos = len(factura.pagos) > 0
    quiere_cambiar_montos = any(
        v is not None for v in (payload.items, payload.numero_cuotas, payload.descuento, payload.tasa_interes_prestamo)
    )

    if quiere_cambiar_montos:
        capital_ya_pagado = sum((Decimal(p.monto_capital) for p in factura.pagos), Decimal("0"))

        items_payload = payload.items if payload.items is not None else [
            FacturaItemCreate(
                descripcion=it.descripcion, cantidad=float(it.cantidad),
                precio_unitario=float(it.precio_unitario), porcentaje_impuesto=float(it.porcentaje_impuesto),
            ) for it in factura.items
        ]
        descuento_val = payload.descuento if payload.descuento is not None else float(factura.descuento)
        tasa_val = (
            payload.tasa_interes_prestamo if payload.tasa_interes_prestamo is not None
            else (float(factura.tasa_interes_prestamo) if factura.tasa_interes_prestamo else None)
        )

        subtotal, impuestos, interes_prestamo, total, items_db = _recalcular_totales(
            items_payload, descuento_val, tasa_val
        )

        if tiene_pagos and total < capital_ya_pagado:
            raise HTTPException(
                400,
                f"No puedes dejar el monto corregido (RD${total}) por debajo de lo que ya se cobró "
                f"en esta factura (RD${capital_ya_pagado}). Sube el monto, o si fue un error grave, "
                "anula la factura y créala de nuevo.",
            )

        factura.items = items_db
        factura.subtotal = subtotal
        factura.impuestos = impuestos
        factura.descuento = Decimal(str(descuento_val))
        factura.tasa_interes_prestamo = tasa_val
        factura.interes_prestamo = interes_prestamo
        factura.total = total

        n_cuotas = payload.numero_cuotas if payload.numero_cuotas is not None else factura.total_cuotas
        nuevas_cuotas = _generar_plan_cuotas(
            total, factura.fecha_vencimiento, n_cuotas, factura.frecuencia_pago
        )

        if tiene_pagos and capital_ya_pagado > 0:
            CENTAVO = Decimal("0.01")
            restante = capital_ya_pagado
            for c in sorted(nuevas_cuotas, key=lambda c: c.numero_cuota):
                if restante <= 0:
                    break
                capital_cuota = Decimal(c.monto_capital).quantize(CENTAVO)
                aplicado = min(restante, capital_cuota)
                c.monto_pagado = aplicado
                c.estado = EstadoFactura.pagada if aplicado >= capital_cuota else EstadoFactura.parcial
                restante -= aplicado

        factura.cuotas = nuevas_cuotas
        factura.saldo_capital = total - capital_ya_pagado
        if factura.saldo_capital <= 0:
            factura.saldo_capital = Decimal("0")
            factura.estado = EstadoFactura.pagada
        elif tiene_pagos:
            factura.estado = EstadoFactura.parcial

        actualizar_estado_mora_factura(factura)

    db.commit()
    db.refresh(factura)
    return factura


@router.get("/{factura_id}", response_model=FacturaOut)
def obtener_factura(factura_id: int, db: Session = Depends(get_db)):
    factura = db.query(Factura).options(
        joinedload(Factura.items), joinedload(Factura.cuotas), joinedload(Factura.pagos)
    ).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    actualizar_estado_mora_factura(factura)
    db.commit()
    return factura


@router.get("/{factura_id}/pdf")
def descargar_pdf_factura(factura_id: int, db: Session = Depends(get_db)):
    factura = db.query(Factura).options(
        joinedload(Factura.items), joinedload(Factura.cuotas), joinedload(Factura.cliente)
    ).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    pdf_bytes = generar_pdf_factura(factura, nombre_empresa=settings.EMPRESA_NOMBRE)
    nombre_archivo = f"factura_{factura.numero_factura}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nombre_archivo}"'},
    )


@router.get("/{factura_id}/reenganche/elegibilidad", response_model=ReenganeElegibilidadOut)
def elegibilidad_reenganche(factura_id: int, db: Session = Depends(get_db)):
    factura = db.query(Factura).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    actualizar_estado_mora_factura(factura)
    db.commit()

    return calcular_elegibilidad(factura)


@router.post("/{factura_id}/reenganche", response_model=FacturaOut, status_code=201)
def reenganchar_factura(factura_id: int, payload: ReenganeCreate, db: Session = Depends(get_db)):
    factura = db.query(Factura).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    if payload.frecuencia_pago and payload.frecuencia_pago not in ("semanal", "quincenal", "mensual"):
        raise HTTPException(400, "Frecuencia inválida: usa semanal, quincenal o mensual")

    nueva_factura = ejecutar_reenganche(
        db=db,
        factura=factura,
        monto_adicional=Decimal(str(payload.monto_adicional)),
        fecha_vencimiento=payload.fecha_vencimiento,
        numero_cuotas=payload.numero_cuotas,
        frecuencia_pago=payload.frecuencia_pago,
        descripcion=payload.descripcion,
        generar_plan_cuotas_fn=_generar_plan_cuotas,
    )

    db.commit()
    db.refresh(nueva_factura)
    return nueva_factura


@router.post("/{factura_id}/anular", response_model=FacturaOut, dependencies=[Depends(requerir_admin)])
def anular_factura(factura_id: int, db: Session = Depends(get_db)):
    factura = db.query(Factura).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")
    if factura.estado == EstadoFactura.pagada:
        raise HTTPException(400, "No se puede anular una factura ya pagada")
    factura.estado = EstadoFactura.anulada
    db.commit()
    db.refresh(factura)
    return factura


@router.delete("/{factura_id}", status_code=204, dependencies=[Depends(requerir_admin)])
def eliminar_factura(factura_id: int, db: Session = Depends(get_db)):
    """Borra una factura y todo lo que le pertenece (cuotas, ítems, pagos,
    recibos). Es IRREVERSIBLE. Pensado para que el usuario limpie a mano
    facturas ya pagadas/cerradas o de prueba — el sistema NUNCA borra nada
    solo, esto es siempre una decisión manual desde el botón "Eliminar".
    No toca al cliente: el cliente y sus demás facturas siguen intactos."""
    factura = db.query(Factura).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    pago_ids = [p.id for p in db.query(Pago.id).filter(Pago.factura_id == factura_id)]
    if pago_ids:
        db.query(Recibo).filter(Recibo.pago_id.in_(pago_ids)).delete(synchronize_session=False)
        db.query(Pago).filter(Pago.id.in_(pago_ids)).delete(synchronize_session=False)

    db.query(Factura).filter(Factura.factura_origen_id == factura_id).update(
        {"factura_origen_id": None}, synchronize_session=False
    )

    db.query(Cuota).filter(Cuota.factura_id == factura_id).delete(synchronize_session=False)
    db.query(FacturaItem).filter(FacturaItem.factura_id == factura_id).delete(synchronize_session=False)

    db.delete(factura)
    db.commit()
