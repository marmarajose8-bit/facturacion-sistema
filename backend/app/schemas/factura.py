from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class FacturaItemCreate(BaseModel):
    descripcion: str
    cantidad: float = 1
    precio_unitario: float
    porcentaje_impuesto: float = 0


class FacturaItemOut(FacturaItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subtotal_linea: float


class FacturaCreate(BaseModel):
    cliente_id: int
    fecha_vencimiento: date
    numero_cuotas: int = 1  # 1 = pago único, >1 genera plan de cuotas
    frecuencia_pago: str = "mensual"  # diario | quincenal | mensual
    descuento: float = 0
    notas: Optional[str] = None
    items: List[FacturaItemCreate]


class CuotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    numero_cuota: int
    fecha_vencimiento: date
    monto_capital: float
    monto_interes: float
    monto_recargo: float
    monto_pagado: float
    estado: str


class ClienteMiniOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    razon_social: str
    telefono: Optional[str] = None
    email: Optional[str] = None


class FacturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_factura: str
    cliente_id: int
    cliente: Optional[ClienteMiniOut] = None
    fecha_emision: date
    fecha_vencimiento: date
    frecuencia_pago: str = "mensual"
    subtotal: float
    impuestos: float
    descuento: float
    total: float
    saldo_capital: float
    interes_acumulado: float
    recargo_mora: float
    estado: str
    estado_mora: str
    dias_atraso: int
    items: List[FacturaItemOut] = []
    cuotas: List[CuotaOut] = []
    creado_en: datetime
