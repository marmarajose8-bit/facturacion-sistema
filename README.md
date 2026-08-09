# Sistema de Facturación y Control de Cobros

Sistema profesional, modular e independiente de facturación, cartera y cobros.
Backend API-first (FastAPI), desplegable en la nube o de forma local (Docker),
y preparado para ser consumido por una futura app móvil (Android/iOS).

## Arquitectura

```
Cliente Web (Tailwind/JS)  ─┐
Cliente Móvil (futuro)     ─┼──►  API REST (FastAPI)  ──►  PostgreSQL
Cliente 3ros / Integraciones─┘
```

- **Backend**: FastAPI + SQLAlchemy + Alembic + PostgreSQL. 100% desacoplado
  del frontend, expone JSON puro. Autenticación con JWT.
- **Frontend Web**: HTML + TailwindCSS + JS vanilla (fetch a la API). No
  requiere build tools, se sirve como archivos estáticos.
- **Despliegue nube**: listo para Railway/Render (usa `PORT` de entorno,
  `DATABASE_URL` estándar).
- **Despliegue local**: `docker-compose up -d` levanta API + BD + frontend
  con un solo comando, sin dependencias del sistema operativo del cliente.
- **App móvil (futuro)**: como la lógica vive 100% en la API REST/JSON, una
  app en React Native / Flutter / Swift / Kotlin puede consumirla sin tocar
  el backend.

## Estructura del repositorio

```
facturacion-sistema/
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   └── app/
│       ├── main.py
│       ├── core/
│       │   ├── config.py        # variables de entorno
│       │   ├── database.py      # engine/session SQLAlchemy
│       │   └── security.py      # JWT, hashing de password
│       ├── models/               # tablas ORM
│       ├── schemas/               # Pydantic (request/response)
│       ├── routers/               # endpoints agrupados por módulo
│       ├── services/              # lógica de negocio (mora, recibos, etc.)
│       └── utils/
├── database/
│   └── schema.sql               # DDL de referencia (equivalente a las migraciones)
├── frontend/
│   ├── index.html                # login
│   ├── dashboard.html
│   ├── clientes.html
│   ├── facturas.html
│   ├── cartera.html
│   └── static/{js,css}
└── docs/
    └── API.md
```

## Arranque rápido (local, con Docker)

```bash
cp .env.example .env
docker-compose up -d --build
```

- API: http://localhost:8000  (docs interactivas en `/docs`)
- Frontend: http://localhost:8080
- Base de datos: PostgreSQL en el puerto 5432 (persistida en volumen)

## Arranque en modo desarrollo (sin Docker)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

## Despliegue en la nube (Railway / Render)

1. Crear un servicio Postgres administrado y copiar su `DATABASE_URL`.
2. Crear un servicio Web apuntando a `backend/` con el `Dockerfile` incluido.
3. Configurar variables de entorno (ver `.env.example`).
4. El comando de arranque ya usa `$PORT` si está definido, para compatibilidad
   con estas plataformas.

## Módulos funcionales incluidos

| Módulo | Descripción |
|---|---|
| Autenticación | Login JWT, roles (admin, cajero, cobrador) |
| Clientes | Datos fiscales, contacto, límite de crédito |
| Facturación | Facturas, ítems, impuestos, cuotas, intereses y recargos por mora |
| Pagos | Abonos parciales, pagos totales, recibos de caja autogenerados |
| Cartera y Mora | Clasificación automática por días de atraso + alertas |
| Dashboard | Totales facturado / cobrado / pendiente, gráficos |

## Próximos pasos sugeridos

- Añadir generación de PDF de facturas/recibos (WeasyPrint o similar).
- Notificaciones automáticas (email/WhatsApp) para cartera vencida.
- App móvil consumiendo esta misma API (React Native recomendado por compartir
  lógica con el frontend web si se desea).
