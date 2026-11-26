from datetime import date
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.authorization import can_import_timetable
from app.core.csrf import require_csrf
from app.core.dependencies import get_current_user, require_policy
from app.database import get_db
from app.core.templating import templates
from app.models import User
from app.services.admin import AdminNotFound, get_acting_admin
from app.services.timetable import (
    MAX_UPLOAD_BYTES,
    TimetableCsvError,
    TimetableHistoryConflict,
    build_timetable_grid,
    import_timetable_csv,
)


router = APIRouter(dependencies=[Depends(require_csrf)])


@router.get("/timetable", response_class=HTMLResponse)
def read_timetable(
    request: Request,
    section: str | None = Query(default=None),
    faculty: str | None = Query(default=None),
    selected_date: date | None = Query(default=None, alias="date"),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    can_import = current_user.role == "super_admin"
    can_view_reports = current_user.role == "super_admin"
    if current_user.role != "super_admin":
        try:
            acting_admin, _ = get_acting_admin(session, current_user.department, date.today())
            can_view_reports = acting_admin.id == current_user.id
            can_import = current_user.role == "hod" and can_view_reports
        except AdminNotFound:
            can_import = False
    context = build_timetable_grid(
        session,
        selected_date or date.today(),
        section_name=section,
        faculty_email=faculty,
    )
    return templates.TemplateResponse(
        request=request,
        name="timetable.html",
        context={
            "request": request,
            "current_user": current_user,
            "can_import": can_import,
            "can_view_reports": can_view_reports,
            "today": date.today().isoformat(),
            **context,
        },
    )


@router.post("/timetable/import")
async def import_timetable(
    file: UploadFile = File(...),
    actor: User = Depends(require_policy(can_import_timetable)),
    session: Session = Depends(get_db),
) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail="Upload a .csv timetable file.")
    if file.content_type != "text/csv":
        raise HTTPException(status_code=415, detail="The uploaded file must have the text/csv content type.")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="The CSV file exceeds the 2 MB limit.")
    try:
        imported_rows = import_timetable_csv(session, content, actor=actor)
    except TimetableCsvError as error:
        raise HTTPException(
            status_code=422,
            detail={"message": str(error), "errors": error.errors},
        ) from error
    except TimetableHistoryConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": str(error), "errors": error.errors},
        ) from error
    return {"imported_rows": imported_rows}
