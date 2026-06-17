from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import ConsoleUser
from app.schemas import AuthResponse, ChangePasswordRequest, ConsoleLoginRequest, UserResponse
from app.services.console_auth import (
    create_access_token,
    get_current_user,
    gravatar_url,
    hash_password,
    user_display_name,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


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


@router.post("/login", response_model=AuthResponse)
async def login(req: ConsoleLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ConsoleUser).where(ConsoleUser.username == req.username.strip().lower())
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active or not verify_password(req.password, user.password_hash):
        raise HTTPException(401, "Identifiants incorrects")

    token = create_access_token(user.id)
    return AuthResponse(access_token=token, user=_user_response(user))


@router.get("/me", response_model=UserResponse)
async def me(user: ConsoleUser = Depends(get_current_user)):
    return _user_response(user)


@router.post("/change-password", response_model=UserResponse)
async def change_password(
    req: ChangePasswordRequest,
    user: ConsoleUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(400, "Mot de passe actuel incorrect")
    if req.current_password == req.new_password:
        raise HTTPException(400, "Le nouveau mot de passe doit être différent")

    user.password_hash = hash_password(req.new_password)
    user.must_change_password = False
    await db.commit()
    await db.refresh(user)
    return _user_response(user)


@router.post("/logout")
async def logout():
    return {"status": "ok"}
