from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class PagoCreate(BaseModel):
    factura_id: int
    cuota_id: Optional[int] = None
    tipo_pago: str = "abono"          # abono | total
    metodo_pago: str = "efectivo"     # efectivo | transferencia | tarjeta | cheque | otro
    monto: float
    referencia: Optional[str] = None
    notas: Optional[str] = None


class PagoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    factura_id: int
    cuota_id: Optional[int]
    tipo_pago: str
    metodo_pago: str
    monto_capital: float
    monto_interes: float
    monto_recargo: float
    monto_total: float
    vuelto: float
    referencia: Optional[str]
    fecha_pago: datetime


class ReciboOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_recibo: str
    pago_id: int
    monto_total: float
    generado_en: datetime
