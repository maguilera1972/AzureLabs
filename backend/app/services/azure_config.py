from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.azure.constants import AZURE_CLI_CLIENT_ID
from app.config import settings
from app.crypto import decrypt_secret, encrypt_secret
from app.models import AppSetting


def _authority_for_tenant(tenant_id: str | None) -> str:
    if tenant_id:
        return f"https://login.microsoftonline.com/{tenant_id}"
    return AZURE_AUTHORITY_ORGS


async def get_azure_client_id(db: AsyncSession | None = None) -> str:
    if db:
        value = await _get_setting(db, "azure_client_id")
        if value:
            return value
    return settings.azure_client_id


async def get_azure_tenant_id(db: AsyncSession | None = None) -> str:
    if db:
        value = await _get_setting(db, "azure_tenant_id")
        if value:
            return value
    return settings.azure_tenant_id


async def get_azure_client_secret(db: AsyncSession | None = None) -> str | None:
    if db:
        encrypted = await _get_setting(db, "azure_client_secret_encrypted")
        if encrypted:
            return decrypt_secret(encrypted)
    if settings.azure_client_secret:
        return settings.azure_client_secret
    return None


async def get_azure_authority(db: AsyncSession | None = None) -> str:
    tenant_id = await get_azure_tenant_id(db)
    return _authority_for_tenant(tenant_id or None)


async def is_custom_app_configured(db: AsyncSession) -> bool:
    client_id = await get_azure_client_id(db)
    return client_id != AZURE_CLI_CLIENT_ID


async def is_oauth_ready(db: AsyncSession) -> bool:
    if not await is_custom_app_configured(db):
        return False
    return bool(await get_azure_client_secret(db))


async def save_azure_auth_config(
    db: AsyncSession,
    client_id: str,
    tenant_id: str = "",
    client_secret: str | None = None,
) -> None:
    existing_secret = await get_azure_client_secret(db)
    if not client_secret and not existing_secret:
        raise ValueError(
            "Le Client Secret est obligatoire. Créez-le dans Azure AD "
            "(Certificates & secrets), puis saisissez sa valeur."
        )
    await _set_setting(db, "azure_client_id", client_id.strip())
    await _set_setting(db, "azure_tenant_id", tenant_id.strip())
    if client_secret:
        await _set_setting(db, "azure_client_secret_encrypted", encrypt_secret(client_secret.strip()))
    await db.commit()


async def _get_setting(db: AsyncSession, key: str) -> str | None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _set_setting(db: AsyncSession, key: str, value: str) -> None:
    result = await db.execute(select(AppSetting).where(AppSetting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


from app.azure.constants import AZURE_AUTHORITY_ORGS  # noqa: E402
