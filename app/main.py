import secrets
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.core.body_limits import RequestBodyLimitMiddleware
from app.core.csrf import CSRF_COOKIE_NAME
from app.core.templating import templates
from app.routes.absence import router as absence_router
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.pages import router as pages_router
from app.routes.timetable import router as timetable_router
from app.routes.substitution import router as substitution_router

app = FastAPI(title="ClassSwap")
app.add_middleware(RequestBodyLimitMiddleware)
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


@app.get("/health", openapi_extra={"x-auth-policy": "public"})
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(StarletteHTTPException)
async def http_error_page(request: Request, exc: StarletteHTTPException) -> HTMLResponse | JSONResponse:
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
