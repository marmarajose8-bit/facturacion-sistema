import enum
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, String, Numeric, DateTime, ForeignKey, Enum, Text, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class EstadoFactura(str, enum.Enum):
    pendiente = "pendiente"
    parcial = "parcial"
    pagada = "pagada"
    anulada = "anulada"
    vencida = "vencida"
    reenganchada = "reenganchada"  # cerrada porque su saldo se consolidó en un nuevo préstamo (reenganche)


class EstadoMora(str, enum.Enum):
    al_dia = "al_dia"
    preventiva = "preventiva"
    administrativa = "administrativa"
    extrajudicial = "extrajudicial"


class Factura(Base):
    __tablename__ = "facturas"

    id = Column(Integer, primary_key=True, index=True)
    numero_factura = Column(String(30), unique=True, index=True, nullable=False)

    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    cliente = relationship("Cliente", back_populates="facturas")

    # Trazabilidad de reenganches: si esta factura nació de un reenganche,
    # apunta a la factura anterior cuyo saldo fue consolidado aquí.
    factura_origen_id = Column(Integer, ForeignKey("facturas.id"), nullable=True)
    factura_origen = relationship("Factura", remote_side=[id], backref="reenganches")

    fecha_emision = Column(Date, server_default=func.current_date())
    fecha_vencimiento = Column(Date, nullable=False)

    # Cada cuánto cobra: semanal, quincenal (15 y 30) o mensual
    frecuencia_pago = Column(String(20), nullable=False, default="mensual")

    # Desglose financiero
    subtotal = Column(Numeric(14, 2), nullable=False, default=0)
    impuestos = Column(Numeric(14, 2), nullable=False, default=0)
    descuento = Column(Numeric(14, 2), nullable=False, default=0)
    # Interés del préstamo (distinto de interes_acumulado, que es mora por
    # atraso). Se cobra una sola vez sobre el capital, no es compuesto.
    # Ej: 15.00 = 15%. Campo libre: en RD los prestamistas informales cobran
    # entre 5% y 30% según el plazo (semanal/quincenal/mensual).
    tasa_interes_prestamo = Column(Numeric(5, 2), nullable=True)
    interes_prestamo = Column(Numeric(14, 2), nullable=False, default=0)
    # Forzar a mano el número de cuota mostrado (ej. se pagó por fuera del
    # sistema y hay que ajustar el contador). NULL = modo automático de
    # siempre (1 pago registrado = avanza 1 cuota). Con valor puesto,
    # panel, PDF, JPG y WhatsApp lo respetan de inmediato porque todos
    # leen de la misma propiedad cuota_actual, sin excepción.
    cuota_manual_override = Column(Integer, nullable=True)
    total = Column(Numeric(14, 2), nullable=False, default=0)

    # Saldo vivo (capital + intereses/recargos - abonos)
    saldo_capital = Column(Numeric(14, 2), nullable=False, default=0)
    # Interés PROPIO del préstamo aún pendiente de cobrar (lo que definió
    # tasa_interes_prestamo al crear la factura). Distinto de interes_acumulado,
    # que es el interés por MORA (atraso), calculado día a día en services/mora.py.
    interes_prestamo_pendiente = Column(Numeric(14, 2), nullable=False, default=0)
    interes_acumulado = Column(Numeric(14, 2), nullable=False, default=0)
    recargo_mora = Column(Numeric(14, 2), nullable=False, default=0)

    estado = Column(
        Enum(EstadoFactura, name="estado_factura"),
        default=EstadoFactura.pendiente, nullable=False,
    )
    estado_mora = Column(
        Enum(EstadoMora, name="estado_mora"),
        default=EstadoMora.al_dia, nullable=False,
    )
    dias_atraso = Column(Integer, default=0)

    notas = Column(Text, nullable=True)

    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    items = relationship("FacturaItem", back_populates="factura", cascade="all, delete-orphan")
    cuotas = relationship("Cuota", back_populates="factura", cascade="all, delete-orphan")
    pagos = relationship("Pago", back_populates="factura")

    # --- Propiedades calculadas para el resumen de cuenta del cliente ---
    # No se guardan en columnas propias: se derivan de los pagos/cuotas ya
    # existentes en cada consulta, así nunca quedan desactualizadas.

    @property
    def total_abonado(self) -> Decimal:
        """Total acumulado que el cliente ha pagado hasta la fecha en esta factura."""
        return sum((Decimal(p.monto_total) for p in self.pagos), Decimal("0"))

    @property
    def saldo_pendiente(self) -> Decimal:
        """Lo que le falta exactamente por pagar: capital + interés del
        préstamo pendiente + interés por mora + recargo, todos vigentes."""
        return (
            Decimal(self.saldo_capital)
            + Decimal(self.interes_prestamo_pendiente)
            + Decimal(self.interes_acumulado)
            + Decimal(self.recargo_mora)
        )

    @property
    def total_cuotas(self) -> int:
        """Plazo total del préstamo en número de cuotas (mínimo 1, aunque sea pago único)."""
        return len(self.cuotas) if self.cuotas else 1

    @property
    def cuotas_pagadas(self) -> int:
        return sum(1 for c in self.cuotas if c.estado == EstadoFactura.pagada)

    @property
    def cuota_actual(self) -> int:
        """Cuenta cuántas cuotas del plan ya quedaron completamente
        cerradas (estado 'pagada'), sin importar en cuántos pagos se hizo:
        - Sin ninguna cuota cerrada todavía: 0.
        - Un pago que cierra 1 cuota: avanza a 1. Un pago único que alcanza
          para cerrar 2 cuotas de una vez (ej. quincenal doble, paga el 15
          y el 30 juntos): avanza directo de 0 a 2, en el mismo pago.
        - Si la factura ya quedó completamente pagada, se topa en el total
          de cuotas (nunca pasa de ahí, aunque haya habido más pagos que
          cuotas por algún abono de más).

        Si cuota_manual_override tiene un valor (se pagó por fuera del
        sistema y se ajustó a mano desde 'Editar cuota'), ese número manda
        por encima del automático — pero siempre topado entre 0 y el total
        de cuotas, para que nunca se pueda mostrar algo como 'Cuota 20 de
        13' o un número negativo por error de dedo."""
        if self.cuota_manual_override is not None:
            return max(0, min(self.cuota_manual_override, self.total_cuotas))
        if self.estado == EstadoFactura.pagada:
            return self.total_cuotas
        return min(self.cuotas_pagadas, self.total_cuotas)

    @property
    def texto_cuota(self) -> str:
        """Texto listo para mostrar en pantalla, ej. 'Cuota 2 de 6'. Usa el
        mismo número que cuota_actual — es a propósito la ÚNICA definición
        de este texto en todo el proyecto: panel web, tabla de Cartera,
        PDF, JPG y mensaje de WhatsApp lo leen de aquí, así que siempre
        van a coincidir exactamente entre sí."""
        return f"Cuota {self.cuota_actual} de {self.total_cuotas}"

    @property
    def cuota_pendiente_actual(self):
        """El objeto Cuota que corresponde cobrar hoy (la primera no pagada,
        por número de cuota). None si la factura no tiene plan de cuotas."""
        if not self.cuotas:
            return None
        pendientes = sorted(
            (c for c in self.cuotas if c.estado != EstadoFactura.pagada),
            key=lambda c: c.numero_cuota,
        )
        if pendientes:
            return pendientes[0]
        # Todas pagadas: devuelve la última como referencia
        return sorted(self.cuotas, key=lambda c: c.numero_cuota)[-1]

    @property
    def fecha_vencimiento_vigente(self):
        """La fecha que de verdad importa para mora/cobranza hoy: el
        vencimiento de la CUOTA que toca pagar ahora mismo — no la fecha
        fija del préstamo completo. Si no hay plan de cuotas (pago único),
        cae de vuelta a fecha_vencimiento, que en ese caso es la misma cosa.
        Esto es lo que se le debe pasar a calcular_dias_atraso(), y lo que
        deben mostrar la tabla, el PDF/JPG y el mensaje de WhatsApp."""
        cuota = self.cuota_pendiente_actual
        return cuota.fecha_vencimiento if cuota else self.fecha_vencimiento

    @property
    def editable_completo(self) -> bool:
        """True si todavía no se ha registrado ningún pago: en ese caso es
        seguro dejar editar montos, ítems, cuotas y frecuencia sin
        descuadrar nada ya cobrado."""
        return len(self.pagos) == 0


