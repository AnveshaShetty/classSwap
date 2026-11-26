import secrets
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.routing import Mount
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.body_limits import RequestBodyLimitMiddleware
from app.core.csrf import CSRF_COOKIE_NAME
from app.core.observability import configure_logging, request_id_context
from app.core.rate_limit import rate_limit_response
from app.core.templating import templates
from app.routes.absence import router as absence_router
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.pages import router as pages_router
from app.routes.timetable import router as timetable_router
from app.routes.substitution import router as substitution_router

configure_logging(settings.log_level)


def api_docs_urls(environment: str) -> dict[str, Any]:
    if environment == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"}


app = FastAPI(
    title="ClassSwap",
    debug=settings.debug,
    **api_docs_urls(settings.environment),
)
app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_host_list or ["localhost", "127.0.0.1", "testserver"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-TOTP-Code"],
    expose_headers=["Retry-After"],
)
if settings.environment == "production":
    app.add_middleware(HTTPSRedirectMiddleware)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(pages_router)
app.include_router(timetable_router)
app.include_router(absence_router)
app.include_router(admin_router)
app.include_router(substitution_router)

for route in app.routes:
    if isinstance(route, Mount) or getattr(route, "name", None) in {
        "openapi",
        "swagger_ui_html",
        "swagger_ui_redirect",
        "redoc_html",
    }:
        setattr(route, "auth_policy", "public")
    elif isinstance(route, APIRoute) and route.path in {
        "/docs",
        "/redoc",
        "/openapi.json",
        "/docs/oauth2-redirect",
    }:
        route.openapi_extra = {"x-auth-policy": "public"}


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = secrets.token_hex(16)
    request.state.request_id = request_id
    context_token = request_id_context.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_context.reset(context_token)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def apply_rate_limits(request: Request, call_next):
    limited_response = rate_limit_response(request)
    if limited_response is not None:
        return limited_response
    return await call_next(request)


@app.middleware("http")
async def set_csrf_cookie(request: Request, call_next):
    response = await call_next(request)
    if request.method in {"GET", "HEAD"} and CSRF_COOKIE_NAME not in request.cookies:
        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=secrets.token_urlsafe(32),
            httponly=False,
            secure=settings.cookie_secure,
            samesite="strict",
            max_age=8 * 60 * 60,
            path="/",
        )
    return response


@app.middleware("http")
async def set_security_headers(request: Request, call_next):
    nonce = secrets.token_urlsafe(18)
    request.state.csp_nonce = nonce
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'nonce-%s' https://unpkg.com; "
        "style-src 'self' 'nonce-%s'; "
        "img-src 'self' data: https://images.unsplash.com; font-src 'self' data:; connect-src 'self'; "
        "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ) % (nonce, nonce)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    auth_cookie = settings.auth_cookie_name + "="
    if (
        settings.auth_cookie_name in request.cookies
        or any(cookie.startswith(auth_cookie) for cookie in response.headers.getlist("set-cookie"))
    ):
        response.headers["Cache-Control"] = "no-store"
    if "server" in response.headers:
        del response.headers["server"]
    return response


@app.get("/health", openapi_extra={"x-auth-policy": "public"})
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(StarletteHTTPException)
async def http_error_page(request: Request, exc: StarletteHTTPException) -> Response:
    if (
        exc.status_code == 403
        and isinstance(exc.detail, str)
        and exc.detail in {
            "Set up two-factor authentication before using admin features.",
            "A valid two-factor code is required.",
        }
        and request.url.path in {"/reports", "/reports/monthly"}
        and "text/html" in request.headers.get("accept", "").lower()
    ):
        next_url = request.url.path
        if request.url.query:
            next_url += "?" + request.url.query
        return RedirectResponse(
            url="/security/two-factor?" + urlencode({"next": next_url}),
            status_code=303,
        )
    if exc.status_code == 404:
        if request.url.path.startswith("/api") or "application/json" in request.headers.get("accept", ""):
            return JSONResponse(status_code=404, content={"detail": "The requested resource could not be found."})
        return templates.TemplateResponse(
            request=request,
            name="404.html",
            status_code=404,
            context={"request": request, "title": "Page not found"},
        )
    if exc.status_code in (403, 409, 422, 503):
        message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
        accept = request.headers.get("accept", "")
        is_api_request = (
            "application/json" in accept
            or "*/*" in accept
            or request.url.path.endswith("/import")
            or request.url.path.startswith("/stats/")
            or request.url.path.startswith("/reports/monthly")
            or request.url.path.startswith("/absences/")
            or request.url.path.startswith("/substitutions")
            or request.url.path.startswith("/rooms/")
            or request.url.path.startswith("/leaves")
            or request.url.path.startswith("/admin/")
        )
        if is_api_request:
            detail = exc.detail if isinstance(exc.detail, (str, dict, list)) else message
            return JSONResponse(status_code=exc.status_code, content={"detail": detail})
        return templates.TemplateResponse(
            request=request,
            name="500.html",
            status_code=exc.status_code,
            context={
                "request": request,
                "title": "Request could not be completed",
                "message": message,
            },
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail if isinstance(exc.detail, str) else "The request could not be completed."},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_page(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = [
        {
            "loc": error.get("loc", ()),
            "msg": error.get("msg", "Invalid value."),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Some submitted details need attention.", "errors": errors},
    )


@app.exception_handler(Exception)
async def unexpected_error_page(request: Request, exc: Exception) -> HTMLResponse | JSONResponse:
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(
            status_code=500,
            content={"detail": "Something interrupted this request. Try again in a moment."},
        )
    return templates.TemplateResponse(
        request=request,
        name="500.html",
        status_code=500,
        context={"request": request, "title": "Request interrupted"},
    )
