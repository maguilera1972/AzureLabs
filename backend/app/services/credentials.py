from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.azure.auth import AzureCredentials
from app.models import AzureConnection
from app.services.auth_store import unpack_auth_secret


async def get_active_credentials(db: AsyncSession) -> AzureCredentials | None:
    result = await db.execute(
        select(AzureConnection).where(AzureConnection.is_active == True).order_by(AzureConnection.id.desc())
    )
    conn = result.scalar_one_or_none()
    if not conn:
        return None

    auth = unpack_auth_secret(conn.client_secret_encrypted)
    auth_type = auth.get("auth_type") or conn.auth_type or "oauth"

    return AzureCredentials(
        tenant_id=conn.tenant_id,
        username=conn.client_id,
        subscription_id=conn.subscription_id,
        auth_type=auth_type,
        password=auth.get("password"),
        refresh_token=auth.get("refresh_token"),
        client_id=auth.get("client_id"),
        client_secret=auth.get("client_secret"),
    )


async def get_active_connection_record(db: AsyncSession) -> AzureConnection | None:
    result = await db.execute(
        select(AzureConnection).where(AzureConnection.is_active == True).order_by(AzureConnection.id.desc())
    )
    return result.scalar_one_or_none()
