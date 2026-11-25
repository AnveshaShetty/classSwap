import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_acting_admin
from app.core.templating import templates
from app.database import get_db
from app.models import User
from app.services.admin import AdminNotFound, get_acting_admin
from app.services.dashboard import build_dashboard_data
from app.services.reports import build_monthly_report, render_monthly_csv


router = APIRouter()
MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}$")


def _can_view_reports(session: Session, current_user: User) -> bool:
    if current_user.role == "super_admin":
        return True
    try:
        acting_admin, _ = get_acting_admin(session, current_user.department, date.today())
    except AdminNotFound:
        return False
    return acting_admin.id == current_user.id


def _department_scope(current_user: User, requested: str | None) -> str | None:
    if current_user.role == "super_admin":
        return requested
    if requested and requested != current_user.department:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view reports for your department.",
        )
    return current_user.department


def _parse_month(month: str | None) -> date:
    if month is None:
        today = date.today()
        return today.replace(day=1)
    if not MONTH_PATTERN.fullmatch(month):
        raise HTTPException(status_code=422, detail="Month must use the YYYY-MM format.")
    try:
        return datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="Month must be a valid calendar month.") from error


@router.get("/stats/dashboard")
def read_dashboard_stats(
    selected_date: date | None = Query(default=None, alias="date"),
    department: str | None = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    scope = _department_scope(current_user, department)
    return build_dashboard_data(session, selected_date or date.today(), scope)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    selected_date: date | None = Query(default=None, alias="date"),
    department: str | None = None,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    scope = _department_scope(current_user, department)
    data = build_dashboard_data(session, selected_date or date.today(), scope)
    can_view_reports = _can_view_reports(session, current_user)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "request": request,
            "current_user": current_user,
            "today": date.today().isoformat(),
            "can_view_reports": can_view_reports,
            **data,
        },
    )


@router.get("/reports", response_class=HTMLResponse)
def reports_page(
    request: Request,
    month: str | None = None,
    department: str | None = None,
    current_user: User = Depends(require_acting_admin("reports")),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    scope = _department_scope(current_user, department)
    report = build_monthly_report(session, _parse_month(month), scope)
    return templates.TemplateResponse(
        request=request,
        name="reports.html",
        context={
            "request": request,
            "current_user": current_user,
            "today": date.today().isoformat(),
            "can_view_reports": True,
            **report,
        },
    )


@router.get("/reports/monthly")
def download_monthly_report(
    month: str | None = None,
    department: str | None = None,
    current_user: User = Depends(require_acting_admin("reports")),
    session: Session = Depends(get_db),
) -> StreamingResponse:
    scope = _department_scope(current_user, department)
    report = build_monthly_report(session, _parse_month(month), scope)
    csv_content = render_monthly_csv(report)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="classswap-%s.csv"' % report["month"],
        },
    )
