import logging
import secrets
import uuid

import msal
from sqlalchemy.ext.asyncio import AsyncSession

from app.azure.auth import (
    _decode_jwt_claims,
    _get_tenant_display_name,
    list_subscriptions_from_credential,
)
from app.azure.constants import AZURE_CLI_CLIENT_ID, MANAGEMENT_SCOPES
from app.azure.msal_credential import RefreshTokenCredential
from app.azure.msal_factory import create_msal_app
from app.config import settings
from app.services.azure_config import (
    get_azure_authority,
    get_azure_client_id,
    get_azure_client_secret,
    get_azure_tenant_id,
    is_custom_app_configured,
    is_oauth_ready,
)

logger = logging.getLogger(__name__)


def friendly_oauth_error(message: str) -> str:
    msg = message.lower()
    if "aadsts7000218" in msg or "client_assertion" in msg or "client_secret" in msg:
        return (
            "Le Client Secret de l'application Azure AD est requis. "
            "Créez un secret dans Certificates & secrets, puis saisissez-le dans la configuration Lab Console."
        )
    if (
        "aadsts53003" in msg
        or "conditional access" in msg
        or "ne respecte pas les critères" in msg
        or "access has been blocked" in msg
        or "blocked by conditional access" in msg
    ):
        return (
            "Accès bloqué par une politique Conditional Access de votre tenant. "
            "Enregistrez une application « Lab Console » dans Azure AD, saisissez son Client ID "
            "dans la configuration ci-dessous, puis utilisez « Connexion via navigateur »."
        )
    if "aadsts50011" in msg or "redirect_uri" in msg:
        return (
            "URI de redirection non reconnue. Vérifiez que l'URI affichée dans la configuration "
            "est bien enregistrée dans votre application Azure AD (plateforme Web)."
        )
    if "aadsts700016" in msg or "application was not found" in msg:
        return "Application Azure AD introuvable. Vérifiez le Client ID configuré."
    return message


async def _msal_app(
    db: AsyncSession,
    tenant_id: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> msal.PublicClientApplication | msal.ConfidentialClientApplication:
    resolved_client = client_id or await get_azure_client_id(db)
    secret = client_secret if client_secret is not None else await get_azure_client_secret(db)
    authority = (
        f"https://login.microsoftonline.com/{tenant_id}"
        if tenant_id
        else await get_azure_authority(db)
    )
    return create_msal_app(resolved_client, authority, secret)


def _username_from_token(access_token: str, id_token: str | None = None) -> str:
    if id_token:
        claims = _decode_jwt_claims(id_token)
        for key in ("preferred_username", "upn", "email", "unique_name"):
            if claims.get(key):
                return claims[key]
    claims = _decode_jwt_claims(access_token)
    for key in ("upn", "preferred_username", "unique_name", "email"):
        if claims.get(key):
            return claims[key]
    return claims.get("name", "utilisateur")


def _build_login_result(token_result: dict, client_id: str, client_secret: str | None) -> dict:
    access_token = token_result["access_token"]
    refresh_token = token_result.get("refresh_token")
    if not refresh_token:
        raise ValueError("Azure n'a pas fourni de jeton de rafraîchissement. Réessayez la connexion.")

    claims = _decode_jwt_claims(access_token)
    tenant_id = token_result.get("tenant_id") or claims.get("tid", "")
    if not tenant_id:
        raise ValueError("Impossible de déterminer le tenant Azure.")

    username = _username_from_token(access_token, token_result.get("id_token"))
    credential = RefreshTokenCredential(
        tenant_id, refresh_token, client_id=client_id, client_secret=client_secret
    )
    subs = list_subscriptions_from_credential(credential, tenant_id)
    if not subs:
        raise ValueError("Aucune souscription accessible avec ce compte.")

    tenant_name = _get_tenant_display_name(credential, tenant_id)
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "username": username,
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "subscriptions": subs,
    }


async def start_device_flow(db: AsyncSession) -> dict:
    if not await is_oauth_ready(db):
        raise ValueError(
            "Configurez Client ID, Tenant ID et Client Secret, puis utilisez "
            "« Connexion via navigateur »."
        )

    client_id = await get_azure_client_id(db)
    client_secret = await get_azure_client_secret(db)
    app = await _msal_app(db)
    flow = app.initiate_device_flow(scopes=MANAGEMENT_SCOPES)
    if not flow or "user_code" not in flow:
        message = friendly_oauth_error(
            (flow or {}).get("error_description") or "Impossible de démarrer la connexion Microsoft."
        )
        raise ValueError(message)

    flow_id = str(uuid.uuid4())
    flow["_flow_id"] = flow_id
    flow["_client_id"] = client_id
    flow["_has_client_secret"] = bool(client_secret)
    return {
        "flow_id": flow_id,
        "user_code": flow["user_code"],
        "verification_uri": flow.get("verification_uri") or "https://microsoft.com/devicelogin",
        "message": flow.get("message", ""),
        "expires_in": flow.get("expires_in", 900),
        "flow_data": flow,
    }


