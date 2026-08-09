from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List


class Settings(BaseSettings):
    ENVIRONMENT: str = "local"
    DATABASE_URL: str = "postgresql+psycopg2://facturacion:facturacion_pass@db:5432/facturacion_db"
    SECRET_KEY: str = "change_this_secret_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    CORS_ORIGINS: str = "http://localhost:8080"
    EMPRESA_NOMBRE: str = "Tu Empresa"

    TASA_INTERES_MORA_MENSUAL: float = 0.03
    DIAS_MORA_PREVENTIVA: int = 1
    DIAS_MORA_ADMINISTRATIVA: int = 30
    DIAS_MORA_EXTRAJUDICIAL: int = 90

    REENGANCHE_PORCENTAJE_MINIMO: float = 0.5
    REENGANCHE_DESCRIPCION_DEFECTO: str = "Reenganche de crédito"
    PRESTAMO_DESCRIPCION_DEFECTO: str = "Préstamo personal"

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalizar_database_url(cls, v: str) -> str:
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg2://", 1)
        elif v.startswith("postgresql://") and "+psycopg2" not in v:
            v = v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
