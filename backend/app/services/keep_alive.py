"""
Auto-mantenimiento: envía un ping HTTP periódico a la propia URL pública de
la aplicación para evitar que la nube la suspenda por inactividad.

Se activa/desactiva y configura por completo vía variables de entorno
(ver app/core/config.py: KEEP_ALIVE_ENABLED, KEEP_ALIVE_URL,
KEEP_ALIVE_INTERVALO_MINUTOS) — nunca corre por accidente en desarrollo
local, y en producción apunta a /api/health en vez de la portada completa
porque es la ruta más liviana posible para este propósito.
"""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def mantener_servidor_despierto(url: str, intervalo_minutos: int = 14):
    """Hace ping a `url` cada `intervalo_minutos`, indefinidamente, hasta que
    la tarea se cancele (ej. al apagar la app). Un fallo de red puntual no
    detiene el ciclo — solo se registra como aviso y se sigue intentando
    en la siguiente vuelta."""
    intervalo_segundos = intervalo_minutos * 60

    # Damos un respiro para asegurarnos de que el servidor levantó por completo
    await asyncio.sleep(30)

    async with httpx.AsyncClient() as client:
        while True:
            try:
                response = await client.get(url, timeout=10.0)
                logger.info(f"Ping de mantenimiento automático enviado a {url} - Status: {response.status_code}")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Aviso de mantenimiento: No se pudo completar el ping: {e}")

            await asyncio.sleep(intervalo_segundos)
