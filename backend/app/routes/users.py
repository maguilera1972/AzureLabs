from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ConsoleUser, Workshop
from app.schemas import AdminSetPasswordRequest, UserCreateRequest, UserResponse, UserUpdateRequest
from app.services.console_auth import (
    DEFAULT_NEW_USER_PASSWORD,
    get_current_admin,
    gravatar_url,
    hash_password,
    user_display_name,
)

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[])


def _user_response(user: ConsoleUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        display_name=user_display_name(user),
        gravatar_url=gravatar_url(user.email),
        must_change_password=user.must_change_password,
        is_admin=user.is_admin,
        is_active=user.is_active,
        created_at=user.created_at.isoformat(),
    )


@router.get("", response_model=list[UserResponse])
async def list_users(
    _: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ConsoleUser).order_by(ConsoleUser.username))
    return [_user_response(u) for u in result.scalars().all()]


@router.post("", response_model=UserResponse)
async def create_user(
    req: UserCreateRequest,
    _: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(ConsoleUser).where(ConsoleUser.username == req.username))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"L'utilisateur '{req.username}' existe déjà")

    user = ConsoleUser(
        username=req.username,
        first_name=req.first_name.strip(),
        last_name=req.last_name.strip(),
        email=req.email.strip().lower(),
        password_hash=hash_password(DEFAULT_NEW_USER_PASSWORD),
        must_change_password=True,
        is_admin=False,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    req: UserUpdateRequest,
    admin: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ConsoleUser).where(ConsoleUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    if req.is_admin is False and user.is_admin and user.id == admin.id:
        raise HTTPException(400, "Vous ne pouvez pas retirer vos propres droits administrateur")

    if req.is_active is False and user.id == admin.id:
        raise HTTPException(400, "Vous ne pouvez pas désactiver votre propre compte")

    if req.first_name is not None:
        user.first_name = req.first_name.strip()
    if req.last_name is not None:
        user.last_name = req.last_name.strip()
    if req.email is not None:
        user.email = req.email.strip().lower()
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.is_admin is not None:
        user.is_admin = req.is_admin

    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.post("/{user_id}/reset-password", response_model=UserResponse)
async def reset_user_password(
    user_id: int,
    admin: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ConsoleUser).where(ConsoleUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.password_hash = hash_password(DEFAULT_NEW_USER_PASSWORD)
    user.must_change_password = True
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.post("/{user_id}/set-password", response_model=UserResponse)
async def set_user_password(
    user_id: int,
    req: AdminSetPasswordRequest,
    admin: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ConsoleUser).where(ConsoleUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    user.password_hash = hash_password(req.new_password)
    user.must_change_password = req.must_change_password
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    admin: ConsoleUser = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ConsoleUser).where(ConsoleUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Utilisateur introuvable")

    if user.id == admin.id:
        raise HTTPException(400, "Vous ne pouvez pas supprimer votre propre compte")

    if user.is_admin and user.is_active:
        admin_count = await db.execute(
            select(func.count()).select_from(ConsoleUser).where(
                ConsoleUser.is_admin.is_(True),
                ConsoleUser.is_active.is_(True),
            )
        )
        if (admin_count.scalar() or 0) <= 1:
            raise HTTPException(400, "Impossible de supprimer le dernier administrateur actif")

    await db.execute(
        update(Workshop)
        .where(Workshop.created_by_user_id == user_id)
        .values(created_by_user_id=None)
    )
    await db.delete(user)
    await db.commit()
    return {"status": "deleted", "id": user_id}
