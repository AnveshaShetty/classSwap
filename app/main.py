from fastapi import FastAPI

from app.routes.absence import router as absence_router
from app.routes.admin import router as admin_router
from app.routes.auth import router as auth_router
from app.routes.dashboard import router as dashboard_router
from app.routes.pages import router as pages_router
from app.routes.timetable import router as timetable_router
from app.routes.substitution import router as substitution_router

app = FastAPI(title="ClassSwap")
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
