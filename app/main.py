from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.routes.absence import router as absence_router
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.pages import router as pages_router
from app.routes.timetable import router as timetable_router
from app.routes.substitution import router as substitution_router

app = FastAPI(title="ClassSwap")
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(pages_router)
app.include_router(timetable_router)
app.include_router(absence_router)
app.include_router(admin_router)
app.include_router(substitution_router)


@app.get("/health")
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
    return JSONResponse(
        status_code=422,
        content={"detail": "Some submitted details need attention.", "errors": exc.errors()},
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
