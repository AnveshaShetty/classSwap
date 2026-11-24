from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models import Section, Subject, Timetable, User
from app.services.absence import AbsenceNotFound, get_absence
from app.services.admin import AdminNotFound, get_acting_admin
from app.services.substitution import (
    SubstitutionConflict,
    SubstitutionForbidden,
    SubstitutionNotFound,
    get_inbox,
    respond_to_substitution,
)


router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))


def _can_view_reports(session: Session, current_user: User) -> bool:
    if current_user.role == "super_admin":
        return True
    try:
        acting_admin, _ = get_acting_admin(session, current_user.department, date.today())
    except AdminNotFound:
        return False
    return acting_admin.id == current_user.id


@router.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"request": request},
    )


@router.get("/absence/new", response_class=HTMLResponse)
def absence_form(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    if not current_user.teaches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is not eligible to mark teaching absences.",
        )
    return templates.TemplateResponse(
        request=request,
        name="absence_form.html",
        context={
            "request": request,
            "current_user": current_user,
            "max_period": settings.max_period,
            "today": date.today().isoformat(),
            "can_view_reports": _can_view_reports(session, current_user),
        },
    )


@router.get("/requests", response_class=HTMLResponse)
def requests_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="inbox.html",
        context={
            "request": request,
            "current_user": current_user,
            "today": date.today().isoformat(),
            "can_view_reports": _can_view_reports(session, current_user),
            "items": get_inbox(session, current_user.id),
        },
    )


@router.post("/requests/{substitution_id}/respond", response_class=HTMLResponse)
def respond_from_inbox(
    request: Request,
    substitution_id: int,
    response_status: Literal["accepted", "declined"] = Form(alias="status"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        _, next_request = respond_to_substitution(
            session,
            substitution_id,
            current_user.id,
            response_status,
        )
    except SubstitutionNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except SubstitutionForbidden as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    except SubstitutionConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return templates.TemplateResponse(
        request=request,
        name="request_result.html",
        context={
            "request": request,
            "current_user": current_user,
            "can_view_reports": _can_view_reports(session, current_user),
            "response_status": response_status,
            "next_request": next_request,
        },
    )


@router.get("/absences/{absence_id}/suggestions/view", response_class=HTMLResponse)
def suggestions_page(
    request: Request,
    absence_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        absence = get_absence(session, absence_id)
    except AbsenceNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    timetable = session.get(Timetable, absence.timetable_id)
    section = session.get(Section, timetable.section_id) if timetable is not None else None
    subject = session.get(Subject, timetable.subject_id) if timetable is not None else None
    if timetable is None or section is None or subject is None:
        raise HTTPException(status_code=409, detail="The absence is not linked to a complete class.")
    return templates.TemplateResponse(
        request=request,
        name="suggestions.html",
        context={
            "request": request,
            "current_user": current_user,
            "can_view_reports": _can_view_reports(session, current_user),
            "absence": absence,
            "section": section,
            "subject": subject,
            "today": date.today(),
        },
    )
