"""Genera el PDF de una factura para descargar o enviar al cliente."""
import io
from datetime import date, datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
)

from app.models.factura import Factura

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fmt(monto) -> str:
    return f"RD$ {float(monto or 0):,.2f}"


def _fecha_es(valor) -> str:
    """Formatea una fecha en español ('5 de agosto de 2026'). Acepta un
    date/datetime, un string ISO ('2026-08-05') o None/vacío/valor
    corrupto — en cualquiera de esos últimos casos cae de vuelta a la
    fecha de hoy en vez de imprimir algo como 'Invalid Date' o 'None'."""
    dt = valor
    if isinstance(dt, str):
        try:
            dt = date.fromisoformat(dt[:10])
        except (ValueError, TypeError):
            dt = None
    if isinstance(dt, datetime):
        dt = dt.date()
    if not isinstance(dt, date):
        dt = date.today()
    return f"{dt.day} de {MESES_ES[dt.month - 1]} de {dt.year}"


def generar_pdf_factura(factura: Factura, nombre_empresa: str = "Tu Empresa", logo_path: str = None) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=1.8 * cm, bottomMargin=2.2 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=styles["Title"], fontSize=20, spaceAfter=2)
    subtitulo = ParagraphStyle("subtitulo", parent=styles["Normal"], textColor=colors.grey)
    etiqueta = ParagraphStyle("etiqueta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    story = []

    # Encabezado (con logo si está disponible)
    if logo_path:
        try:
            logo = Image(logo_path, width=1.6 * cm, height=1.6 * cm)
            encabezado = Table(
                [[logo, Paragraph(nombre_empresa, titulo)]],
                colWidths=[2 * cm, 15 * cm],
            )
            encabezado.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
            ]))
            story.append(encabezado)
        except Exception:
            story.append(Paragraph(nombre_empresa, titulo))
    else:
        story.append(Paragraph(nombre_empresa, titulo))

    story.append(Paragraph(f"Factura {factura.numero_factura}", subtitulo))
    story.append(Spacer(1, 14))

    # Datos cliente / fechas — siempre en español, nunca ISO crudo
    cliente = factura.cliente
    datos = [
        ["Cliente:", cliente.razon_social, "Fecha emisión:", _fecha_es(factura.fecha_emision)],
        ["Documento:", cliente.numero_documento, "Fecha de Pago:", _fecha_es(factura.fecha_vencimiento_vigente)],
        ["Teléfono:", cliente.telefono or "-", "Estado:", factura.estado.value.capitalize()],
        ["Cuota:", factura.texto_cuota, "", ""],
    ]
    tabla_datos = Table(datos, colWidths=[3 * cm, 6 * cm, 3.5 * cm, 4 * cm])
    tabla_datos.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#333333")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tabla_datos)
    story.append(Spacer(1, 16))

    # Ítems
    encabezado_items = ["Descripción", "Cant.", "Precio unit.", "Impuesto %", "Subtotal"]
    filas = [encabezado_items]
    for item in factura.items:
        filas.append([
            item.descripcion,
            f"{float(item.cantidad):g}",
            _fmt(item.precio_unitario),
            f"{float(item.porcentaje_impuesto):g}%",
            _fmt(item.subtotal_linea),
        ])

    tabla_items = Table(filas, colWidths=[7 * cm, 1.8 * cm, 3 * cm, 2.5 * cm, 2.7 * cm])
    tabla_items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f7f7")]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(tabla_items)
    story.append(Spacer(1, 12))

    # Totales — se mantiene el desglose de "Capital" e "Interés" por
    # separado (solo cuando la factura de verdad tiene interés aplicado),
    # pero la fila final ya no dice "Capital e Interés": dice "Total",
    # con el mismo monto combinado de siempre.
    tiene_interes = factura.interes_prestamo and factura.interes_prestamo > 0
    totales = []
    if tiene_interes:
        totales.append(["Capital", _fmt(factura.subtotal)])
    totales.append(["Impuestos", _fmt(factura.impuestos)])
    if tiene_interes:
        totales.append(["Interés", _fmt(factura.interes_prestamo)])
    totales.append(["Descuento", f"-{_fmt(factura.descuento)}"])
    fila_total = len(totales)
    totales.append(["Total", _fmt(factura.total)])
    totales += [
        ["Abonado", _fmt(factura.total_abonado)],
        ["Saldo pendiente", _fmt(factura.saldo_pendiente)],
    ]
    tabla_totales = Table(totales, colWidths=[13 * cm, 4 * cm])
    estilo_totales = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
        # Resalta la fila "Total" para que se vea de un vistazo.
        ("FONTNAME", (0, fila_total), (-1, fila_total), "Helvetica-Bold"),
        ("LINEABOVE", (0, fila_total), (-1, fila_total), 0.4, colors.HexColor("#999999")),
        ("LINEBELOW", (0, fila_total), (-1, fila_total), 0.4, colors.HexColor("#999999")),
        ("TOPPADDING", (0, fila_total), (-1, fila_total), 5),
        ("BOTTOMPADDING", (0, fila_total), (-1, fila_total), 5),
    ]
    tabla_totales.setStyle(TableStyle(estilo_totales))
    story.append(tabla_totales)

    if factura.notas:
        story.append(Spacer(1, 16))
        story.append(Paragraph("Notas:", etiqueta))
        story.append(Paragraph(factura.notas, styles["Normal"]))

    def _pie_de_pagina(canvas, doc_):
        """Fecha de generación fija (la del momento en que se crea el PDF),
        siempre formateada en español y nunca como 'Invalid Date'."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#9ca3af"))
        texto = f"Generado el {_fecha_es(date.today())}"
        ancho_pagina = letter[0]
        canvas.drawCentredString(ancho_pagina / 2, 1.2 * cm, texto)
        canvas.restoreState()

    doc.build(story, onFirstPage=_pie_de_pagina, onLaterPages=_pie_de_pagina)
    return buffer.getvalue()
