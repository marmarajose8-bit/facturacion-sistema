from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ClienteBase(BaseModel):
    tipo_documento: str = "CEDULA"
    numero_documento: str
    razon_social: str
    nombre_comercial: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    limite_credito: float = 0
    dias_credito: int = 30
    notas: Optional[str] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    razon_social: Optional[str] = None
    nombre_comercial: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    limite_credito: Optional[float] = None
    dias_credito: Optional[int] = None
    activo: Optional[bool] = None
    notas: Optional[str] = None


class ClienteOut(ClienteBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activo: bool
    creado_en: datetime
