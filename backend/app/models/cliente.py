from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)

    # Identificación / datos fiscales
    tipo_documento = Column(String(20), nullable=False, default="CEDULA")  # CEDULA, RNC, PASAPORTE
    numero_documento = Column(String(50), unique=True, index=True, nullable=False)
    razon_social = Column(String(200), nullable=False)  # nombre o razón social
    nombre_comercial = Column(String(200), nullable=True)

    # Contacto
    email = Column(String(150), nullable=True)
    telefono = Column(String(30), nullable=True)
    direccion = Column(Text, nullable=True)

    # Condiciones comerciales
    limite_credito = Column(Numeric(14, 2), default=0)
    dias_credito = Column(Integer, default=30)

    activo = Column(Boolean, default=True)
    notas = Column(Text, nullable=True)

    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    actualizado_en = Column(DateTime(timezone=True), onupdate=func.now())

    facturas = relationship("Factura", back_populates="cliente")
