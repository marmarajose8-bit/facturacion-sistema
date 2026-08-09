"""
Lógica de negocio para el cálculo de mora, intereses corrientes y recargos,
y la clasificación de cartera (preventiva / administrativa / extrajudicial).

Esta lógica está centralizada aquí para que las reglas del negocio (tasas,
umbrales de días) se puedan ajustar por cliente vía variables de entorno,
sin tocar el resto del código.
"""
from datetime import date
from decimal import Decimal

from app.core.config import settings
from app.models.factura import Factura, EstadoMora, EstadoFactura


def calcular_dias_atraso(fecha_vencimiento: date, hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    delta = (hoy - fecha_vencimiento).days
    return max(delta, 0)


def clasificar_mora(dias_atraso: int) -> EstadoMora:
    if dias_atraso >= settings.DIAS_MORA_EXTRAJUDICIAL:
        return EstadoMora.extrajudicial
    if dias_atraso >= settings.DIAS_MORA_ADMINISTRATIVA:
        return EstadoMora.administrativa
    if dias_atraso >= settings.DIAS_MORA_PREVENTIVA:
        return EstadoMora.preventiva
    return EstadoMora.al_dia


def calcular_interes_y_recargo(saldo_capital: Decimal, dias_atraso: int) -> tuple[Decimal, Decimal]:
    """
    Sistema de cobro directo: NO se calcula ningún interés por mora ni
    recargo automático por atraso. Lo único que el cliente debe es el
    saldo de capital que quedó fijado al emitir la factura (que ya
    incluye, si aplica, el interés del préstamo pactado una sola vez al
    principio — eso se define en tasa_interes_prestamo/interes_prestamo,
    no aquí).

    Esta función se deja en su lugar (en vez de borrarla) solo para no
    romper las llamadas existentes en mora.py/pagos.py/reenganche.py, pero
    siempre devuelve (0, 0). dias_atraso y estado_mora se siguen calculando
    aparte (ver actualizar_estado_mora_factura) porque son solo
    informativos para saber a quién dar seguimiento — no le suman ni un
    peso a lo que el cliente debe pagar.
    """
    return Decimal("0"), Decimal("0")


def actualizar_estado_mora_factura(factura: Factura, hoy: date | None = None) -> Factura:
    """Recalcula días de atraso, clasificación de cartera, interés y recargo de una factura."""
    if factura.estado in (EstadoFactura.pagada, EstadoFactura.anulada):
        factura.dias_atraso = 0
        factura.estado_mora = EstadoMora.al_dia
        return factura

    # Usa el vencimiento de la CUOTA que toca cobrar hoy, no la fecha fija
    # del préstamo completo — así un cliente que va al día cuota a cuota no
    # aparece en mora por atraso del plan original.
    dias = calcular_dias_atraso(factura.fecha_vencimiento_vigente, hoy)
    factura.dias_atraso = dias
    factura.estado_mora = clasificar_mora(dias)

    interes, recargo = calcular_interes_y_recargo(Decimal(factura.saldo_capital), dias)
    factura.interes_acumulado = interes
    factura.recargo_mora = recargo

    if dias > 0 and factura.estado == EstadoFactura.pendiente:
        factura.estado = EstadoFactura.vencida

    return factura
