from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional

from backend.app.database import get_db
from backend.app.core.dependencies import get_current_user_optional, require_faculty
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, Room, Section
from backend.app.models.timetable import Timetable, PeriodConfig
from backend.app.models.substitution import Absence, Substitution, SubstitutionStatus, DateOverride
from backend.app.models.notification import Notification
from backend.app.services.timetable_service import get_date_specific_timetable
from backend.app.config import settings

router = APIRouter(prefix="/faculty", tags=["Faculty Web UI"])
templates = Jinja2Templates(directory="backend/app/templates")

def get_faculty_context(request: Request, user: User, db: Session, active_page: str):
    unread_notifs = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    first_of_month = date(date.today().year, date.today().month, 1)
    
    monthly_subs_count = db.query(Substitution).join(Absence).filter(
        Substitution.substitute_id == user.id,
        Absence.date >= first_of_month,
        Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
    ).count()

    pending_requests_count = db.query(Substitution).filter(
        Substitution.substitute_id == user.id,
        Substitution.status == SubstitutionStatus.PENDING.value
    ).count()

    return {
        "request": request,
        "user": user,
        "college_name": settings.COLLEGE_NAME,
        "active_page": active_page,
        "unread_notifications_count": unread_notifs,
        "monthly_subs_count": monthly_subs_count,
        "pending_requests_count": pending_requests_count,
        "current_date": date.today().strftime("%A, %B %d, %Y"),
        "today_iso": date.today().strftime("%Y-%m-%d")
    }

@router.get("/dashboard", response_class=HTMLResponse)
def faculty_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.FACULTY.value:
        return RedirectResponse(url="/login?error=Faculty+login+required", status_code=303)

    today = date.today()
    day_name = today.strftime("%A")

    todays_classes = get_date_specific_timetable(db=db, target_date=today, faculty_id=user.id)

    weekly_entries = db.query(Timetable).filter(Timetable.faculty_id == user.id).order_by(Timetable.period_no).all()
    periods = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    
    weekly_grid = {day: {p.period_no: None for p in periods} for day in days}
    for e in weekly_entries:
        if e.day_of_week in weekly_grid and e.period_no in weekly_grid[e.day_of_week]:
            weekly_grid[e.day_of_week][e.period_no] = e

    pending_requests = db.query(Substitution).filter(
        Substitution.substitute_id == user.id,
        Substitution.status == SubstitutionStatus.PENDING.value
    ).order_by(Substitution.created_at.desc()).all()

    past_substitutions = db.query(Substitution).filter(
        Substitution.substitute_id == user.id,
        Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
    ).order_by(Substitution.created_at.desc()).limit(8).all()

    absence_history = db.query(Absence).filter(
        Absence.faculty_id == user.id
    ).order_by(Absence.date.desc(), Absence.period_no).limit(8).all()

    recent_notifs = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.created_at.desc()).limit(5).all()

    ctx = get_faculty_context(request, user, db, "dashboard")
    ctx.update({
        "todays_classes": todays_classes,
        "weekly_grid": weekly_grid,
        "periods": periods,
        "days": days,
        "pending_requests": pending_requests,
        "past_substitutions": past_substitutions,
        "absence_history": absence_history,
        "recent_notifs": recent_notifs
    })
    return templates.TemplateResponse(request, "faculty/dashboard.html", ctx)

@router.get("/mark-absence", response_class=HTMLResponse)
def faculty_mark_absence_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.FACULTY.value:
        return RedirectResponse(url="/login?error=Faculty+login+required", status_code=303)

    periods = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()
    absences = db.query(Absence).filter(Absence.faculty_id == user.id).order_by(Absence.date.desc()).limit(15).all()

    ctx = get_faculty_context(request, user, db, "mark_absence")
    ctx.update({
        "periods": periods,
        "absences": absences
    })
    return templates.TemplateResponse(request, "faculty/mark_absence.html", ctx)

@router.get("/requests", response_class=HTMLResponse)
def faculty_requests_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.FACULTY.value:
        return RedirectResponse(url="/login?error=Faculty+login+required", status_code=303)

    pending_requests = db.query(Substitution).filter(
        Substitution.substitute_id == user.id,
        Substitution.status == SubstitutionStatus.PENDING.value
    ).order_by(Substitution.created_at.desc()).all()

    history_requests = db.query(Substitution).filter(
        Substitution.substitute_id == user.id,
        Substitution.status != SubstitutionStatus.PENDING.value
    ).order_by(Substitution.created_at.desc()).all()

    ctx = get_faculty_context(request, user, db, "requests")
    ctx.update({
        "pending_requests": pending_requests,
        "history_requests": history_requests
    })
    return templates.TemplateResponse(request, "faculty/requests.html", ctx)

@router.get("/history", response_class=HTMLResponse)
def faculty_history_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.FACULTY.value:
        return RedirectResponse(url="/login?error=Faculty+login+required", status_code=303)

    subs = db.query(Substitution).filter(
        Substitution.substitute_id == user.id
    ).order_by(Substitution.created_at.desc()).all()

    ctx = get_faculty_context(request, user, db, "history")
    ctx.update({"substitutions": subs})
    return templates.TemplateResponse(request, "faculty/history.html", ctx)
