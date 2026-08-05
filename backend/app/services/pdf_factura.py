"""Genera el PDF de una factura para descargar o enviar al cliente."""
import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

from app.models.factura import Factura


def _fmt(monto) -> str:
    return f"RD$ {float(monto or 0):,.2f}"


def generar_pdf_factura(factura: Factura, nombre_empresa: str = "Tu Empresa") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
    )

    styles = getSampleStyleSheet()
    titulo = ParagraphStyle("titulo", parent=styles["Title"], fontSize=20, spaceAfter=2)
    subtitulo = ParagraphStyle("subtitulo", parent=styles["Normal"], textColor=colors.grey)
    etiqueta = ParagraphStyle("etiqueta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    story = []

    # Encabezado
    story.append(Paragraph(nombre_empresa, titulo))
    story.append(Paragraph(f"Factura {factura.numero_factura}", subtitulo))
    story.append(Spacer(1, 14))

    # Datos cliente / fechas
    cliente = factura.cliente
    datos = [
        ["Cliente:", cliente.razon_social, "Fecha emisión:", str(factura.fecha_emision)],
        ["Documento:", cliente.numero_documento, "Fecha vencimiento:", str(factura.fecha_vencimiento)],
        ["Teléfono:", cliente.telefono or "-", "Estado:", factura.estado.value.capitalize()],
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

    # Totales
    totales = [
        ["Subtotal", _fmt(factura.subtotal)],
        ["Impuestos", _fmt(factura.impuestos)],
        ["Descuento", f"-{_fmt(factura.descuento)}"],
        ["Total", _fmt(factura.total)],
        ["Saldo pendiente", _fmt(factura.saldo_capital + factura.interes_acumulado + factura.recargo_mora)],
    ]
    tabla_totales = Table(totales, colWidths=[13 * cm, 4 * cm])
    tabla_totales.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 11),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
        ("TOPPADDING", (0, -1), (-1, -1), 6),
    ]))
    story.append(tabla_totales)

    if factura.notas:
        story.append(Spacer(1, 16))
        story.append(Paragraph("Notas:", etiqueta))
        story.append(Paragraph(factura.notas, styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
