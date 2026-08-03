import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Sistema de Facturación API", version="1.0.0")

# Habilitar CORS para permitir peticiones desde cualquier origen
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas de directorios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../../frontend"))

# Montar archivos estáticos si la carpeta existe
static_path = os.path.join(FRONTEND_DIR, "static")
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

# Ruta raíz para cargar el frontend principal (index.html)
@app.get("/")
def read_index():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"status": "ok", "servicio": "facturacion-api", "entorno": "produccion"}

# Ruta para el dashboard
@app.get("/dashboard.html")
def read_dashboard():
    dash_path = os.path.join(FRONTEND_DIR, "dashboard.html")
    if os.path.exists(dash_path):
        return FileResponse(dash_path)
    return {"error": "Dashboard no encontrado"}

# Ruta de verificación de estado API pura
@app.get("/api/health")
def health_check():
    return {"status": "ok", "servicio": "facturacion-api", "entorno": "produccion"}
