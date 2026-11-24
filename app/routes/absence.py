from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.authorization import can_access_absence
from app.core.csrf import require_csrf
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.absence import AbsenceCreate, AbsenceRead
from app.schemas.suggestion import SuggestionRead
from app.services.absence import (
    AbsenceConflict,
    AbsenceNotFound,
    AbsenceSelectionError,
    get_absence,
    mark_absence,
)
from app.services.suggestion import suggest_candidates
from app.services.substitution import auto_request_for_hod_absence


router = APIRouter(dependencies=[Depends(require_csrf)])


@router.post("/absences", response_model=list[AbsenceRead])
def create_absences(
    payload: AbsenceCreate,
    faculty: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[AbsenceRead]:
    try:
        absences = mark_absence(
            session,
            faculty,
            payload.date,
            payload.periods,
            payload.reason,
        )
    except AbsenceSelectionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except AbsenceConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if faculty.role == "hod":
        for absence in absences:
            auto_request_for_hod_absence(session, absence)
    return [AbsenceRead.model_validate(absence) for absence in absences]


@router.get("/absences/{absence_id}/suggestions", response_model=list[SuggestionRead])
def read_suggestions(
    absence_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[SuggestionRead]:
    try:
        absence = get_absence(session, absence_id)
        owner = session.get(User, absence.faculty_id)
        if not can_access_absence(current_user, absence, owner):
            raise AbsenceNotFound("Absence not found.")
        suggestions = suggest_candidates(session, absence_id)
    except AbsenceNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return [SuggestionRead.model_validate(suggestion.__dict__) for suggestion in suggestions]
