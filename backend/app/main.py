import asyncio
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.routers import auth, clientes, facturas, pagos, dashboard, cartera
from app.services.keep_alive import mantener_servidor_despierto

app = FastAPI(title="Facturación API")

# CORS: permite que el frontend (mismo dominio o distinto, según config) llame a la API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routers de la API (antes NO estaban registrados) ---
app.include_router(auth.router)
app.include_router(clientes.router)
app.include_router(facturas.router)
app.include_router(pagos.router)
app.include_router(dashboard.router)
app.include_router(cartera.router)

# --- Rutas de directorios del frontend ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")),
    name="static",
)


def _serve(pagina: str):
    return FileResponse(os.path.join(FRONTEND_DIR, pagina))


@app.get("/")
async def index():
    return _serve("index.html")


@app.get("/index.html")
async def index_html():
    return _serve("index.html")


@app.get("/dashboard.html")
async def dashboard_html():
    return _serve("dashboard.html")


@app.get("/clientes.html")
async def clientes_html():
    return _serve("clientes.html")


@app.get("/facturas.html")
async def facturas_html():
    return _serve("facturas.html")


@app.get("/cartera.html")
async def cartera_html():
    return _serve("cartera.html")


@app.on_event("startup")
async def startup_event():
    if not settings.KEEP_ALIVE_ENABLED:
        return
    if not settings.KEEP_ALIVE_URL:
        # Encendido por variable de entorno pero sin URL configurada: no
        # adivinamos ninguna URL pública, mejor no arrancar nada a ciegas.
        import logging
        logging.getLogger(__name__).warning(
            "KEEP_ALIVE_ENABLED=true pero KEEP_ALIVE_URL está vacío — el auto-ping no se activó."
        )
        return
    app.state.keep_alive_task = asyncio.create_task(
        mantener_servidor_despierto(settings.KEEP_ALIVE_URL, settings.KEEP_ALIVE_INTERVALO_MINUTOS)
    )


@app.on_event("shutdown")
async def shutdown_event():
    tarea = getattr(app.state, "keep_alive_task", None)
    if tarea:
        tarea.cancel()


@app.get("/api/health")
def health():
    return {"status": "ok", "servicio": "facturacion-api", "entorno": settings.ENVIRONMENT}
