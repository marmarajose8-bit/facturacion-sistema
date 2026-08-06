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
    total = Column(Numeric(14, 2), nullable=False, default=0)

    # Saldo vivo (capital + intereses/recargos - abonos)
    saldo_capital = Column(Numeric(14, 2), nullable=False, default=0)
    interes_acumulado = Column(Numeric(14, 2), nullable=False, default=0)
    recargo_mora = Column(Numeric(14, 2), nullable=False, default=0)

    estado = Column(Enum(EstadoFactura), default=EstadoFactura.pendiente, nullable=False)
    estado_mora = Column(Enum(EstadoMora), default=EstadoMora.al_dia, nullable=False)
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
        """Lo que le falta exactamente por pagar (capital + interés + mora vigentes)."""
        return Decimal(self.saldo_capital) + Decimal(self.interes_acumulado) + Decimal(self.recargo_mora)

    @property
    def total_cuotas(self) -> int:
        """Plazo total del préstamo en número de cuotas (mínimo 1, aunque sea pago único)."""
        return len(self.cuotas) if self.cuotas else 1

    @property
    def cuotas_pagadas(self) -> int:
        return sum(1 for c in self.cuotas if c.estado == EstadoFactura.pagada)

    @property
    def cuota_actual(self) -> int:
        """En qué número de cuota va el cliente (la primera pendiente; si ya
        pagó todas, se queda en la última)."""
        if not self.cuotas:
            return 1
        if self.estado == EstadoFactura.pagada:
            return self.total_cuotas
        pendientes = sorted(
            (c for c in self.cuotas if c.estado != EstadoFactura.pagada),
            key=lambda c: c.numero_cuota,
        )
        return pendientes[0].numero_cuota if pendientes else self.total_cuotas

    @property
    def texto_cuota(self) -> str:
        """Texto listo para mostrar en pantalla, ej. 'Cuota 2 de 6'."""
        return f"Cuota {self.cuota_actual} de {self.total_cuotas}"


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
    estado = Column(Enum(EstadoFactura), default=EstadoFactura.pendiente, nullable=False)

    factura = relationship("Factura", back_populates="cuotas")
