"""Generacion de PDFs: Oferta Cliente (limpia) e Informe Interno (completo)."""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app.schemas.epi_schemas import ClientOffer, InternalReport, SingleItemOffer, SingleItemInternalReport
from app.services.pump_curve import build_curve_drawing

# Identidad visual (colores y tipografias reales de la web, agosto 2026)
NAVY_DEEP = colors.HexColor("#071527")
NAVY = colors.HexColor("#0e2b4d")
BRASS = colors.HexColor("#c69a45")
BRASS_BRIGHT = colors.HexColor("#e0b25f")
INK = colors.HexColor("#1a2433")
INK_SOFT = colors.HexColor("#4a5568")
# alias retrocompatibles (el resto del fichero usaba estos nombres)
NAVY_TEXT = INK
GOLD = BRASS

_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
_LOGO_PATH = os.path.join(_ASSETS_DIR, "logo_transparent.png")
_MONO_REGULAR = os.path.join(_ASSETS_DIR, "fonts", "IBMPlexMono-Regular.ttf")
_MONO_BOLD = os.path.join(_ASSETS_DIR, "fonts", "IBMPlexMono-Bold.ttf")

# IBM Plex Mono es la tipografia real de la web para etiquetas/eyebrows.
# Cormorant (titulares web) no tiene sustituto exacto disponible sin conexion
# a internet -> se usa Times (serif clasica) como aproximacion mas cercana.
_MONO_AVAILABLE = os.path.exists(_MONO_REGULAR) and os.path.exists(_MONO_BOLD)
if _MONO_AVAILABLE:
    pdfmetrics.registerFont(TTFont("IBMPlexMono", _MONO_REGULAR))
    pdfmetrics.registerFont(TTFont("IBMPlexMono-Bold", _MONO_BOLD))
_MONO_FONT = "IBMPlexMono" if _MONO_AVAILABLE else "Courier"

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=NAVY_TEXT, fontName="Times-Bold")
h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=NAVY_TEXT, fontName="Times-Bold")
body = ParagraphStyle("body", parent=styles["BodyText"], fontName="Times-Roman")
_eyebrow = ParagraphStyle(
    "eyebrow", parent=styles["Normal"], fontName=_MONO_FONT, fontSize=7.5,
    textColor=BRASS, alignment=TA_CENTER, spaceAfter=3,
)
_header_subtitle = ParagraphStyle(
    "header_subtitle", parent=styles["Normal"], fontName="Times-Italic",
    textColor=NAVY_TEXT, alignment=TA_CENTER, fontSize=11, spaceAfter=2,
)
_header_address = ParagraphStyle(
    "header_address", parent=styles["Normal"], fontName=_MONO_FONT,
    textColor=INK_SOFT, alignment=TA_CENTER, fontSize=7.5,
)


def _company_header(elements, subtitle: str):
    """Cabecera de marca: banner oscuro con el logo (igual que la web),
    seguida del subtítulo del documento y la dirección, centrados."""
    if os.path.exists(_LOGO_PATH):
        logo_img = Image(_LOGO_PATH, width=90 * mm, height=90 * mm * (575 / 1106))
        logo_img.hAlign = "CENTER"
        banner = Table([[logo_img]], colWidths=[170 * mm])
        banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), NAVY_DEEP),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8 * mm),
        ]))
        elements.append(banner)
        elements.append(Spacer(1, 5 * mm))
    else:
        elements.append(Paragraph("EFICIENCIA Y PRECISIÓN INDUSTRIAL, S.L.", h1))

    elements.append(Paragraph(subtitle, _header_subtitle))
    elements.append(Paragraph(
        "CALLE ANDRÉS ELISEO MAÑARICUA Nº 7, BAJO · 48013 BILBAO (BIZKAIA)", _header_address))
    elements.append(Spacer(1, 10 * mm))


