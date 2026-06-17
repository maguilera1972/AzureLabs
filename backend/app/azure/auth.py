import base64
import json
import logging
import re
from dataclasses import dataclass

import httpx
import msal
from azure.core.credentials import TokenCredential
from azure.identity import UsernamePasswordCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.subscription import SubscriptionClient

from app.azure.constants import AZURE_AUTHORITY_ORGS, AZURE_CLI_CLIENT_ID, MANAGEMENT_SCOPES
from app.azure.msal_credential import RefreshTokenCredential
from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AzureCredentials:
    tenant_id: str
    username: str
    subscription_id: str
    auth_type: str = "oauth"
    password: str | None = None
    refresh_token: str | None = None
    client_id: str | None = None
    client_secret: str | None = None


def get_credential(creds: AzureCredentials) -> TokenCredential:
    if creds.auth_type == "oauth" and creds.refresh_token:
        return RefreshTokenCredential(
            creds.tenant_id,
            creds.refresh_token,
            client_id=creds.client_id or settings.azure_client_id,
            client_secret=creds.client_secret or settings.azure_client_secret or None,
        )
    if creds.password:
        return UsernamePasswordCredential(
            client_id=settings.azure_client_id,
            username=creds.username,
            password=creds.password,
            tenant_id=creds.tenant_id,
        )
    raise ValueError("Aucune information d'authentification Azure valide.")


def get_resource_client(creds: AzureCredentials) -> ResourceManagementClient:
    return ResourceManagementClient(get_credential(creds), creds.subscription_id)


def list_subscriptions_from_credential(credential: TokenCredential, tenant_id: str) -> list[dict]:
    client = SubscriptionClient(credential)
    return [
        {"id": s.subscription_id, "name": s.display_name, "state": s.state}
        for s in client.subscriptions.list()
    ]


def list_subscriptions(creds: AzureCredentials) -> list[dict]:
    return list_subscriptions_from_credential(get_credential(creds), creds.tenant_id)


def _decode_jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return {}


