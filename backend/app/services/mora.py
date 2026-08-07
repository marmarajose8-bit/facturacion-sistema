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
    Interés corriente simple proporcional a los días de atraso (base 30 días)
    + un recargo fijo escalonado según la severidad de la mora.
    Ajustar esta función según la política financiera real del cliente.
    """
    if dias_atraso <= 0 or saldo_capital <= 0:
        return Decimal("0"), Decimal("0")

    tasa_mensual = Decimal(str(settings.TASA_INTERES_MORA_MENSUAL))
    interes = (saldo_capital * tasa_mensual * Decimal(dias_atraso) / Decimal(30)).quantize(Decimal("0.01"))

    if dias_atraso >= settings.DIAS_MORA_EXTRAJUDICIAL:
        recargo_pct = Decimal("0.10")
    elif dias_atraso >= settings.DIAS_MORA_ADMINISTRATIVA:
        recargo_pct = Decimal("0.05")
    elif dias_atraso >= settings.DIAS_MORA_PREVENTIVA:
        recargo_pct = Decimal("0.02")
    else:
        recargo_pct = Decimal("0")

    recargo = (saldo_capital * recargo_pct).quantize(Decimal("0.01"))
    return interes, recargo


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