def generate_client_offer_pdf(offer: ClientOffer, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    elements = []
    _company_header(elements, "Solución Técnica y Oferta Comercial — Asistente de IA EPi")

    if offer.contact and (offer.contact.company_name or offer.contact.contact_name):
        dest = offer.contact.company_name or offer.contact.contact_name
        elements.append(Paragraph(f"Para: {dest}", body))
        if offer.contact.contact_name and offer.contact.company_name:
            elements.append(Paragraph(f"At./ {offer.contact.contact_name}", body))
        elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph(f"<b>Precio total final:</b> {offer.final_price_eur:,.2f} €", h2))
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("Equipo de bombeo recomendado", h2))
    elements.append(Paragraph(
        f"{offer.pump.technology.value} — {offer.pump.brand} {offer.pump.model} "
        f"(perfil {offer.pump.profile.value})", body))
    elements.append(Paragraph(offer.pump.description, body))
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("Materiales y piping incluidos", h2))
    data = [["Elemento", "Especificación", "Cantidad"]]
    for m in offer.materials:
        data.append([m.element, m.specification, m.quantity_display])
    table = Table(data, colWidths=[55 * mm, 80 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("Parámetros operativos", h2))
    elements.append(Paragraph(
        f"Fluido: {offer.fluid_name} · Caudal: {offer.flow_m3h} m3/h · "
        f"Velocidad: {offer.velocity_ms} m/s · TDH: {offer.tdh_m} m.c.f.", body))

    elements.append(Spacer(1, 4 * mm))
    try:
        curve_drawing = build_curve_drawing(
            offer.pump, operating_flow_m3h=offer.flow_m3h, operating_head_m=offer.tdh_m,
        )
        elements.append(curve_drawing)
        if offer.pump.curve_reference_url:
            elements.append(Paragraph(
                f"Curva oficial del fabricante: {offer.pump.curve_reference_url}", body))
        else:
            elements.append(Paragraph(
                "Curva orientativa, calculada a partir del caudal y la altura máximos de "
                "catálogo de esta bomba (no es la curva exacta publicada por el fabricante).",
                body))
    except Exception:
        pass  # si la generacion de la curva falla, no bloquea el resto de la oferta

    elements.append(Spacer(1, 6 * mm))
    elements.append(Paragraph(
        "<b>En caso de aceptación del presupuesto</b>, envíe el pedido oficial a "
        "<b>pedidos@eficienciayprecisionindustrial.com</b>. Si no recibe confirmación de "
        "la recepción de su pedido, es posible que este no se haya tramitado — "
        "por favor, contacte con nosotros en ese caso.", body))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("Propuesta válida durante 30 días naturales.", body))

    doc.build(elements)
    return output_path


def generate_internal_report_pdf(report: InternalReport, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    elements = []
    _company_header(elements, "Informe Técnico y Financiero — USO INTERNO")

    elements.append(Paragraph(f"Fecha consulta: {report.consultation_date} · Cliente ID: {report.client_id}", body))
    elements.append(Paragraph(f"Estado red: {report.network_status}", body))
    if report.contact:
        c = report.contact
        elements.append(Paragraph(
            f"Contacto: {c.contact_name or '-'} · Empresa: {c.company_name or '-'} · "
            f"Tel: {c.phone or '-'} · Email: {c.email or '-'}", body))
    elements.append(Spacer(1, 6 * mm))

    h = report.hydraulics
    elements.append(Paragraph("Análisis hidráulico", h2))
    elements.append(Paragraph(
        f"Q={h.flow_m3h} m3/h · v={h.velocity_ms} m/s · Re={h.reynolds:.0f} ({h.flow_regime}) · "
        f"TDH={h.total_dynamic_head_m} m.c.f. · Motor rec.: {h.recommended_motor_kw} kW", body))
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("Desglose de materiales (coste real + margen web +40%)", h2))
    data = [["Componente", "Proveedor", "Cant.", "Coste real", "PVP +40%"]]
    for line in report.materials_breakdown.lines:
        data.append([line.component, line.supplier, f"{line.quantity}",
                     f"{line.total_cost_real_eur:.2f} €", f"{line.pvp_with_margin_eur:.2f} €"])
    table = Table(data, colWidths=[55 * mm, 45 * mm, 15 * mm, 25 * mm, 25 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    c = report.commercial
    elements.append(Paragraph("Análisis financiero interno", h2))
    fin_data = [
        ["Coste bomba base", f"{c.pump_base_cost_eur:.2f} €"],
        ["Componentes web (+40%)", f"{c.materials_pvp_40_eur:.2f} €"],
        ["Mano de obra/ingeniería", f"{c.labor_engineering_eur:.2f} €"],
        ["Subtotal comercial", f"{c.subtotal_commercial_eur:.2f} €"],
        [f"Contingencia ({c.contingency_pct:.0f}%)", f"{c.contingency_amount_eur:.2f} €"],
        ["PRECIO FINAL CLIENTE", f"{c.final_client_price_eur:.2f} €"],
        ["Beneficio bruto estimado", f"{c.estimated_gross_profit_eur:.2f} €"],
    ]
    ftable = Table(fin_data, colWidths=[80 * mm, 40 * mm])
    ftable.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, -2), (-1, -2), GOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(ftable)
    elements.append(Spacer(1, 6 * mm))

    p = report.selected_pump
    elements.append(Paragraph("Bomba seleccionada y razonamiento de tecnología (V7)", h2))
    elements.append(Paragraph(
        f"<b>{p.technology.value}</b> — {p.brand} {p.model} "
        f"(rango {p.min_flow_m3h}-{p.max_flow_m3h} m3/h, {p.max_head_m} m.c.f. máx.)", body))
    if report.technology_reasoning:
        for rec in report.technology_reasoning:
            estado = "✓ APTA" if rec.suitable else "✗ DESCARTADA"
            elements.append(Paragraph(
                f"<b>{rec.technology.value}</b> [{estado}, score={rec.score:.2f}]", body))
            for reason in rec.reasons:
                elements.append(Paragraph(f"　+ {reason}", body))
            for warn in rec.warnings:
                elements.append(Paragraph(f"　! {warn}", body))
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("Compatibilidad química fluido/material (V8)", h2))
    if report.chemical_compatibility:
        cc = report.chemical_compatibility
        cuerpo = cc.body_material or "sin dato"
        elastomero = cc.elastomer_material or "sin dato"
        if cc.compatible is True:
            estado_txt = "✓ COMPATIBLE"
        elif cc.compatible is False:
            estado_txt = "✗ NO COMPATIBLE — REVISAR ANTES DE OFERTAR"
        else:
            estado_txt = "? SIN CONFIRMAR — verificar manualmente"
        elements.append(Paragraph(
            f"Fluido: <b>{cc.fluid_name}</b> · Cuerpo: {cuerpo} · Elastómero/junta: {elastomero} · "
            f"<b>{estado_txt}</b>", body))
        for w in cc.warnings:
            elements.append(Paragraph(f"　! {w}", body))
    else:
        elements.append(Paragraph("No evaluada.", body))
    elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph("Instrucciones para el ingeniero de proyecto", h2))
    elements.append(Paragraph(report.engineer_instructions, body))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("CONFIDENCIAL — USO INTERNO EFICIENCIA Y PRECISIÓN INDUSTRIAL S.L.", body))

    doc.build(elements)
    return output_path


