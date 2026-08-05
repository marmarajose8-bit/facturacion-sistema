import enum
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

    fecha_emision = Column(Date, server_default=func.current_date())
    fecha_vencimiento = Column(Date, nullable=False)

    # Cada cuánto cobra: diario, quincenal (15 y 30) o mensual
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


class FacturaItem(Base):
    __tablename__ = "factura_items"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    descripcion = Column(String(300), nullable=False)
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
