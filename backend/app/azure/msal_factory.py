import msal


def create_msal_app(
    client_id: str,
    authority: str,
    client_secret: str | None = None,
) -> msal.PublicClientApplication | msal.ConfidentialClientApplication:
    if client_secret:
        return msal.ConfidentialClientApplication(
            client_id,
            authority=authority,
            client_credential=client_secret,
        )
    return msal.PublicClientApplication(client_id, authority=authority)
