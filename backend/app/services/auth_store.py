import json
import logging
from datetime import datetime, timedelta

from app.crypto import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)


def pack_auth_secret(
    auth_type: str,
    *,
    refresh_token: str | None = None,
    password: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> str:
    payload: dict[str, str] = {"auth_type": auth_type}
    if refresh_token:
        payload["refresh_token"] = refresh_token
    if password:
        payload["password"] = password
    if client_id:
        payload["client_id"] = client_id
    if client_secret:
        payload["client_secret"] = client_secret
    return encrypt_secret(json.dumps(payload))


def unpack_auth_secret(encrypted: str) -> dict:
    try:
        data = json.loads(decrypt_secret(encrypted))
        if isinstance(data, dict) and "auth_type" in data:
            return data
    except Exception:
        pass
    # Legacy: stored plain password string
    try:
        return {"auth_type": "password", "password": decrypt_secret(encrypted)}
    except Exception:
        return {"auth_type": "password", "password": encrypted}
