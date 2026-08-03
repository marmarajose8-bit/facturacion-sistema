import enum
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class MetodoPago(str, enum.Enum):
    efectivo = "efectivo"
    transferencia = "transferencia"
    tarjeta = "tarjeta"
    cheque = "cheque"
    otro = "otro"


class TipoPago(str, enum.Enum):
    abono = "abono"      # pago parcial a capital
    total = "total"       # liquida la factura/cuota


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    cuota_id = Column(Integer, ForeignKey("cuotas.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    tipo_pago = Column(Enum(TipoPago), default=TipoPago.abono, nullable=False)
    metodo_pago = Column(Enum(MetodoPago), default=MetodoPago.efectivo, nullable=False)

    monto_capital = Column(Numeric(14, 2), nullable=False, default=0)
    monto_interes = Column(Numeric(14, 2), nullable=False, default=0)
    monto_recargo = Column(Numeric(14, 2), nullable=False, default=0)
    monto_total = Column(Numeric(14, 2), nullable=False, default=0)

    referencia = Column(String(100), nullable=True)  # # cheque, # transferencia, etc.
    notas = Column(Text, nullable=True)

    fecha_pago = Column(DateTime(timezone=True), server_default=func.now())

    factura = relationship("Factura", back_populates="pagos")
    recibo = relationship("Recibo", back_populates="pago", uselist=False)


class Recibo(Base):
    """Recibo de caja generado automáticamente por cada pago registrado."""
    __tablename__ = "recibos"

    id = Column(Integer, primary_key=True, index=True)
    numero_recibo = Column(String(30), unique=True, index=True, nullable=False)
    pago_id = Column(Integer, ForeignKey("pagos.id"), unique=True, nullable=False)

    monto_total = Column(Numeric(14, 2), nullable=False)
    generado_en = Column(DateTime(timezone=True), server_default=func.now())

    pago = relationship("Pago", back_populates="recibo")