def _get_tenant_display_name(credential: TokenCredential, tenant_id: str) -> str:
    try:
        token = credential.get_token("https://graph.microsoft.com/.default")
        resp = httpx.get(
            "https://graph.microsoft.com/v1.0/organization",
            headers={"Authorization": f"Bearer {token.token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            orgs = resp.json().get("value", [])
            for org in orgs:
                if org.get("id") == tenant_id or not orgs:
                    return org.get("displayName", tenant_id)
            if orgs:
                return orgs[0].get("displayName", tenant_id)
    except Exception as e:
        logger.warning("Could not fetch tenant name: %s", e)
    return tenant_id


def _friendly_auth_error(exc_or_result: Exception | dict) -> str:
    if isinstance(exc_or_result, dict):
        code = str(exc_or_result.get("error", ""))
        desc = str(exc_or_result.get("error_description", ""))
        msg = f"{code} {desc}".lower()
    else:
        msg = str(exc_or_result).lower()

    if "aadsts50126" in msg or "invalid_grant" in msg or "wrong password" in msg or "invalid username" in msg:
        return "Identifiant ou mot de passe incorrect."
    if "aadsts50076" in msg or "aadsts50079" in msg or "mfa" in msg or "multi-factor" in msg:
        return (
            "Authentification multi-facteurs (MFA) requise. "
            "Utilisez la connexion Microsoft (bouton ci-dessus) qui prend en charge le MFA."
        )
    if "aadsts7000218" in msg or "aadsts65001" in msg or "consent" in msg:
        return "Consentement Azure requis pour ce compte. Contactez votre administrateur Azure AD."
    if "aadsts50057" in msg or "disabled" in msg:
        return "Ce compte utilisateur est désactivé."
    if "wstrust" in msg or "ws-trust" in msg or "msa account" in msg:
        return (
            "Ce type de compte n'est pas supporté. "
            "Utilisez un compte administrateur professionnel Azure AD (ex. admin@votredomaine.onmicrosoft.com)."
        )
    if isinstance(exc_or_result, dict):
        return desc or code or "Authentification échouée."
    return f"Authentification échouée : {exc_or_result}"


def _acquire_user_token(username: str, password: str, tenant_id: str | None = None) -> dict:
    authority = (
        f"https://login.microsoftonline.com/{tenant_id}"
        if tenant_id
        else AZURE_AUTHORITY_ORGS
    )
    app = msal.PublicClientApplication(settings.azure_client_id, authority=authority)
    result = app.acquire_token_by_username_password(
        username,
        password,
        scopes=["https://management.azure.com/user_impersonation"],
    )
    if "access_token" not in result:
        raise ValueError(_friendly_auth_error(result))
    return result


def validate_user_login(username: str, password: str) -> dict:
    """Legacy password login (no MFA). Prefer OAuth device/browser flows."""
    username = username.strip()
    if not username or not password:
        raise ValueError("Identifiant et mot de passe requis.")

    try:
        token_result = _acquire_user_token(username, password)
    except Exception as e:
        raise ValueError(_friendly_auth_error(e)) from e

    claims = _decode_jwt_claims(token_result["access_token"])
    tenant_id = token_result.get("tenant_id") or claims.get("tid", "")
    if not tenant_id:
        raise ValueError("Impossible de déterminer le tenant Azure.")

    creds = AzureCredentials(
        tenant_id=tenant_id,
        username=username,
        password=password,
        auth_type="password",
        subscription_id="00000000-0000-0000-0000-000000000000",
    )

    try:
        subs = list_subscriptions(creds)
    except Exception as e:
        raise ValueError(f"Connexion réussie mais accès aux souscriptions refusé : {e}") from e

    if not subs:
        raise ValueError("Aucune souscription accessible avec ce compte.")

    tenant_name = _get_tenant_display_name(get_credential(creds), tenant_id)

    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "username": username,
        "subscriptions": subs,
        "auth_type": "password",
    }


def validate_connection(creds: AzureCredentials) -> dict:
    subs = list_subscriptions(creds)
    current = next((s for s in subs if s["id"] == creds.subscription_id), None)
    if not current:
        raise ValueError("Souscription introuvable pour ce compte")
    client = get_resource_client(creds)
    client.resource_groups.list()
    return current


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]", "-", name.lower().strip())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:40] or "atelier"


def resource_group_name(workshop_name: str) -> str:
    return f"rg-lab-{slugify(workshop_name)}"[:90]


VM_SIZES = {
    "Standard_D2s_v3": {"vcpu": 2, "ram_gb": 8},
    "Standard_D4s_v3": {"vcpu": 4, "ram_gb": 16},
    "Standard_D8s_v3": {"vcpu": 8, "ram_gb": 32},
    "Standard_D16s_v3": {"vcpu": 16, "ram_gb": 64},
}

OS_IMAGES = {
    "windows11": {
        "publisher": "MicrosoftWindowsDesktop",
        "offer": "windows-11",
        "sku": "win11-23h2-ent",
        "version": "latest",
        "os_type": "Windows",
        "remote_protocol": "RDP",
        "remote_port": 3389,
    },
    "windowsserver2025": {
        "publisher": "MicrosoftWindowsServer",
        "offer": "WindowsServer",
        "sku": "2025-datacenter-azure-edition",
        "version": "latest",
        "os_type": "Windows",
        "remote_protocol": "RDP",
        "remote_port": 3389,
    },
    "ubuntu": {
        "publisher": "Canonical",
        "offer": "0001-com-ubuntu-server-jammy",
        "sku": "22_04-lts-gen2",
        "version": "latest",
        "os_type": "Linux",
        "remote_protocol": "SSH",
        "remote_port": 22,
    },
}

NESTED_VIRT_SIZES = {
    "Standard_D2s_v3", "Standard_D4s_v3", "Standard_D8s_v3",
    "Standard_D16s_v3", "Standard_D2s_v5", "Standard_D4s_v5",
    "Standard_D8s_v5", "Standard_E2s_v3", "Standard_E4s_v3",
}

DEFAULT_VM_SIZE = settings.default_vm_size
