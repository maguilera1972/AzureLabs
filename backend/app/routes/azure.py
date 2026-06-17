from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
import json
from datetime import datetime, timedelta

from app.azure.auth import AzureCredentials, validate_connection, validate_user_login
from app.azure.oauth import (
    auth_setup_info,
    complete_browser_flow,
    default_redirect_uri,
    friendly_oauth_error,
    poll_device_flow,
    start_browser_flow,
    start_device_flow,
)
from app.config import settings
from app.crypto import decrypt_secret, encrypt_secret
from app.database import get_db
from app.models import AzureAuthSession, AzureConnection, ConsoleUser
from app.schemas import (
    AzureAuthConfigRequest,
    AzureAuthSessionResponse,
    AzureBrowserStartRequest,
    AzureBrowserStartResponse,
    AzureConnectRequest,
    AzureConnectionResponse,
    AzureDevicePollRequest,
    AzureDeviceStartResponse,
    AzureLoginRequest,
    AzureLoginResponse,
    SubscriptionInfo,
)
from app.services.auth_store import pack_auth_secret
from app.services.azure_config import get_azure_client_id, get_azure_client_secret, save_azure_auth_config
from app.services.console_auth import get_current_user
from app.services.credentials import get_active_connection_record

router = APIRouter(prefix="/api/azure", tags=["azure"])


