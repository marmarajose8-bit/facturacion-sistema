"""
Script de diagnóstico y auto-reparación para el sistema de facturación y préstamos.

Verifica integridad de cuotas, fechas y saldos en la base de datos y, cuando
encuentra una anomalía MENOR (una fecha fuera de secuencia por error de
redondeo, o un estado de cuota/factura que quedó desincronizado respecto a lo
que ya se abonó), la corrige automáticamente y deja constancia en el log.

Las anomalías que involucran DINERO por encima de una tolerancia mínima
(ANOMALIA_MONTO_TOLERANCIA) NUNCA se autocorrigen — solo se reportan para
revisión humana. Cambiar cuánto debe un cliente no es algo que este script
deba decidir solo; cambiar una fecha mal calculada o una etiqueta de estado
que no refleja lo ya cobrado, sí.

Uso:
    # Solo diagnostica, no escribe nada en la base de datos (modo por defecto)
    python -m scripts.diagnostico_reparacion

    # Diagnostica Y aplica las correcciones menores encontradas
    python -m scripts.diagnostico_reparacion --aplicar

    # Limitar a una factura puntual (para revisar/probar un caso específico)
    python -m scripts.diagnostico_reparacion --factura-id 42 --aplicar

    # Cambiar dónde se guarda el log (por defecto backend/logs/diagnostico.log)
    python -m scripts.diagnostico_reparacion --log-dir /var/log/facturacion
"""
import argparse
import calendar
import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session, joinedload

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.factura import Factura, Cuota, EstadoFactura  # noqa: E402

# Tolerancia para diferencias de dinero: por debajo de esto se considera
# "residuo de redondeo" y NO dispara ni siquiera un reporte; por encima
# de esto se reporta pero NUNCA se autocorrige solo, sin importar el flag
# --aplicar.
CENTAVO = Decimal("0.01")
ANOMALIA_MONTO_TOLERANCIA = Decimal("0.02")

# Si una fecha de cuota está fuera de secuencia por más de este umbral, se
# considera un desajuste "grave" (posible decisión manual deliberada) y
# solo se reporta — no se autocorrige aunque se pase --aplicar. Por debajo
# de este umbral se considera error menor de cálculo y sí se autocorrige.
DIAS_DESVIO_MENOR = 3


# --------------------------------------------------------------------------
# Mismo cálculo de fechas que usa app/routers/facturas.py — se duplica aquí
# a propósito (en vez de importar el router) para que este script de
# mantenimiento no dependa de que la app web cargue (auth, CORS, etc.) y
# pueda correrse solo, por cron o a mano, con la mínima superficie posible.
# --------------------------------------------------------------------------
def _siguiente_quincena(actual: date) -> date:
    ultimo_dia_mes = calendar.monthrange(actual.year, actual.month)[1]
    dia_fin_quincena = min(30, ultimo_dia_mes)
    if actual.day < dia_fin_quincena:
        return actual.replace(day=dia_fin_quincena)
    siguiente_mes = actual.replace(day=1) + relativedelta(months=1)
    return siguiente_mes.replace(day=15)


def _siguiente_fecha_esperada(fecha_actual: date, frecuencia: str) -> date:
    """Dado el vencimiento de una cuota, calcula dónde debería caer la
    cuota inmediatamente siguiente según la frecuencia."""
    if frecuencia == "semanal":
        return fecha_actual + relativedelta(weeks=1)
    if frecuencia == "quincenal":
        return _siguiente_quincena(fecha_actual)
    return fecha_actual + relativedelta(months=1)  # mensual


@dataclass
class Anomalia:
    factura_id: int
    numero_factura: str
    categoria: str  # "frecuencia" | "saldo" | "estado"
    descripcion: str
    corregible: bool
    corregida: bool = False


@dataclass
class ResultadoDiagnostico:
    facturas_revisadas: int = 0
    anomalias: List[Anomalia] = field(default_factory=list)

    @property
    def total_anomalias(self) -> int:
        return len(self.anomalias)

    @property
    def total_corregidas(self) -> int:
        return sum(1 for a in self.anomalias if a.corregida)


