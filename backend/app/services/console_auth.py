import hashlib
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ConsoleUser

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24
DEFAULT_NEW_USER_PASSWORD = "welcome"

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def gravatar_url(email: str, size: int = 80) -> str:
    if not email or not email.strip():
        return f"https://www.gravatar.com/avatar/?d=mp&s={size}"
    digest = hashlib.md5(email.strip().lower().encode()).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?d=mp&s={size}"


def user_display_name(user: ConsoleUser) -> str:
    parts = [p for p in (user.first_name, user.last_name) if p and p.strip()]
    return " ".join(parts) if parts else user.username


async def get_user_by_id(db: AsyncSession, user_id: int) -> ConsoleUser | None:
    result = await db.execute(select(ConsoleUser).where(ConsoleUser.id == user_id))
    return result.scalar_one_or_none()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> ConsoleUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Authentification requise")

    try:
        payload = jwt.decode(credentials.credentials, settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except Exception as exc:
        raise HTTPException(401, "Token invalide ou expiré") from exc

    user = await get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(401, "Utilisateur introuvable ou désactivé")
    return user


async def get_current_admin(user: ConsoleUser = Depends(get_current_user)) -> ConsoleUser:
    if not user.is_admin:
        raise HTTPException(403, "Droits administrateur requis")
    return user
