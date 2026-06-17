import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.azure.pdf_branding import (
    BRAND_ACCENT_BG,
    BRAND_BORDER,
    BRAND_DARK,
    BRAND_LIGHT,
    BRAND_MUTED,
    BRAND_PURPLE,
    BRAND_PURPLE_BG,
    BRAND_TEXT,
    LOCATION_LABELS,
    get_logo_path,
    page_callbacks,
)

OS_LABELS = {
    "windows11": "Windows 11 Enterprise",
    "windowsserver2025": "Windows Server 2025",
    "ubuntu": "Ubuntu Server LTS",
}


def _connection_command(vm: dict, public_ip: str) -> str:
    if not public_ip or public_ip == "En cours de provisionnement":
        return "—"
    protocol = vm.get("remote_protocol", "")
    if protocol == "RDP":
        return f"mstsc /v:{public_ip}"
    return f"ssh {vm.get('admin_username', '')}@{public_ip}"


def generate_workshop_credentials_pdf(
    workshop_name: str,
    resource_group: str,
    location: str,
    duration_days: int,
    vms: list[dict],
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=3.6 * cm,
        bottomMargin=2.2 * cm,
        title=f"Identifiants — {workshop_name}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CredTitle",
        parent=styles["Heading1"],
        fontSize=22,
        leading=26,
        textColor=BRAND_TEXT,
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "CredSubtitle",
        parent=styles["Normal"],
        fontSize=10,
        textColor=BRAND_MUTED,
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "CredSection",
        parent=styles["Heading2"],
        fontSize=11,
        textColor=BRAND_PURPLE,
        spaceBefore=8,
        spaceAfter=6,
    )
    note_style = ParagraphStyle(
        "CredNote",
        parent=styles["Normal"],
        fontSize=8,
        textColor=BRAND_MUTED,
        leading=11,
    )

    story = []
    now = datetime.now()
    region_label = LOCATION_LABELS.get(location, location)
    ready_ips = sum(1 for vm in vms if vm.get("public_ip"))

    logo_cell = ""
    logo_path = get_logo_path()
    if logo_path.exists():
        logo = Image(str(logo_path), width=1.6 * cm, height=1.6 * cm)
        logo.hAlign = "LEFT"
        logo_cell = logo

    header_table = Table(
        [[logo_cell, Paragraph(
            "<b>Identifiants de connexion</b><br/>"
            "<font size='10' color='#64748b'>Accès aux machines virtuelles de l'atelier</font>",
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

    story.append(Paragraph(workshop_name, title_style))
    story.append(Paragraph(
        f"Groupe de ressources : <b>{resource_group}</b> · Région : {region_label}<br/>"
        f"Généré le {now.strftime('%d/%m/%Y à %H:%M')}",
        subtitle_style,
    ))

    kpi_data = [[
        Paragraph("<font size='8' color='#64748b'>MACHINES</font><br/><b>"
                  f"{len(vms)} VM(s)</b>", styles["Normal"]),
        Paragraph("<font size='8' color='#64748b'>DURÉE</font><br/><b>"
                  f"{duration_days} jour(s)</b>", styles["Normal"]),
        Paragraph("<font size='8' color='#64748b'>IP ASSIGNÉES</font><br/><b>"
                  f"{ready_ips} / {len(vms)}</b>", styles["Normal"]),
        Paragraph("<font size='8' color='#64748b'>PROTOCOLES</font><br/><b>"
                  f"{', '.join(sorted({vm.get('remote_protocol', '') for vm in vms if vm.get('remote_protocol')})) or '—'}</b>",
                  styles["Normal"]),
    ]]
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

    if ready_ips < len(vms):
        story.append(Paragraph(
            "<i>Certaines adresses IP sont encore en cours de provisionnement Azure. "
            "Réexportez ce document une fois toutes les VMs prêtes.</i>",
            note_style,
        ))
        story.append(Spacer(1, 0.25 * cm))

    story.append(Paragraph(f"Machines virtuelles ({len(vms)})", section_style))

    for idx, vm in enumerate(vms, 1):
        os_label = OS_LABELS.get(vm.get("os_type", ""), vm.get("os_type", ""))
        protocol = vm.get("remote_protocol", "")
        port = vm.get("remote_port", "")
        public_ip = vm.get("public_ip") or "En cours de provisionnement"
        connection = _connection_command(vm, public_ip)

        story.append(Paragraph(
            f"<b>VM {idx} — {vm.get('name', '')}</b> "
            f"<font size='9' color='#64748b'>· {os_label}</font>",
            section_style,
        ))

        rows = [
            ["Système", os_label],
            ["Taille", vm.get("vm_size", "") or "—"],
            ["IP publique", public_ip],
            ["IP privée", vm.get("private_ip") or "—"],
            ["Protocole", f"{protocol} (port {port})" if protocol else "—"],
            ["Utilisateur", vm.get("admin_username", "") or "—"],
            ["Mot de passe", vm.get("admin_password", "") or "—"],
            ["Commande", connection],
        ]

        table = Table(rows, colWidths=[4.2 * cm, 11.8 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), BRAND_LIGHT),
            ("TEXTCOLOR", (0, 0), (0, -1), BRAND_MUTED),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
            ("FONTNAME", (1, 6), (1, 6), "Courier-Bold"),
            ("FONTNAME", (1, 7), (1, 7), "Courier"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 6), (-1, 6), BRAND_PURPLE_BG),
            ("BOX", (0, 6), (-1, 6), 0.5, BRAND_PURPLE),
            ("ROWBACKGROUNDS", (0, 0), (-1, 5), [colors.white, BRAND_LIGHT]),
            ("ROWBACKGROUNDS", (0, 7), (-1, 7), [colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(table)
        story.append(Spacer(1, 0.35 * cm))

    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "<b>Document confidentiel</b> — Ne pas diffuser en dehors des participants à l'atelier. "
        "Chaque machine dispose d'un mot de passe unique. "
        "Conservez ce document en lieu sûr et détruisez-le à la fin de la formation.",
        note_style,
    ))

    doc.build(story, onFirstPage=page_callbacks("Lab Console — Identifiants de connexion"),
              onLaterPages=page_callbacks("Lab Console — Identifiants de connexion"))
    return buffer.getvalue()
