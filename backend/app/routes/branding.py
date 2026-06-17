from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ConsoleUser
from app.services.branding import (
    ALLOWED_TYPES,
    get_logo_version,
    has_custom_logo,
    mark_logo_updated,
    process_and_save_logo,
    reset_custom_logo,
    resolve_logo_path,
)
from app.services.console_auth import get_current_admin

router = APIRouter(prefix="/api/branding", tags=["branding"])


@router.get("/logo")
async def get_logo_image(db: AsyncSession = Depends(get_db)):
    path = resolve_logo_path()
    if not path.exists():
        raise HTTPException(404, "Logo introuvable")
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/logo/info")
async def get_logo_info(db: AsyncSession = Depends(get_db)):
    custom = has_custom_logo()
    version = await get_logo_version(db)
    return {
        "custom": custom,
        "url": f"/api/branding/logo?v={version}",
        "version": version,
        "ideal_size": "256×256 px (carré recommandé)",
        "max_size": "512×512 px",
        "formats": ["PNG", "JPEG", "WebP", "GIF"],
    }


@router.post("/logo")
async def upload_logo(
    file: UploadFile = File(...),
    _: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if not file.content_type or file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Format non supporté — PNG, JPEG, WebP ou GIF uniquement")

    content = await file.read()
    try:
        width, height = process_and_save_logo(content, file.content_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    version = await mark_logo_updated(db)
    return {
        "status": "ok",
        "width": width,
        "height": height,
        "url": f"/api/branding/logo?v={version}",
        "custom": True,
    }


@router.delete("/logo")
async def delete_custom_logo(
    _: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await reset_custom_logo(db)
    return {"status": "ok", "custom": False, "url": "/api/branding/logo?v=default"}