async def poll_device_flow(db: AsyncSession, flow_data: dict) -> dict:
    client_id = flow_data.get("_client_id") or await get_azure_client_id(db)
    client_secret = await get_azure_client_secret(db)
    app = await _msal_app(db, client_id=client_id, client_secret=client_secret)
    result = app.acquire_token_by_device_flow(flow_data)
    if not result:
        raise ValueError("En attente de la connexion Microsoft…")
    if "access_token" not in result:
        if result.get("error") == "authorization_pending":
            raise ValueError("En attente de la connexion Microsoft…")
        raise ValueError(
            friendly_oauth_error(
                result.get("error_description") or result.get("error") or "Authentification échouée."
            )
        )
    return _build_login_result(result, client_id, client_secret)


async def start_browser_flow(db: AsyncSession, redirect_uri: str) -> dict:
    if not await is_oauth_ready(db):
        raise ValueError(
            "Configurez Client ID, Tenant ID et Client Secret de votre application Azure AD "
            "(Certificates & secrets), puis réessayez."
        )

    client_id = await get_azure_client_id(db)
    client_secret = await get_azure_client_secret(db)
    app = await _msal_app(db)
    state = secrets.token_urlsafe(32)
    flow = app.initiate_auth_code_flow(
        scopes=MANAGEMENT_SCOPES,
        redirect_uri=redirect_uri,
        state=state,
    )
    flow_id = str(uuid.uuid4())
    flow["_flow_id"] = flow_id
    flow["_redirect_uri"] = redirect_uri
    flow["_client_id"] = client_id
    flow["_has_client_secret"] = bool(client_secret)
    return {
        "flow_id": flow_id,
        "state": state,
        "auth_url": flow["auth_uri"],
        "redirect_uri": redirect_uri,
        "flow_data": flow,
    }


async def complete_browser_flow(db: AsyncSession, flow_data: dict, query_params: dict) -> dict:
    client_id = flow_data.get("_client_id") or await get_azure_client_id(db)
    client_secret = await get_azure_client_secret(db)
    app = await _msal_app(db, client_id=client_id, client_secret=client_secret)
    result = app.acquire_token_by_auth_code_flow(flow_data, query_params)
    if "access_token" not in result:
        raise ValueError(
            friendly_oauth_error(
                result.get("error_description") or result.get("error") or "Authentification échouée."
            )
        )
    return _build_login_result(result, client_id, client_secret)


def public_base_url(request_base_url: str = "") -> str:
    if settings.azure_public_base_url:
        return settings.azure_public_base_url.rstrip("/")
    return request_base_url.rstrip("/") if request_base_url else ""


def default_redirect_uri(request_base_url: str = "") -> str:
    if settings.azure_redirect_uri:
        return settings.azure_redirect_uri.rstrip("/")
    base = public_base_url(request_base_url)
    if base:
        return f"{base}/api/azure/auth/callback"
    if request_base_url:
        return f"{request_base_url.rstrip('/')}/api/azure/auth/callback"
    return ""


async def auth_setup_info(db: AsyncSession, request_base_url: str) -> dict:
    redirect_uri = default_redirect_uri(request_base_url)
    base_url = public_base_url(request_base_url)
    client_id = await get_azure_client_id(db)
    tenant_id = await get_azure_tenant_id(db)
    custom = await is_custom_app_configured(db)
    secret_configured = bool(await get_azure_client_secret(db))
    oauth_ready = await is_oauth_ready(db)
    return {
        "client_id": client_id,
        "tenant_id": tenant_id,
        "public_base_url": base_url,
        "redirect_uri": redirect_uri,
        "scopes": MANAGEMENT_SCOPES,
        "custom_app_configured": custom,
        "client_secret_configured": secret_configured,
        "oauth_ready": oauth_ready,
        "using_default_client": client_id == AZURE_CLI_CLIENT_ID,
        "steps": [
            "Azure Portal → Microsoft Entra ID → App registrations → New registration",
            "Nom : Lab Console — Comptes : Uniquement ce répertoire",
            f"Redirect URI (Web) : {redirect_uri}",
            "Certificates & secrets → New client secret → copier la valeur immédiatement",
            "API permissions → Azure Service Management → user_impersonation (délégué) → Grant admin consent",
            "Saisir Client ID, Tenant ID et Client Secret ci-dessous, puis enregistrer",
        ],
        "instructions": (
            "Application Web Azure AD : le Client Secret est obligatoire pour échanger le code "
            "de connexion. Après configuration, cliquez sur « Connexion via navigateur »."
        ),
    }