def _setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("diagnostico_reparacion")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formato = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formato)
    logger.addHandler(consola)

    archivo = RotatingFileHandler(
        log_dir / "diagnostico.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    archivo.setFormatter(formato)
    logger.addHandler(archivo)

    return logger


# --------------------------------------------------------------------------
# Verificación 1: frecuencias y secuencia de fechas
# --------------------------------------------------------------------------
def _verificar_frecuencias(factura: Factura, aplicar: bool, logger: logging.Logger) -> List[Anomalia]:
    """Revisa que las cuotas TODAVÍA PENDIENTES caigan en la secuencia
    correcta según la frecuencia de cobro (semanal=7 días, quincenal=15/30,
    mensual=mismo día del mes siguiente). Las cuotas ya PAGADAS son
    historial y nunca se tocan ni se cuestionan aquí: pudieron haberse
    cobrado en una fecha distinta a la teórica por mil razones legítimas
    (el cliente pagó adelantado, atrasado, hubo un reenganche, etc.) — eso
    no es una anomalía, es la vida real de la calle."""
    anomalias: List[Anomalia] = []
    pendientes = sorted(
        (c for c in factura.cuotas if c.estado != EstadoFactura.pagada),
        key=lambda c: c.numero_cuota,
    )
    for anterior, siguiente in zip(pendientes, pendientes[1:]):
        esperada = _siguiente_fecha_esperada(anterior.fecha_vencimiento, factura.frecuencia_pago)
        if siguiente.fecha_vencimiento == esperada:
            continue

        desvio_dias = abs((siguiente.fecha_vencimiento - esperada).days)
        va_hacia_atras = siguiente.fecha_vencimiento < anterior.fecha_vencimiento
        es_menor = desvio_dias <= DIAS_DESVIO_MENOR and not va_hacia_atras

        desc = (
            f"Cuota {siguiente.numero_cuota} vence {siguiente.fecha_vencimiento.isoformat()} "
            f"pero según frecuencia '{factura.frecuencia_pago}' desde la cuota "
            f"{anterior.numero_cuota} ({anterior.fecha_vencimiento.isoformat()}) debería ser "
            f"{esperada.isoformat()} (desvío de {desvio_dias} día(s))"
        )
        anomalia = Anomalia(
            factura_id=factura.id,
            numero_factura=factura.numero_factura,
            categoria="frecuencia",
            descripcion=desc,
            corregible=es_menor,
        )
        logger.warning(f"[Factura {factura.numero_factura}] {desc}")

        if es_menor and aplicar:
            siguiente.fecha_vencimiento = esperada
            anomalia.corregida = True
            logger.info(
                f"[Factura {factura.numero_factura}] AUTOCORREGIDO: cuota "
                f"{siguiente.numero_cuota} ajustada a {esperada.isoformat()}"
            )
        anomalias.append(anomalia)

    # Caso especial quincenal: cada cuota pendiente debe caer justo en día
    # 15 o en el "día de cierre de quincena" (min(30, último día del mes)).
    if factura.frecuencia_pago == "quincenal":
        for c in pendientes:
            ultimo_dia_mes = calendar.monthrange(c.fecha_vencimiento.year, c.fecha_vencimiento.month)[1]
            dia_cierre = min(30, ultimo_dia_mes)
            if c.fecha_vencimiento.day in (15, dia_cierre):
                continue
            desc = (
                f"Cuota {c.numero_cuota} cae el día {c.fecha_vencimiento.day} "
                f"({c.fecha_vencimiento.isoformat()}), pero una cuota quincenal debe caer "
                f"el 15 o el {dia_cierre} del mes"
            )
            corregible = abs(c.fecha_vencimiento.day - 15) <= DIAS_DESVIO_MENOR or \
                abs(c.fecha_vencimiento.day - dia_cierre) <= DIAS_DESVIO_MENOR
            anomalia = Anomalia(
                factura_id=factura.id, numero_factura=factura.numero_factura,
                categoria="frecuencia", descripcion=desc, corregible=corregible,
            )
            logger.warning(f"[Factura {factura.numero_factura}] {desc}")
            if corregible and aplicar:
                dia_correcto = 15 if abs(c.fecha_vencimiento.day - 15) <= abs(c.fecha_vencimiento.day - dia_cierre) else dia_cierre
                c.fecha_vencimiento = c.fecha_vencimiento.replace(day=dia_correcto)
                anomalia.corregida = True
                logger.info(
                    f"[Factura {factura.numero_factura}] AUTOCORREGIDO: cuota {c.numero_cuota} "
                    f"movida al día {dia_correcto}"
                )
            anomalias.append(anomalia)

    return anomalias


# --------------------------------------------------------------------------
# Verificación 2: saldos y abonos
# --------------------------------------------------------------------------
def _verificar_saldos(factura: Factura, aplicar: bool, logger: logging.Logger) -> List[Anomalia]:
    """Comprueba que capital + interés del préstamo - abonos cuadre en tres
    lugares distintos que DEBEN coincidir entre sí:
      1) factura.saldo_capital vs (total - abonado a capital)
      2) suma de cuota.monto_capital vs factura.total (plan completo)
      3) suma de cuota.monto_pagado vs suma de pagos.monto_capital

    Cualquier diferencia de dinero por encima de la tolerancia se REPORTA
    pero nunca se autocorrige sola — eso queda para revisión humana."""
    anomalias: List[Anomalia] = []

    total = Decimal(factura.total)
    abonado_capital = sum((Decimal(p.monto_capital) for p in factura.pagos), Decimal("0"))
    saldo_esperado = total - abonado_capital
    if saldo_esperado < 0:
        saldo_esperado = Decimal("0")

    diferencia_saldo = abs(Decimal(factura.saldo_capital) - saldo_esperado)
    if diferencia_saldo > CENTAVO:
        desc = (
            f"saldo_capital guardado es RD${factura.saldo_capital}, pero "
            f"total (RD${total}) - abonado a capital (RD${abonado_capital}) = RD${saldo_esperado} "
            f"(diferencia de RD${diferencia_saldo})"
        )
        corregible = diferencia_saldo <= ANOMALIA_MONTO_TOLERANCIA
        anomalia = Anomalia(
            factura_id=factura.id, numero_factura=factura.numero_factura,
            categoria="saldo", descripcion=desc, corregible=corregible,
        )
        nivel = logger.info if corregible else logger.error
        nivel(f"[Factura {factura.numero_factura}] {desc}")
        if corregible and aplicar:
            factura.saldo_capital = saldo_esperado
            anomalia.corregida = True
            logger.info(
                f"[Factura {factura.numero_factura}] AUTOCORREGIDO: saldo_capital "
                f"ajustado a RD${saldo_esperado}"
            )
        anomalias.append(anomalia)

    suma_cuotas = sum((Decimal(c.monto_capital) for c in factura.cuotas), Decimal("0"))
    diferencia_plan = abs(suma_cuotas - total)
    if diferencia_plan > CENTAVO:
        desc = (
            f"la suma de las cuotas del plan (RD${suma_cuotas}) no coincide con el total "
            f"de la factura (RD${total}), diferencia de RD${diferencia_plan}"
        )
        anomalia = Anomalia(
            factura_id=factura.id, numero_factura=factura.numero_factura,
            categoria="saldo", descripcion=desc, corregible=False,
        )
        logger.error(f"[Factura {factura.numero_factura}] {desc} — requiere revisión manual, no se autocorrige")
        anomalias.append(anomalia)

    suma_pagado_cuotas = sum((Decimal(c.monto_pagado) for c in factura.cuotas), Decimal("0"))
    diferencia_abonos = abs(suma_pagado_cuotas - abonado_capital)
    if diferencia_abonos > CENTAVO:
        desc = (
            f"lo marcado como pagado en las cuotas (RD${suma_pagado_cuotas}) no coincide con "
            f"lo realmente abonado a capital en los pagos registrados (RD${abonado_capital}), "
            f"diferencia de RD${diferencia_abonos}"
        )
        anomalia = Anomalia(
            factura_id=factura.id, numero_factura=factura.numero_factura,
            categoria="saldo", descripcion=desc, corregible=False,
        )
        logger.error(f"[Factura {factura.numero_factura}] {desc} — requiere revisión manual, no se autocorrige")
        anomalias.append(anomalia)

    return anomalias


# --------------------------------------------------------------------------
# Verificación 3: consistencia de estados (cuota y factura)
#
# Esto SOLO corrige la etiqueta de estado a partir de montos que ya están
# guardados — nunca mueve dinero. Por eso, a diferencia de los saldos, sí
# se considera "menor" y se autocorrige siempre que se pase --aplicar.
# --------------------------------------------------------------------------
def _estado_cuota_esperado(cuota: Cuota) -> EstadoFactura:
    pagado = Decimal(cuota.monto_pagado).quantize(CENTAVO)
    capital = Decimal(cuota.monto_capital).quantize(CENTAVO)
    if pagado <= 0:
        return EstadoFactura.pendiente
    if pagado >= capital:
        return EstadoFactura.pagada
    return EstadoFactura.parcial


def _verificar_estados(factura: Factura, aplicar: bool, logger: logging.Logger) -> List[Anomalia]:
    anomalias: List[Anomalia] = []

    for c in factura.cuotas:
        esperado = _estado_cuota_esperado(c)
        if c.estado == esperado:
            continue
        desc = (
            f"Cuota {c.numero_cuota} tiene estado '{c.estado.value}' pero según lo abonado "
            f"(RD${c.monto_pagado} de RD${c.monto_capital}) debería ser '{esperado.value}'"
        )
        anomalia = Anomalia(
            factura_id=factura.id, numero_factura=factura.numero_factura,
            categoria="estado", descripcion=desc, corregible=True,
        )
        logger.warning(f"[Factura {factura.numero_factura}] {desc}")
        if aplicar:
            c.estado = esperado
            anomalia.corregida = True
            logger.info(
                f"[Factura {factura.numero_factura}] AUTOCORREGIDO: cuota {c.numero_cuota} "
                f"pasó a estado '{esperado.value}'"
            )
        anomalias.append(anomalia)

    if factura.estado in (EstadoFactura.anulada, EstadoFactura.reenganchada):
        return anomalias  # estados cerrados/terminales: no se tocan aquí

    saldo = Decimal(factura.saldo_capital)
    tiene_pagos = len(factura.pagos) > 0
    if saldo <= 0:
        estado_esperado = EstadoFactura.pagada
    elif tiene_pagos:
        estado_esperado = EstadoFactura.parcial
    else:
        estado_esperado = EstadoFactura.pendiente
    # 'vencida' es válido en vez de 'pendiente' cuando ya pasó la fecha —
    # eso lo decide services/mora.py, no este script, así que no se marca
    # como anomalía si el estado actual es 'vencida' donde se esperaría
    # 'pendiente'.
    if estado_esperado == EstadoFactura.pendiente and factura.estado == EstadoFactura.vencida:
        return anomalias

    if factura.estado != estado_esperado:
        desc = (
            f"La factura tiene estado '{factura.estado.value}' pero según su saldo "
            f"(RD${saldo}) y pagos registrados debería ser '{estado_esperado.value}'"
        )
        anomalia = Anomalia(
            factura_id=factura.id, numero_factura=factura.numero_factura,
            categoria="estado", descripcion=desc, corregible=True,
        )
        logger.warning(f"[Factura {factura.numero_factura}] {desc}")
        if aplicar:
            factura.estado = estado_esperado
            anomalia.corregida = True
            logger.info(
                f"[Factura {factura.numero_factura}] AUTOCORREGIDO: estado de la factura "
                f"pasó a '{estado_esperado.value}'"
            )
        anomalias.append(anomalia)

    return anomalias


def ejecutar_diagnostico(
    db: Session, logger: logging.Logger, aplicar: bool, factura_id: Optional[int] = None
) -> ResultadoDiagnostico:
    query = db.query(Factura).options(
        joinedload(Factura.cuotas), joinedload(Factura.pagos)
    )
    if factura_id is not None:
        query = query.filter(Factura.id == factura_id)
    facturas = query.order_by(Factura.id).all()

    resultado = ResultadoDiagnostico()
    modo = "APLICANDO correcciones" if aplicar else "solo diagnóstico (dry-run)"
    logger.info(f"Iniciando revisión de {len(facturas)} factura(s) — modo: {modo}")

    for factura in facturas:
        resultado.facturas_revisadas += 1
        resultado.anomalias += _verificar_frecuencias(factura, aplicar, logger)
        resultado.anomalias += _verificar_saldos(factura, aplicar, logger)
        resultado.anomalias += _verificar_estados(factura, aplicar, logger)

    if aplicar and resultado.total_corregidas > 0:
        db.commit()
        logger.info(f"Cambios guardados en la base de datos ({resultado.total_corregidas} corrección(es))")
    else:
        db.rollback()  # dry-run: por seguridad, nunca deja nada a medio escribir

    return resultado


def main():
    parser = argparse.ArgumentParser(description="Diagnóstico y auto-reparación de facturación")
    parser.add_argument(
        "--aplicar", action="store_true",
        help="Aplica y guarda las correcciones menores encontradas. Sin esta bandera, solo reporta (dry-run).",
    )
    parser.add_argument("--factura-id", type=int, default=None, help="Limitar la revisión a una sola factura")
    parser.add_argument(
        "--log-dir", type=str, default=str(Path(__file__).resolve().parent.parent / "logs"),
        help="Carpeta donde se guarda diagnostico.log (por defecto backend/logs/)",
    )
    args = parser.parse_args()

    logger = _setup_logging(Path(args.log_dir))
    db = SessionLocal()
    try:
        resultado = ejecutar_diagnostico(db, logger, aplicar=args.aplicar, factura_id=args.factura_id)
    finally:
        db.close()

    logger.info(
        f"Resumen: {resultado.facturas_revisadas} factura(s) revisada(s), "
        f"{resultado.total_anomalias} anomalía(s) encontrada(s), "
        f"{resultado.total_corregidas} corregida(s) automáticamente"
    )
    sin_corregir = resultado.total_anomalias - resultado.total_corregidas
    if sin_corregir:
        logger.warning(
            f"{sin_corregir} anomalía(s) requieren revisión manual "
            "(involucran dinero por encima de la tolerancia, o un desvío de fecha demasiado grande "
            "para autocorregir con seguridad)"
        )

    # Código de salida útil para cron/CI: 0 = todo limpio, 1 = quedan
    # anomalías pendientes de revisión manual (incluso en modo --aplicar).
    sys.exit(1 if sin_corregir else 0)


if __name__ == "__main__":
    main()
