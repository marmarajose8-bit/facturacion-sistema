from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import auth, clientes, facturas, pagos, cartera, dashboard

app = FastAPI(
    title="Sistema de Facturación y Control de Cobros",
    description="API REST para gestión de clientes, facturación, pagos y cartera. "
                "Diseñada para ser consumida por web, escritorio y app móvil.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(facturas.router)
app.include_router(pagos.router)
app.include_router(cartera.router)
app.include_router(dashboard.router)


@app.get("/", tags=["Salud"])
def raiz():
    return {"status": "ok", "servicio": "facturacion-api", "entorno": settings.ENVIRONMENT}


@app.get("/health", tags=["Salud"])
def health_check():
    return {"status": "healthy"}
