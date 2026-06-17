from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppSetting
from app.services.azure_config import _get_setting, _set_setting

ROOT = Path("/var/www/lab-console")
DEFAULT_LOGO_PATH = ROOT / "assets" / "logo.png"
BRANDING_DIR = ROOT / "data" / "branding"
CUSTOM_LOGO_PATH = BRANDING_DIR / "logo.png"

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 512
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


def ensure_branding_dir() -> None:
    BRANDING_DIR.mkdir(parents=True, exist_ok=True)


def resolve_logo_path() -> Path:
    if CUSTOM_LOGO_PATH.exists() and CUSTOM_LOGO_PATH.stat().st_size > 0:
        return CUSTOM_LOGO_PATH
    return DEFAULT_LOGO_PATH


def has_custom_logo() -> bool:
    return CUSTOM_LOGO_PATH.exists() and CUSTOM_LOGO_PATH.stat().st_size > 0


async def get_logo_version(db: AsyncSession) -> str:
    if not has_custom_logo():
        return "default"
    stored = await _get_setting(db, "logo_updated_at")
    if stored:
        return stored
    return str(int(CUSTOM_LOGO_PATH.stat().st_mtime))


def process_and_save_logo(content: bytes, content_type: str) -> tuple[int, int]:
    ensure_branding_dir()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Fichier trop volumineux (max {MAX_UPLOAD_BYTES // 1024 // 1024} Mo)")

    if content_type not in ALLOWED_TYPES:
        raise ValueError("Format non supporté — utilisez PNG, JPEG, WebP ou GIF")

    img = Image.open(BytesIO(content))
    if img.mode in ("RGBA", "P", "LA"):
        background = Image.new("RGBA", img.size, (255, 255, 255, 0))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    if w < 32 or h < 32:
        raise ValueError("Image trop petite — minimum 32×32 pixels")

    if w > MAX_DIMENSION or h > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    if img.mode == "RGBA":
        img.save(CUSTOM_LOGO_PATH, format="PNG", optimize=True)
    else:
        img.convert("RGB").save(CUSTOM_LOGO_PATH, format="PNG", optimize=True)

    final = Image.open(CUSTOM_LOGO_PATH)
    return final.size


async def mark_logo_updated(db: AsyncSession) -> str:
    version = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    await _set_setting(db, "logo_updated_at", version)
    await db.commit()
    return version


async def reset_custom_logo(db: AsyncSession) -> None:
    if CUSTOM_LOGO_PATH.exists():
        CUSTOM_LOGO_PATH.unlink()
    await _set_setting(db, "logo_updated_at", "")
    await db.commit()
