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
    abono = "abono"
    total = "total"


class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True)
    factura_id = Column(Integer, ForeignKey("facturas.id"), nullable=False)
    cuota_id = Column(Integer, ForeignKey("cuotas.id"), nullable=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    tipo_pago = Column(Enum(TipoPago, name="tipo_pago"), default=TipoPago.abono, nullable=False)
    metodo_pago = Column(Enum(MetodoPago, name="metodo_pago"), default=MetodoPago.efectivo, nullable=False)

    monto_capital = Column(Numeric(14, 2), nullable=False, default=0)
    monto_interes = Column(Numeric(14, 2), nullable=False, default=0)
    monto_recargo = Column(Numeric(14, 2), nullable=False, default=0)
    monto_total = Column(Numeric(14, 2), nullable=False, default=0)
    vuelto = Column(Numeric(14, 2), nullable=False, default=0)

    cuota_desde = Column(Integer, nullable=True)
    cuota_hasta = Column(Integer, nullable=True)

    referencia = Column(String(100), nullable=True)
    notas = Column(Text, nullable=True)

    fecha_pago = Column(DateTime(timezone=True), server_default=func.now())

    factura = relationship("Factura", back_populates="pagos")
    recibo = relationship("Recibo", back_populates="pago", uselist=False)

    @property
    def texto_cuotas_cubiertas(self) -> str:
        if self.cuota_desde is None:
            return "-"
        total = self.factura.total_cuotas if self.factura else None
        sufijo = f" de {total}" if total else ""
        if self.cuota_desde == self.cuota_hasta:
            return f"Cuota {self.cuota_desde}{sufijo}"
        return f"Cuotas {self.cuota_desde} a {self.cuota_hasta}{sufijo}"


class Recibo(Base):
    __tablename__ = "recibos"

    id = Column(Integer, primary_key=True, index=True)
    numero_recibo = Column(String(30), unique=True, index=True, nullable=False)
    pago_id = Column(Integer, ForeignKey("pagos.id"), unique=True, nullable=False)

    monto_total = Column(Numeric(14, 2), nullable=False)
    generado_en = Column(DateTime(timezone=True), server_default=func.now())

    pago = relationship("Pago", back_populates="recibo")

    @property
    def texto_cuotas_cubiertas(self) -> str:
        return self.pago.texto_cuotas_cubiertas if self.pago else "-"

    @property
    def cuota_desde(self):
        return self.pago.cuota_desde if self.pago else None

    @property
    def cuota_hasta(self):
        return self.pago.cuota_hasta if self.pago else None
