import os
from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.app.config import settings
from backend.app.database import engine, Base, get_db
from backend.app.models import (
    User, UserRole, Subject, FacultySubject, Room, Section,
    PeriodConfig, Timetable, Absence, Substitution, DateOverride, Notification
)
from backend.app.core.dependencies import get_current_user_optional
from backend.app.routes import (
    auth_routes,
    admin_routes,
    faculty_routes,
    timetable_routes,
    absence_routes,
    substitution_routes,
    room_routes,
    report_routes
)

# Create tables if not present
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Smart Substitutions. Zero Idle Hours. Intelligent college timetable and faculty substitution management platform.",
    version=settings.VERSION
)

# Ensure static directories exist
os.makedirs("backend/app/static/css", exist_ok=True)
os.makedirs("backend/app/static/js", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="backend/app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="backend/app/templates")

# Register routers
app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(faculty_routes.router)
app.include_router(timetable_routes.router)
app.include_router(absence_routes.router)
app.include_router(substitution_routes.router)
app.include_router(room_routes.router)
app.include_router(report_routes.router)

@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request, db: Session = Depends(get_db)):
    """Modern Academic SaaS Landing Page."""
    current_user = get_current_user_optional(request, db=db)
    
    # Real demo statistics from database
    total_faculty = db.query(User).filter(User.role == UserRole.FACULTY.value).count()
    total_sections = db.query(Section).count()
    total_rooms = db.query(Room).count()
    completed_subs = db.query(Substitution).filter(
        Substitution.status.in_(["Accepted", "Completed"])
    ).count()
    idle_hours_saved = round(completed_subs * (settings.PERIOD_DURATION_MINUTES / 60.0), 1)

    return templates.TemplateResponse(request, "landing.html", {
        "request": request,
        "user": current_user,
        "college_name": settings.COLLEGE_NAME,
        "total_faculty": total_faculty,
        "total_sections": total_sections,
        "total_rooms": total_rooms,
        "completed_subs": completed_subs,
        "idle_hours_saved": idle_hours_saved
    })

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, error: str = None, msg: str = None, db: Session = Depends(get_db)):
    """Professional Academic SaaS Login Page."""
    current_user = get_current_user_optional(request, db=db)
    if current_user:
        if current_user.role == UserRole.ADMIN.value:
            return RedirectResponse(url="/admin/dashboard", status_code=303)
        return RedirectResponse(url="/faculty/dashboard", status_code=303)

    return templates.TemplateResponse(request, "login.html", {
        "request": request,
        "error": error,
        "msg": msg,
        "college_name": settings.COLLEGE_NAME
    })

@app.get("/health")
def health_check():
    return {"status": "ok", "app": settings.PROJECT_NAME, "version": settings.VERSION}
