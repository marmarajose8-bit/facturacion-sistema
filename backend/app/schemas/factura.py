from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator


class FacturaItemCreate(BaseModel):
    # Opcional: si el usuario no la llena, el router le pone un texto
    # predeterminado ("Préstamo personal") para no bloquear la emisión.
    descripcion: Optional[str] = None
    cantidad: float = 1
    precio_unitario: float
    porcentaje_impuesto: float = 0

    @field_validator("descripcion")
    @classmethod
    def _vacio_a_none(cls, v):
        # Trata espacios en blanco como si no se hubiera llenado el campo
        if v is None or not v.strip():
            return None
        return v.strip()


class FacturaItemOut(FacturaItemCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    subtotal_linea: float


class FacturaCreate(BaseModel):
    cliente_id: int
    fecha_vencimiento: date
    numero_cuotas: int = 1  # 1 = pago único, >1 genera plan de cuotas
    frecuencia_pago: str = "mensual"  # semanal | quincenal | mensual
    descuento: float = 0
    tasa_interes_prestamo: Optional[float] = None
    notas: Optional[str] = None
    items: List[FacturaItemCreate]


class FacturaUpdate(BaseModel):
    """Edición de una factura existente.

    fecha_vencimiento, frecuencia_pago y notas se pueden cambiar siempre.
    items, descuento, tasa_interes_prestamo y numero_cuotas SOLO se aplican
    si la factura todavía no tiene ningún pago registrado (si no, el router
    los ignora en silencio para no descuadrar lo ya cobrado)."""
    fecha_vencimiento: Optional[date] = None
    frecuencia_pago: Optional[str] = None
    notas: Optional[str] = None
    numero_cuotas: Optional[int] = None
    descuento: Optional[float] = None
    tasa_interes_prestamo: Optional[float] = None
    items: Optional[List[FacturaItemCreate]] = None


class CuotaManualUpdate(BaseModel):
    """Forzar a mano el número de cuota mostrado (panel, PDF, JPG y
    WhatsApp). cuota: null vuelve al modo automático de siempre."""
    cuota: Optional[int] = None


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


class ReenganeCreate(BaseModel):
    """Ampliación de un préstamo activo: se consolida el saldo pendiente
    (capital + interés + recargo) más el nuevo monto entregado en una
    factura nueva, y la anterior se cierra como 'reenganchada'."""
    monto_adicional: float
    fecha_vencimiento: date
    numero_cuotas: int = 1
    frecuencia_pago: Optional[str] = None  # None = mantiene la de la factura original
    descripcion: Optional[str] = None       # None = usa el texto por defecto de reenganche

    @field_validator("descripcion")
    @classmethod
    def _vacio_a_none(cls, v):
        if v is None or not v.strip():
            return None
        return v.strip()


class ReenganeElegibilidadOut(BaseModel):
    """Respuesta informativa para que el frontend muestre si un cliente
    puede reenganchar y cuánto lleva pagado, antes de intentar la operación."""
    factura_id: int
    numero_factura: str
    capital_original: float
    capital_pagado: float
    porcentaje_pagado: float
    porcentaje_minimo_requerido: float
    elegible: bool
    saldo_a_consolidar: float  # saldo_capital + interes_acumulado + recargo_mora actuales


class FacturaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    numero_factura: str
    cliente_id: int
    cliente: Optional[ClienteMiniOut] = None
    factura_origen_id: Optional[int] = None
    fecha_emision: date
    fecha_vencimiento: date
    fecha_vencimiento_vigente: date  # vencimiento real de la cuota que toca cobrar hoy (usar este para mostrar/cobrar)
    frecuencia_pago: str = "mensual"
    subtotal: float
    impuestos: float
    descuento: float
    tasa_interes_prestamo: Optional[float] = None
    interes_prestamo: float = 0
    notas: Optional[str] = None
    total: float
    saldo_capital: float
    interes_acumulado: float
    recargo_mora: float
    estado: str
    estado_mora: str
    dias_atraso: int

    # --- Resumen de cuenta: historial de abonos, saldo restante y cuota actual ---
    total_abonado: float          # cuánto ha pagado el cliente hasta la fecha
    saldo_pendiente: float        # cuánto le falta exactamente por pagar
    total_cuotas: int             # plazo total del préstamo en cuotas
    cuotas_pagadas: int           # cuántas cuotas ya saldó por completo
    cuota_actual: int             # en qué número de cuota va
    texto_cuota: str              # ej. "Cuota 2 de 6", listo para mostrar
    cuota_manual_override: Optional[int] = None  # si no es None, alguien lo forzó a mano

    # True si la factura todavía no tiene ningún pago: el frontend usa esto
    # para decidir si deja editar montos/ítems/cuotas o solo lo básico
    # (fecha de vencimiento, frecuencia, notas).
    editable_completo: bool

    items: List[FacturaItemOut] = []
    cuotas: List[CuotaOut] = []
    creado_en: datetime
