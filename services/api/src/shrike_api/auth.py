from typing import cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from shrike.application.auth import DashboardAuth
from shrike.config import Settings
from shrike.domain.auth import AuthenticationError

from .errors import ApiError

router = APIRouter()


def session_cookie(settings: Settings) -> str:
    return "__Host-shrike_session" if settings.secure_dashboard_cookies else "shrike_session"


def oauth_cookie(settings: Settings) -> str:
    return (
        "__Host-shrike_oauth_state" if settings.secure_dashboard_cookies else "shrike_oauth_state"
    )


def service(request: Request) -> DashboardAuth:
    auth = cast(DashboardAuth | None, request.app.state.dashboard_auth)
    if auth is None:
        raise ApiError(503, "authentication_unavailable", "User authentication is not configured")
    return auth


def cookie(response: Response, settings: Settings, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        path="/",
        httponly=True,
        secure=settings.secure_dashboard_cookies,
        samesite="lax",
    )


@router.get("/auth/github/start")
def start(request: Request) -> Response:
    settings = cast(Settings, request.app.state.settings)
    url, state = service(request).start()
    response = RedirectResponse(url, status_code=302)
    cookie(response, settings, oauth_cookie(settings), state, 300)
    return response


@router.get("/auth/github/callback")
def callback(request: Request, code: str = "", state: str = "") -> Response:
    settings = cast(Settings, request.app.state.settings)
    try:
        token = service(request).complete(
            code,
            state,
            request.cookies.get(oauth_cookie(settings)),
            request.cookies.get(session_cookie(settings)),
        )
    except AuthenticationError:
        response: Response = RedirectResponse(
            settings.dashboard_origin + "/login?error=authorization", status_code=303
        )
    else:
        response = RedirectResponse(settings.dashboard_origin + "/", status_code=303)
        cookie(response, settings, session_cookie(settings), token, 3600)
    cookie(response, settings, oauth_cookie(settings), "", 0)
    return response


@router.get("/auth/session")
def current(request: Request) -> Response:
    settings = cast(Settings, request.app.state.settings)
    try:
        user = service(request).authenticate(request.cookies.get(session_cookie(settings)))
    except AuthenticationError as error:
        status = 503 if error.code == "authorization_unavailable" else 401
        raise ApiError(status, error.code, "Authentication could not be verified") from None
    return JSONResponse({"login": user.identity.login, "mode": "live"})


@router.post("/auth/logout")
def logout(request: Request) -> Response:
    settings = cast(Settings, request.app.state.settings)
    if request.headers.get("origin") != settings.dashboard_origin:
        raise ApiError(403, "origin_denied", "Same-origin request is required")
    service(request).logout(request.cookies.get(session_cookie(settings)))
    response = Response(status_code=204)
    cookie(response, settings, session_cookie(settings), "", 0)
    return response
