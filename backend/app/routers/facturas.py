from datetime import date
from decimal import Decimal
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.security import decode_token
from app.core.config import settings
from app.models.cliente import Cliente
from app.models.factura import Factura, FacturaItem, Cuota, EstadoFactura
from app.schemas.factura import FacturaCreate, FacturaOut, ReenganeCreate, ReenganeElegibilidadOut
from app.services.numeracion import generar_numero_factura
from app.services.mora import actualizar_estado_mora_factura
from app.services.pdf_factura import generar_pdf_factura
from app.services.reenganche import calcular_elegibilidad, ejecutar_reenganche

router = APIRouter(prefix="/api/facturas", tags=["Facturación"], dependencies=[Depends(decode_token)])


def _siguiente_vencimiento(base: date, numero: int, frecuencia: str) -> date:
    """Cada cuánto cae la próxima cuota según la frecuencia de pago."""
    if frecuencia == "diario":
        return base + relativedelta(days=numero - 1)
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
            monto = total - acumulado  # ajuste de redondeo en la última cuota
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
):
    query = db.query(Factura).options(
        joinedload(Factura.items), joinedload(Factura.cuotas), joinedload(Factura.cliente)
    )
    if cliente_id:
        query = query.filter(Factura.cliente_id == cliente_id)
    if estado:
        query = query.filter(Factura.estado == estado)
    if estado_mora:
        query = query.filter(Factura.estado_mora == estado_mora)

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

    if payload.frecuencia_pago not in ("diario", "quincenal", "mensual"):
        raise HTTPException(400, "Frecuencia inválida: usa diario, quincenal o mensual")

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
            # Si el usuario dejó la descripción en blanco, se usa un texto
            # predeterminado en vez de bloquear la emisión de la factura/PDF.
            descripcion=item.descripcion or settings.PRESTAMO_DESCRIPCION_DEFECTO,
            cantidad=cant,
            precio_unitario=precio,
            porcentaje_impuesto=pct_imp,
            subtotal_linea=subtotal_linea,
        ))

    descuento = Decimal(str(payload.descuento))
    total = subtotal + impuestos - descuento

    factura = Factura(
        numero_factura=generar_numero_factura(db),
        cliente_id=cliente.id,
        fecha_emision=date.today(),
        fecha_vencimiento=payload.fecha_vencimiento,
        frecuencia_pago=payload.frecuencia_pago,
        subtotal=subtotal,
        impuestos=impuestos,
        descuento=descuento,
        total=total,
        saldo_capital=total,
        estado=EstadoFactura.pendiente,
        notas=payload.notas,
        items=items_db,
    )

    # Generar plan de cuotas si aplica (reparto igualitario de capital).
    # La frecuencia decide cada cuánto cae la próxima cuota:
    #   diario -> +1 día, quincenal -> +15 días, mensual -> +1 mes (por defecto)
    factura.cuotas = _generar_plan_cuotas(
        total, payload.fecha_vencimiento, payload.numero_cuotas, payload.frecuencia_pago
    )

    db.add(factura)
    db.commit()
    db.refresh(factura)
    return factura


@router.get("/{factura_id}", response_model=FacturaOut)
def obtener_factura(factura_id: int, db: Session = Depends(get_db)):
    factura = db.query(Factura).options(
        joinedload(Factura.items), joinedload(Factura.cuotas)
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
    """Consulta rápida (sin efectos secundarios en BD más allá del recálculo
    de mora habitual) para que el frontend muestre si el cliente ya puede
    reenganchar y cuánto lleva pagado, antes de intentar la operación."""
    factura = db.query(Factura).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    actualizar_estado_mora_factura(factura)
    db.commit()

    return calcular_elegibilidad(factura)


@router.post("/{factura_id}/reenganche", response_model=FacturaOut, status_code=201)
def reenganchar_factura(factura_id: int, payload: ReenganeCreate, db: Session = Depends(get_db)):
    """Amplía/reengancha un préstamo activo: consolida el saldo pendiente de
    `factura_id` más `monto_adicional` en una factura nueva, y cierra la
    anterior como 'reenganchada' (sin borrar su historial de pagos)."""
    factura = db.query(Factura).get(factura_id)
    if not factura:
        raise HTTPException(404, "Factura no encontrada")

    if payload.frecuencia_pago and payload.frecuencia_pago not in ("diario", "quincenal", "mensual"):
        raise HTTPException(400, "Frecuencia inválida: usa diario, quincenal o mensual")

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


@router.post("/{factura_id}/anular", response_model=FacturaOut)
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
