from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime
from typing import Optional

from backend.app.database import get_db
from backend.app.core.dependencies import get_current_user, require_admin, get_current_user_optional
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, Room, Section, FacultySubject
from backend.app.models.timetable import Timetable, PeriodConfig
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus, DateOverride
from backend.app.models.notification import Notification
from backend.app.services.report_service import calculate_monthly_analytics
from backend.app.config import settings

router = APIRouter(prefix="/admin", tags=["Admin Web UI"])
templates = Jinja2Templates(directory="backend/app/templates")

def get_admin_context(request: Request, user: User, db: Session, active_page: str):
    unread_notifs = db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read == False).count()
    return {
        "request": request,
        "user": user,
        "college_name": settings.COLLEGE_NAME,
        "active_page": active_page,
        "unread_notifications_count": unread_notifs,
        "current_date": date.today().strftime("%A, %B %d, %Y"),
        "today_iso": date.today().strftime("%Y-%m-%d")
    }

@router.get("/dashboard", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    today = date.today()
    day_name = today.strftime("%A")

    # 1. Summary Cards metrics
    total_faculty = db.query(User).filter(User.role == UserRole.FACULTY.value, User.is_active == True).count()
    total_sections = db.query(Section).count()
    total_rooms = db.query(Room).count()
    todays_classes_count = db.query(Timetable).filter(Timetable.day_of_week == day_name).count()
    faculty_absences_today = db.query(Absence).filter(Absence.date == today).count()
    pending_sub_requests = db.query(Substitution).filter(Substitution.status == SubstitutionStatus.PENDING.value).count()
    completed_subs = db.query(Substitution).filter(
        Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
    ).count()
    idle_hours_saved = round(completed_subs * (settings.PERIOD_DURATION_MINUTES / 60.0), 1)

    # 2. Today's Timetable with date-specific overrides
    today_timetable = db.query(Timetable).filter(Timetable.day_of_week == day_name).order_by(Timetable.period_no).all()

    # 3. Recent faculty absence notifications
    recent_absences = db.query(Absence).order_by(Absence.date.desc(), Absence.id.desc()).limit(6).all()

    # 4. Pending substitute approvals/requests
    pending_subs = db.query(Substitution).filter(
        Substitution.status == SubstitutionStatus.PENDING.value
    ).order_by(Substitution.created_at.desc()).limit(5).all()

    # 5. Recently completed substitutions
    recent_completed_subs = db.query(Substitution).filter(
        Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
    ).order_by(Substitution.updated_at.desc()).limit(5).all()

    # 6. Faculty Workload preview
    faculty_workloads = db.query(
        User.id,
        User.name,
        User.department,
        func.count(Substitution.id).label("sub_count")
    ).outerjoin(Substitution, Substitution.substitute_id == User.id)\
     .filter(User.role == UserRole.FACULTY.value)\
     .group_by(User.id).order_by(func.count(Substitution.id).desc()).limit(8).all()

    ctx = get_admin_context(request, user, db, "dashboard")
    ctx.update({
        "total_faculty": total_faculty,
        "total_sections": total_sections,
        "total_rooms": total_rooms,
        "todays_classes_count": todays_classes_count,
        "faculty_absences_today": faculty_absences_today,
        "pending_sub_requests": pending_sub_requests,
        "completed_subs": completed_subs,
        "idle_hours_saved": idle_hours_saved,
        "today_timetable": today_timetable,
        "recent_absences": recent_absences,
        "pending_subs": pending_subs,
        "recent_completed_subs": recent_completed_subs,
        "faculty_workloads": faculty_workloads,
        "day_name": day_name
    })
    return templates.TemplateResponse(request, "admin/dashboard.html", ctx)

@router.get("/timetable", response_class=HTMLResponse)
def admin_timetable_view(request: Request, section_id: Optional[int] = None, faculty_id: Optional[int] = None, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    sections = db.query(Section).order_by(Section.name).all()
    faculties = db.query(User).filter(User.role == UserRole.FACULTY.value).order_by(User.name).all()
    rooms = db.query(Room).order_by(Room.name).all()
    subjects = db.query(Subject).order_by(Subject.name).all()
    periods = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()

    active_section_id = section_id or (sections[0].id if sections else None)
    
    timetable_grid = {day: {p.period_no: None for p in periods} for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]}
    
    if active_section_id:
        entries = db.query(Timetable).filter(Timetable.section_id == active_section_id).all()
        for e in entries:
            if e.day_of_week in timetable_grid and e.period_no in timetable_grid[e.day_of_week]:
                timetable_grid[e.day_of_week][e.period_no] = e

    ctx = get_admin_context(request, user, db, "timetable")
    ctx.update({
        "sections": sections,
        "faculties": faculties,
        "rooms": rooms,
        "subjects": subjects,
        "periods": periods,
        "active_section_id": active_section_id,
        "timetable_grid": timetable_grid,
        "days": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    })
    return templates.TemplateResponse(request, "admin/timetable.html", ctx)

@router.get("/faculty", response_class=HTMLResponse)
def admin_faculty_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    faculty_list = db.query(User).filter(User.role == UserRole.FACULTY.value).order_by(User.name).all()
    subjects = db.query(Subject).order_by(Subject.name).all()
    
    fac_stats = []
    for f in faculty_list:
        sub_count = db.query(Substitution).filter(
            Substitution.substitute_id == f.id,
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).count()
        abs_count = db.query(Absence).filter(Absence.faculty_id == f.id).count()
        fac_stats.append({
            "faculty": f,
            "sub_count": sub_count,
            "abs_count": abs_count,
            "subjects": [fs.subject for fs in f.faculty_subjects]
        })

    ctx = get_admin_context(request, user, db, "faculty")
    ctx.update({
        "fac_stats": fac_stats,
        "subjects": subjects,
        "departments": list({f.department for f in faculty_list})
    })
    return templates.TemplateResponse(request, "admin/faculty.html", ctx)

@router.get("/subjects", response_class=HTMLResponse)
def admin_subjects_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    subjects = db.query(Subject).order_by(Subject.department, Subject.code).all()
    ctx = get_admin_context(request, user, db, "subjects")
    ctx.update({"subjects": subjects})
    return templates.TemplateResponse(request, "admin/subjects.html", ctx)

@router.get("/sections", response_class=HTMLResponse)
def admin_sections_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    sections = db.query(Section).order_by(Section.department, Section.name).all()
    ctx = get_admin_context(request, user, db, "sections")
    ctx.update({"sections": sections})
    return templates.TemplateResponse(request, "admin/sections.html", ctx)

@router.get("/rooms", response_class=HTMLResponse)
def admin_rooms_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    rooms = db.query(Room).order_by(Room.building, Room.name).all()
    ctx = get_admin_context(request, user, db, "rooms")
    ctx.update({"rooms": rooms})
    return templates.TemplateResponse(request, "admin/rooms.html", ctx)

@router.get("/absences", response_class=HTMLResponse)
def admin_absences_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    absences = db.query(Absence).order_by(Absence.date.desc(), Absence.period_no).all()
    faculties = db.query(User).filter(User.role == UserRole.FACULTY.value).order_by(User.name).all()
    periods = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()

    absence_details = []
    for a in absences:
        day_of_week = a.date.strftime("%A")
        tt = db.query(Timetable).filter(
            Timetable.faculty_id == a.faculty_id,
            Timetable.day_of_week == day_of_week,
            Timetable.period_no == a.period_no
        ).first()

        sub = db.query(Substitution).filter(Substitution.absence_id == a.id).order_by(Substitution.id.desc()).first()

        absence_details.append({
            "absence": a,
            "timetable": tt,
            "active_substitution": sub
        })

    ctx = get_admin_context(request, user, db, "absences")
    ctx.update({
        "absence_details": absence_details,
        "faculties": faculties,
        "periods": periods
    })
    return templates.TemplateResponse(request, "admin/absences.html", ctx)

@router.get("/substitutions", response_class=HTMLResponse)
def admin_substitutions_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    subs = db.query(Substitution).order_by(Substitution.created_at.desc()).all()
    ctx = get_admin_context(request, user, db, "substitutions")
    ctx.update({"substitutions": subs})
    return templates.TemplateResponse(request, "admin/substitutions.html", ctx)

@router.get("/free-rooms", response_class=HTMLResponse)
def admin_free_rooms_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    periods = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()
    sections = db.query(Section).order_by(Section.name).all()
    ctx = get_admin_context(request, user, db, "free_rooms")
    ctx.update({
        "periods": periods,
        "sections": sections
    })
    return templates.TemplateResponse(request, "admin/free_rooms.html", ctx)

@router.get("/reports", response_class=HTMLResponse)
def admin_reports_view(request: Request, year: Optional[int] = None, month: Optional[int] = None, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    target_year = year or datetime.now().year
    target_month = month or datetime.now().month

    report_data = calculate_monthly_analytics(db, target_year, target_month)
    ctx = get_admin_context(request, user, db, "reports")
    ctx.update({
        "report": report_data,
        "target_year": target_year,
        "target_month": target_month
    })
    return templates.TemplateResponse(request, "admin/reports.html", ctx)

@router.get("/settings", response_class=HTMLResponse)
def admin_settings_view(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_optional(request, db=db)
    if not user or user.role != UserRole.ADMIN.value:
        return RedirectResponse(url="/login?error=Admin+access+required", status_code=303)

    periods = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()
    ctx = get_admin_context(request, user, db, "settings")
    ctx.update({
        "periods": periods,
        "settings": settings
    })
    return templates.TemplateResponse(request, "admin/settings.html", ctx)