class FacturaItem(Base):
    __tablename__ = "factura_items"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    # Nullable a nivel de BD por seguridad, pero el router SIEMPRE la rellena
    # con un texto por defecto ("Préstamo personal" / "Reenganche de crédito")
    # cuando el usuario la deja en blanco, para no bloquear nunca la emisión.
    descripcion = Column(String(300), nullable=True)
    cantidad = Column(Numeric(12, 2), nullable=False, default=1)
    precio_unitario = Column(Numeric(14, 2), nullable=False, default=0)
    porcentaje_impuesto = Column(Numeric(5, 2), nullable=False, default=0)
    subtotal_linea = Column(Numeric(14, 2), nullable=False, default=0)

    factura = relationship("Factura", back_populates="items")


class Cuota(Base):
    """Permite fraccionar una factura en cuotas (plan de pagos)."""
    __tablename__ = "cuotas"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    numero_cuota = Column(Integer, nullable=False)
    fecha_vencimiento = Column(Date, nullable=False)
    monto_capital = Column(Numeric(14, 2), nullable=False, default=0)
    monto_interes = Column(Numeric(14, 2), nullable=False, default=0)
    monto_recargo = Column(Numeric(14, 2), nullable=False, default=0)
    monto_pagado = Column(Numeric(14, 2), nullable=False, default=0)
    estado = Column(
        Enum(EstadoFactura, name="estado_factura"),
        default=EstadoFactura.pendiente, nullable=False,
    )

    factura = relationship("Factura", back_populates="cuotas")
