import io
from datetime import datetime, timedelta

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.azure.cost_estimator import OS_LABELS
from app.azure.pdf_branding import (
    BRAND_ACCENT_BG,
    BRAND_BORDER,
    BRAND_DARK,
    BRAND_LIGHT,
    BRAND_MUTED,
    BRAND_PURPLE,
    BRAND_TEXT,
    LOCATION_LABELS,
    get_logo_path,
    page_callbacks,
)
from app.schemas import CostEstimateResponse, VMConfigInput


def _fmt_money(amount: float, currency: str) -> str:
    if currency == "EUR":
        return f"{amount:,.2f} €".replace(",", "'")
    return f"{amount:,.2f} CHF".replace(",", "'")


def _vm_config_rows(vms: list[VMConfigInput]) -> list[list[str]]:
    rows = [["Préfixe", "Système", "Quantité", "Taille VM"]]
    for cfg in vms:
        qty = max(1, min(cfg.quantity, 100))
        os_label = OS_LABELS.get(cfg.os_type, cfg.os_type)
        rows.append([
            cfg.name_prefix or "—",
            os_label,
            str(qty),
            cfg.vm_size or "Standard_D4s_v3",
        ])
    return rows


def generate_cost_quote_pdf(
    workshop_name: str,
    client_name: str,
    location: str,
    schedule_start_hour: int,
    schedule_stop_hour: int,
    vms: list[VMConfigInput],
    cost: CostEstimateResponse,
    currency: str = "CHF",
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=3.6 * cm,
        bottomMargin=2.2 * cm,
        title=f"Offre — {workshop_name}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "QuoteTitle",
        parent=styles["Heading1"],
        fontSize=22,
        leading=26,
        textColor=BRAND_TEXT,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "QuoteSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=BRAND_MUTED,
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "QuoteSection",
        parent=styles["Heading2"],
        fontSize=12,
        textColor=BRAND_PURPLE,
        spaceBefore=10,
        spaceAfter=8,
    )
    note_style = ParagraphStyle(
        "QuoteNote",
        parent=styles["Normal"],
        fontSize=8,
        textColor=BRAND_MUTED,
        leading=11,
    )

    story = []
    now = datetime.now()
    valid_until = now + timedelta(days=30)
    region_label = LOCATION_LABELS.get(location, location)
    display_name = workshop_name.strip() or "Atelier Azure"
    client_line = client_name.strip() or "—"

    # Logo + title row
    logo_cell = ""
    logo_path = get_logo_path()
    if logo_path.exists():
        logo = Image(str(logo_path), width=1.6 * cm, height=1.6 * cm)
        logo.hAlign = "LEFT"
        logo_cell = logo

    header_table = Table(
        [[logo_cell, Paragraph(
            f"<b>Offre commerciale</b><br/>"
            f"<font size='10' color='#64748b'>Provisionnement d'atelier de formation Azure</font>",
            ParagraphStyle("Hdr", parent=styles["Normal"], fontSize=14, leading=18, alignment=TA_RIGHT),
        )]],
        colWidths=[2.2 * cm, 13.8 * cm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.35 * cm))

    story.append(Paragraph(display_name, title_style))
    story.append(Paragraph(
        f"Client : <b>{client_line}</b> · Région : {region_label}<br/>"
        f"Établie le {now.strftime('%d/%m/%Y')} · Valable jusqu'au {valid_until.strftime('%d/%m/%Y')}",
        subtitle_style,
    ))

    # Summary KPI cards
    total = cost.total_workshop_chf if currency == "CHF" else cost.total_workshop_eur
    daily = cost.total_daily_chf if currency == "CHF" else cost.total_daily_eur
    kpi_data = [
        [
            Paragraph("<font size='8' color='#64748b'>DURÉE</font><br/><b>"
                      f"{cost.duration_days} jour(s)</b>", styles["Normal"]),
            Paragraph("<font size='8' color='#64748b'>MACHINES</font><br/><b>"
                      f"{cost.total_vm_count} VM(s)</b>", styles["Normal"]),
            Paragraph("<font size='8' color='#64748b'>PLANIFICATION</font><br/><b>"
                      f"{schedule_start_hour}h → {schedule_stop_hour}h</b>", styles["Normal"]),
            Paragraph("<font size='8' color='#64748b'>COÛT TOTAL</font><br/><b>"
                      f"{_fmt_money(total, currency)}</b>", styles["Normal"]),
        ]
    ]
    kpi_table = Table(kpi_data, colWidths=[4 * cm, 4 * cm, 4 * cm, 4 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_ACCENT_BG),
        ("BOX", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, BRAND_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 0.45 * cm))

    # VM configuration
    story.append(Paragraph("Contenu de l'atelier", section_style))
    vm_rows = _vm_config_rows(vms)
    vm_table = Table(vm_rows, colWidths=[4 * cm, 5 * cm, 2.5 * cm, 4.5 * cm])
    vm_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(vm_table)
    story.append(Spacer(1, 0.4 * cm))

    # Cost breakdown
    story.append(Paragraph("Détail des coûts estimés", section_style))
    cost_rows = [["Ressource", "Qté (h)", "Prix / h", "Total"]]
    for item in cost.items:
        unit = item.unit_price_chf if currency == "CHF" else item.unit_price_eur
        line_total = item.monthly_cost_chf if currency == "CHF" else item.monthly_cost_eur
        cost_rows.append([
            item.resource,
            f"{item.quantity:,.1f}".replace(",", "'"),
            _fmt_money(unit, currency),
            _fmt_money(line_total, currency),
        ])

    cost_table = Table(cost_rows, colWidths=[7.5 * cm, 2.2 * cm, 2.8 * cm, 3.5 * cm])
    cost_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(cost_table)
    story.append(Spacer(1, 0.35 * cm))

    # Total highlight
    alt_currency = "EUR" if currency == "CHF" else "CHF"
    alt_total = cost.total_workshop_eur if currency == "CHF" else cost.total_workshop_chf
    total_table = Table(
        [[
            Paragraph("<font size='10' color='#64748b'>Total atelier</font>", styles["Normal"]),
            Paragraph(
                f"<font size='16'><b>{_fmt_money(total, currency)}</b></font><br/>"
                f"<font size='9' color='#64748b'>soit {_fmt_money(daily, currency)} / jour · "
                f"{_fmt_money(alt_total, alt_currency)}</font>",
                ParagraphStyle("Total", parent=styles["Normal"], alignment=TA_RIGHT),
            ),
        ]],
        colWidths=[8 * cm, 8 * cm],
    )
    total_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f0ff")),
        ("BOX", (0, 0), (-1, -1), 1, BRAND_PURPLE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(total_table)
    story.append(Spacer(1, 0.5 * cm))

    rate = cost.exchange_rate
    story.append(Paragraph(
        "<b>Conditions</b><br/>"
        "• Estimation basée sur les tarifs publics Azure (consommation à l'usage).<br/>"
        f"• Planification : {cost.hours_per_day:.0f} heures d'utilisation par jour sur {cost.duration_days} jour(s).<br/>"
        f"• Taux de change : 1 € = {rate.eur_to_chf:.4f} CHF ({rate.source}, {rate.updated_at[:10]}).<br/>"
        "• Les coûts réels peuvent varier selon l'utilisation effective et les évolutions tarifaires Azure.<br/>"
        "• Cette offre est fournie à titre indicatif et ne constitue pas un engagement contractuel.",
        note_style,
    ))

    doc.build(
        story,
        onFirstPage=page_callbacks("Lab Console — Offre de provisionnement Azure"),
        onLaterPages=page_callbacks("Lab Console — Offre de provisionnement Azure"),
    )
    return buffer.getvalue()
