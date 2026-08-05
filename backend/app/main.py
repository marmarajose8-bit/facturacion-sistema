import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import settings
from app.routers import auth, clientes, facturas, pagos, dashboard, cartera

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


@app.get("/api/health")
def health():
    return {"status": "ok", "servicio": "facturacion-api", "entorno": settings.ENVIRONMENT}