# ---------------------------------------------------------------------------
# NUEVO — Oferta de un unico elemento identificado por foto
# ---------------------------------------------------------------------------

def generate_single_item_offer_pdf(offer: SingleItemOffer, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    elements = []
    _company_header(elements, "Oferta de Elemento Individual — Asistente de IA EPi")

    if offer.contact and (offer.contact.company_name or offer.contact.contact_name):
        dest = offer.contact.company_name or offer.contact.contact_name
        elements.append(Paragraph(f"Para: {dest}", body))
        if offer.contact.contact_name and offer.contact.company_name:
            elements.append(Paragraph(f"At./ {offer.contact.contact_name}", body))
        elements.append(Spacer(1, 6 * mm))

    elements.append(Paragraph(f"<b>Precio total final:</b> {offer.final_price_eur:,.2f} €", h2))
    elements.append(Spacer(1, 6 * mm))

    data = [["Elemento", "Cantidad"], [offer.item_name, f"{offer.quantity:g} {offer.unit}"]]
    table = Table(data, colWidths=[110 * mm, 60 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph(
        "Precio llave en mano (suministro e instalación de este elemento). "
        "Consulte con nosotros si desea ampliar la oferta al resto de la instalación.",
        body,
    ))
    elements.append(Spacer(1, 8 * mm))
    elements.append(Paragraph(
        "<b>En caso de aceptación del presupuesto</b>, envíe el pedido oficial a "
        "<b>pedidos@eficienciayprecisionindustrial.com</b>. Si no recibe confirmación de "
        "la recepción de su pedido, es posible que este no se haya tramitado — "
        "por favor, contacte con nosotros en ese caso.", body))

    doc.build(elements)
    return output_path


def generate_single_item_internal_pdf(report: SingleItemInternalReport, output_path: str) -> str:
    doc = SimpleDocTemplate(output_path, pagesize=A4)
    elements = []
    _company_header(elements, "Informe Interno — Elemento Individual (EPi)")

    l = report.item_line
    elements.append(Paragraph(f"Cliente: {report.client_id}", body))
    elements.append(Paragraph(f"Fecha: {report.consultation_date.isoformat()}", body))
    elements.append(Spacer(1, 4 * mm))

    data = [
        ["Elemento", l.component],
        ["Proveedor", l.supplier],
        ["Cantidad", f"{l.quantity:g} {l.unit}"],
        ["Coste real unitario", f"{l.unit_cost_real_eur:.2f} €"],
        ["Coste real total", f"{l.total_cost_real_eur:.2f} €"],
        ["Margen web", f"{l.margin_pct:.0f}%"],
        ["PVP con margen", f"{l.pvp_with_margin_eur:.2f} €"],
    ]
    table = Table(data, colWidths=[70 * mm, 90 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8)]))
    elements.append(table)
    elements.append(Spacer(1, 6 * mm))

    c = report.commercial
    fin_data = [
        ["Subtotal comercial", f"{c.subtotal_commercial_eur:.2f} €"],
        [f"Contingencia ({c.contingency_pct:.0f}%)", f"{c.contingency_amount_eur:.2f} €"],
        ["PRECIO FINAL CLIENTE", f"{c.final_client_price_eur:.2f} €"],
        ["Beneficio bruto estimado", f"{c.estimated_gross_profit_eur:.2f} €"],
    ]
    ftable = Table(fin_data, colWidths=[80 * mm, 40 * mm])
    ftable.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, -2), (-1, -2), GOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(ftable)
    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("CONFIDENCIAL — USO INTERNO EFICIENCIA Y PRECISIÓN INDUSTRIAL S.L.", body))

    doc.build(elements)
    return output_path
