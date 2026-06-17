import logging
import time

import msal
from azure.core.credentials import AccessToken, TokenCredential

from app.azure.constants import AZURE_CLI_CLIENT_ID, MANAGEMENT_SCOPES
from app.azure.msal_factory import create_msal_app

logger = logging.getLogger(__name__)


class RefreshTokenCredential(TokenCredential):
    """Delegated Azure access via OAuth refresh token (supports MFA login)."""

    def __init__(
        self,
        tenant_id: str,
        refresh_token: str,
        client_id: str = AZURE_CLI_CLIENT_ID,
        client_secret: str | None = None,
    ):
        self._tenant_id = tenant_id
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._authority = f"https://login.microsoftonline.com/{tenant_id}"

    @property
    def refresh_token(self) -> str:
        return self._refresh_token

    def get_token(self, *scopes: str, **kwargs) -> AccessToken:
        scope_list = list(scopes) if scopes else MANAGEMENT_SCOPES
        app = create_msal_app(self._client_id, self._authority, self._client_secret)
        result = app.acquire_token_by_refresh_token(self._refresh_token, scopes=scope_list)
        if "access_token" not in result:
            error = result.get("error_description") or result.get("error") or "Token refresh failed"
            raise RuntimeError(error)
        if "refresh_token" in result:
            self._refresh_token = result["refresh_token"]
        expires_on = int(time.time()) + int(result.get("expires_in", 3600))
        return AccessToken(result["access_token"], expires_on)
