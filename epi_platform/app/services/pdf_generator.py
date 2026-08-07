"""Generacion de PDFs: Oferta Cliente (limpia) e Informe Interno (completo)."""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.schemas.epi_schemas import ClientOffer, InternalReport, SingleItemOffer, SingleItemInternalReport

NAVY = colors.HexColor("#0B1D36")
GOLD = colors.HexColor("#C9A227")

styles = getSampleStyleSheet()
h1 = ParagraphStyle("h1", parent=styles["Heading1"], textColor=NAVY)
h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=NAVY)
body = styles["BodyText"]


def _company_header(elements, subtitle: str):
    elements.append(Paragraph("EFICIENCIA Y PRECISIÓN INDUSTRIAL, S.L.", h1))
    elements.append(Paragraph(subtitle, h2))
    elements.append(Paragraph("Calle Andrés Eliseo Mañaricua nº 7, Bajo, 48013 Bilbao (Bizkaia)", body))
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
        f"Fluido: {offer.fluid_name} · Caudal: {offer.flow_m3h} m³/h · "
        f"Velocidad: {offer.velocity_ms} m/s · TDH: {offer.tdh_m} m.c.f.", body))

    elements.append(Spacer(1, 10 * mm))
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
        f"Q={h.flow_m3h} m³/h · v={h.velocity_ms} m/s · Re={h.reynolds:.0f} ({h.flow_regime}) · "
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
