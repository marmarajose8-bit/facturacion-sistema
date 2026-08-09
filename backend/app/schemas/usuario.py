from datetime import datetime
from pydantic import BaseModel, EmailStr, ConfigDict


class UsuarioCreate(BaseModel):
    nombre_completo: str
    email: EmailStr
    password: str
    rol: str = "cajero"


class UsuarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_completo: str
    email: EmailStr
    rol: str
    activo: bool
    creado_en: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioOut
