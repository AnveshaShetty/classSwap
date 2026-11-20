from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database import get_db
from app.models import Substitution, User
from app.schemas.substitution import (
    FreeRoomRead,
    InboxItemRead,
    SubstitutionActionRead,
    SubstitutionCreate,
    SubstitutionRead,
    SubstitutionRespond,
)
from app.services.substitution import (
    SubstitutionConflict,
    SubstitutionForbidden,
    SubstitutionNotFound,
    create_substitution,
    find_free_rooms,
    get_inbox,
    respond_to_substitution,
)


router = APIRouter()


@router.post("/substitutions", response_model=SubstitutionRead)
def request_substitute(
    payload: SubstitutionCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Substitution:
    try:
        return create_substitution(
            session,
            payload.absence_id,
            payload.substitute_id,
            current_user.id,
        )
    except SubstitutionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except SubstitutionForbidden as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except SubstitutionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.patch("/substitutions/{substitution_id}", response_model=SubstitutionActionRead)
def respond_to_request(
    substitution_id: int,
    payload: SubstitutionRespond,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> SubstitutionActionRead:
    try:
        substitution, next_request = respond_to_substitution(
            session,
            substitution_id,
            current_user.id,
            payload.status,
        )
    except SubstitutionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except SubstitutionForbidden as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except SubstitutionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return SubstitutionActionRead(substitution=substitution, next_request=next_request)


@router.get("/substitutions/inbox", response_model=list[InboxItemRead])
def read_inbox(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[InboxItemRead]:
    return [InboxItemRead.model_validate(item) for item in get_inbox(session, current_user.id)]


@router.get("/rooms/free", response_model=list[FreeRoomRead])
def read_free_rooms(
    absence_id: int,
    _: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> list[FreeRoomRead]:
    try:
        return [
            FreeRoomRead.model_validate(room)
            for room in find_free_rooms(session, absence_id)
        ]
    except SubstitutionNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except SubstitutionConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