def _request_base_url(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def _session_expiry() -> datetime:
    return datetime.utcnow() + timedelta(minutes=settings.auth_session_ttl_minutes)


async def _save_auth_session(
    db: AsyncSession,
    *,
    session_id: str,
    flow_type: str,
    flow_data: dict,
    status: str = "pending",
    tenant_id: str = "",
    tenant_name: str = "",
    username: str = "",
    refresh_token: str = "",
    oauth_client_id: str = "",
    subscriptions: list | None = None,
    error_message: str = "",
) -> AzureAuthSession:
    record = AzureAuthSession(
        id=session_id,
        flow_type=flow_type,
        flow_data_encrypted=encrypt_secret(json.dumps(flow_data)),
        status=status,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        username=username,
        refresh_token_encrypted=encrypt_secret(refresh_token) if refresh_token else "",
        oauth_client_id=oauth_client_id,
        subscriptions_json=json.dumps(subscriptions or []),
        error_message=error_message,
        expires_at=_session_expiry(),
    )
    db.add(record)
    await db.commit()
    return record


async def _get_auth_session(db: AsyncSession, session_id: str) -> AzureAuthSession:
    result = await db.execute(select(AzureAuthSession).where(AzureAuthSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "Session d'authentification introuvable ou expirée.")
    if session.expires_at < datetime.utcnow():
        raise HTTPException(410, "Session d'authentification expirée. Recommencez la connexion.")
    return session


def _session_to_login_response(session: AzureAuthSession) -> AzureAuthSessionResponse:
    subs = json.loads(session.subscriptions_json or "[]")
    return AzureAuthSessionResponse(
        session_id=session.id,
        status=session.status,
        tenant_id=session.tenant_id,
        tenant_name=session.tenant_name,
        username=session.username,
        subscriptions=[SubscriptionInfo(**s) for s in subs],
        error_message=session.error_message or None,
    )


def _apply_login_to_session(session: AzureAuthSession, login: dict) -> None:
    session.status = "complete"
    session.tenant_id = login["tenant_id"]
    session.tenant_name = login["tenant_name"]
    session.username = login["username"]
    session.refresh_token_encrypted = encrypt_secret(login["refresh_token"])
    session.oauth_client_id = login.get("client_id", "")
    session.subscriptions_json = json.dumps(login["subscriptions"])


@router.get("/auth/setup")
async def azure_auth_setup(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    return await auth_setup_info(db, _request_base_url(request))


@router.put("/auth/config")
async def azure_auth_config(
    req: AzureAuthConfigRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    if not req.client_id or len(req.client_id) < 10:
        raise HTTPException(400, "Client ID invalide.")
    try:
        await save_azure_auth_config(db, req.client_id, req.tenant_id or "", req.client_secret)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return await auth_setup_info(db, _request_base_url(request))


@router.post("/auth/device/start", response_model=AzureDeviceStartResponse)
async def azure_device_start(
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    try:
        flow = await start_device_flow(db)
    except Exception as e:
        raise HTTPException(400, str(e))

    await _save_auth_session(
        db,
        session_id=flow["flow_id"],
        flow_type="device",
        flow_data=flow["flow_data"],
    )
    return AzureDeviceStartResponse(
        session_id=flow["flow_id"],
        user_code=flow["user_code"],
        verification_uri=flow["verification_uri"],
        message=flow["message"],
        expires_in=flow["expires_in"],
    )


@router.post("/auth/device/poll", response_model=AzureAuthSessionResponse)
async def azure_device_poll(
    req: AzureDevicePollRequest,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    session = await _get_auth_session(db, req.session_id)
    if session.status == "complete":
        return _session_to_login_response(session)

    flow_data = json.loads(decrypt_secret(session.flow_data_encrypted))

    try:
        result = await poll_device_flow(db, flow_data)
    except ValueError as e:
        if "En attente" in str(e):
            return AzureAuthSessionResponse(
                session_id=session.id,
                status="pending",
                tenant_id="",
                tenant_name="",
                username="",
                subscriptions=[],
            )
        session.status = "error"
        session.error_message = str(e)
        await db.commit()
        raise HTTPException(400, str(e))
    except Exception as e:
        session.status = "error"
        session.error_message = friendly_oauth_error(str(e))
        await db.commit()
        raise HTTPException(400, friendly_oauth_error(str(e)))

    _apply_login_to_session(session, result)
    await db.commit()
    return _session_to_login_response(session)


@router.post("/auth/browser/start", response_model=AzureBrowserStartResponse)
async def azure_browser_start(
    req: AzureBrowserStartRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    redirect_uri = req.redirect_uri or default_redirect_uri(_request_base_url(request))
    try:
        flow = await start_browser_flow(db, redirect_uri)
    except Exception as e:
        raise HTTPException(400, str(e))

    await _save_auth_session(
        db,
        session_id=flow["flow_id"],
        flow_type="browser",
        flow_data=flow["flow_data"],
    )
    return AzureBrowserStartResponse(
        session_id=flow["flow_id"],
        auth_url=flow["auth_url"],
        redirect_uri=redirect_uri,
    )


@router.get("/auth/callback")
async def azure_auth_callback(request: Request, db: AsyncSession = Depends(get_db)):
    params = dict(request.query_params)
    state = params.get("state", "")
    if params.get("error_description"):
        msg = friendly_oauth_error(params["error_description"])
        return RedirectResponse(f"/?view=azure&auth_error={msg[:200]}")
    if not state:
        return RedirectResponse("/?view=azure&auth_error=missing_state")

    result = await db.execute(
        select(AzureAuthSession).where(
            AzureAuthSession.flow_type == "browser",
            AzureAuthSession.status == "pending",
        )
    )
    sessions = result.scalars().all()

    target = None
    flow_data = None
    for session in sessions:
        data = json.loads(decrypt_secret(session.flow_data_encrypted))
        if data.get("state") == state:
            target = session
            flow_data = data
            break

    if not target or not flow_data:
        return RedirectResponse("/?view=azure&auth_error=invalid_session")

    try:
        login = await complete_browser_flow(db, flow_data, params)
        _apply_login_to_session(target, login)
        await db.commit()
        return RedirectResponse(f"/?view=azure&session_id={target.id}")
    except Exception as e:
        target.status = "error"
        target.error_message = friendly_oauth_error(str(e))
        await db.commit()
        return RedirectResponse(f"/?view=azure&auth_error={friendly_oauth_error(str(e))[:200]}")


@router.get("/auth/session/{session_id}", response_model=AzureAuthSessionResponse)
async def azure_auth_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    session = await _get_auth_session(db, session_id)
    return _session_to_login_response(session)


@router.post("/login", response_model=AzureLoginResponse)
async def login_azure(
    req: AzureLoginRequest,
    _: ConsoleUser = Depends(get_current_user),
):
    try:
        result = validate_user_login(req.username, req.password)
    except Exception as e:
        raise HTTPException(400, str(e))
    return AzureLoginResponse(
        tenant_id=result["tenant_id"],
        tenant_name=result["tenant_name"],
        username=result["username"],
        subscriptions=[SubscriptionInfo(**s) for s in result["subscriptions"]],
        auth_type="password",
    )


@router.post("/connect", response_model=AzureConnectionResponse)
async def connect_azure(
    req: AzureConnectRequest,
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    tenant_id = req.tenant_id
    tenant_name = req.tenant_name
    username = req.username
    auth_type = "oauth"
    refresh_token = None
    password = None
    oauth_client_id = None
    oauth_client_secret = None

    if req.session_id:
        session = await _get_auth_session(db, req.session_id)
        if session.status != "complete":
            raise HTTPException(400, "La connexion Microsoft n'est pas terminée.")
        tenant_id = session.tenant_id
        tenant_name = session.tenant_name
        username = session.username
        refresh_token = decrypt_secret(session.refresh_token_encrypted)
        oauth_client_id = session.oauth_client_id or await get_azure_client_id(db)
        oauth_client_secret = await get_azure_client_secret(db)
        auth_type = "oauth"
    else:
        if not tenant_id or not username:
            raise HTTPException(400, "Session ou identifiants requis.")
        auth_type = "password" if req.password else "oauth"
        password = req.password
        refresh_token = req.refresh_token
        oauth_client_id = req.oauth_client_id
        oauth_client_secret = await get_azure_client_secret(db)

    creds = AzureCredentials(
        tenant_id=tenant_id,
        username=username,
        subscription_id=req.subscription_id,
        auth_type=auth_type,
        password=password,
        refresh_token=refresh_token,
        client_id=oauth_client_id,
        client_secret=oauth_client_secret,
    )
    try:
        sub = validate_connection(creds)
    except Exception as e:
        raise HTTPException(400, f"Connexion Azure échouée: {e}")

    await db.execute(update(AzureConnection).values(is_active=False))
    record = AzureConnection(
        tenant_id=tenant_id,
        client_id=username,
        client_secret_encrypted=pack_auth_secret(
            auth_type,
            refresh_token=refresh_token,
            password=password,
            client_id=oauth_client_id,
            client_secret=oauth_client_secret,
        ),
        auth_type=auth_type,
        subscription_id=req.subscription_id,
        subscription_name=sub["name"],
        is_active=True,
    )
    db.add(record)
    if req.session_id:
        await db.execute(delete(AzureAuthSession).where(AzureAuthSession.id == req.session_id))
    await db.commit()

    return AzureConnectionResponse(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        username=username,
        subscription_id=req.subscription_id,
        subscription_name=sub["name"],
        connected=True,
        auth_type=auth_type,
    )


@router.get("/status", response_model=AzureConnectionResponse)
async def azure_status(
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    conn = await get_active_connection_record(db)
    if not conn:
        raise HTTPException(404, "Aucune connexion Azure configurée")
    return AzureConnectionResponse(
        tenant_id=conn.tenant_id,
        tenant_name=conn.tenant_id,
        username=conn.client_id,
        subscription_id=conn.subscription_id,
        subscription_name=conn.subscription_name,
        connected=True,
        auth_type=conn.auth_type or "oauth",
    )


@router.delete("/disconnect")
async def disconnect_azure(
    db: AsyncSession = Depends(get_db),
    _: ConsoleUser = Depends(get_current_user),
):
    await db.execute(update(AzureConnection).values(is_active=False))
    await db.commit()
    return {"status": "disconnected"}
