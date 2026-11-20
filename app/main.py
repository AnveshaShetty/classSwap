from fastapi import FastAPI

from app.routes.absence import router as absence_router
from app.routes.auth import router as auth_router
from app.routes.timetable import router as timetable_router
from app.routes.substitution import router as substitution_router

app = FastAPI(title="ClassSwap")
app.include_router(auth_router)
app.include_router(timetable_router)
app.include_router(absence_router)
app.include_router(substitution_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
