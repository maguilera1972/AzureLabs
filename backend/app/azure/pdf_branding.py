from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

from app.services.branding import resolve_logo_path

DEFAULT_LOGO_PATH = Path(__file__).resolve().parents[3] / "assets" / "logo.png"


def get_logo_path() -> Path:
    return resolve_logo_path()

BRAND_CYAN = colors.HexColor("#56ccf2")
BRAND_PURPLE = colors.HexColor("#8e2de2")
BRAND_DARK = colors.HexColor("#121824")
BRAND_TEXT = colors.HexColor("#1a2332")
BRAND_MUTED = colors.HexColor("#64748b")
BRAND_LIGHT = colors.HexColor("#f0f4fa")
BRAND_BORDER = colors.HexColor("#e2e8f0")
BRAND_ACCENT_BG = colors.HexColor("#eef6fc")
BRAND_PURPLE_BG = colors.HexColor("#f5f0ff")

LOCATION_LABELS = {
    "francecentral": "France Central",
    "westeurope": "West Europe",
    "northeurope": "North Europe",
    "switzerlandnorth": "Switzerland North",
}


def draw_header(canvas, _doc):
    width, height = A4
    canvas.saveState()

    steps = 40
    band_h = 3.2 * cm
    for i in range(steps):
        ratio = i / max(steps - 1, 1)
        r = BRAND_CYAN.red + (BRAND_PURPLE.red - BRAND_CYAN.red) * ratio
        g = BRAND_CYAN.green + (BRAND_PURPLE.green - BRAND_CYAN.green) * ratio
        b = BRAND_CYAN.blue + (BRAND_PURPLE.blue - BRAND_CYAN.blue) * ratio
        canvas.setFillColor(colors.Color(r, g, b))
        slice_w = width / steps
        canvas.rect(i * slice_w, height - band_h, slice_w + 1, band_h, fill=1, stroke=0)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 11)
    canvas.drawString(2 * cm, height - 1.15 * cm, "Lab Console")
    canvas.setFont("Helvetica", 8)
    canvas.drawString(2 * cm, height - 1.55 * cm, "Azure Training Labs")
    canvas.restoreState()


def draw_footer(canvas, doc, label: str):
    canvas.saveState()
    canvas.setStrokeColor(BRAND_BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
    canvas.setFillColor(BRAND_MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawString(2 * cm, 1.0 * cm, label)
    canvas.drawRightString(A4[0] - 2 * cm, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def page_callbacks(footer_label: str):
    def _page(canvas, doc):
        draw_header(canvas, doc)
        draw_footer(canvas, doc, footer_label)

    return _page
