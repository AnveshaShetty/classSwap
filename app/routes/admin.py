from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_acting_admin, require_admin_mfa, require_roles
from app.database import get_db
from app.models import User
from app.schemas.admin import (
    ActingAdminRead,
    AdminChainEntryRead,
    AdminChainRead,
    AdminChainUpdate,
    LeaveCreate,
    LeaveRead,
)
from app.services.admin import (
    AdminConflict,
    AdminNotFound,
    cancel_whole_day_leave,
    create_whole_day_leave,
    get_acting_admin,
    read_admin_chain,
    replace_admin_chain,
)


router = APIRouter()


@router.get("/admin/acting", response_model=ActingAdminRead)
def read_acting_admin(
    current_user: User = Depends(get_current_user),
    department: str | None = None,
    session: Session = Depends(get_db),
) -> ActingAdminRead:
    target_department = department or current_user.department
    try:
        user, position = get_acting_admin(session, target_department, date.today())
    except AdminNotFound as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    return ActingAdminRead(
        name=user.name,
        email=user.email,
        role=user.role,
        department=user.department,
        position=position,
    )


@router.post("/admin/users/{user_id}/force-logout", status_code=status.HTTP_204_NO_CONTENT)
def force_logout_user(
    user_id: int,
    actor: User = Depends(require_roles("super_admin")),
    _: User = Depends(require_admin_mfa),
    session: Session = Depends(get_db),
) -> None:
    target = session.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    target.token_version += 1
    session.commit()


@router.get("/admin/chain", response_model=AdminChainRead)
def get_admin_chain(
    current_user: User = Depends(require_acting_admin("chain")),
    department: str | None = None,
    session: Session = Depends(get_db),
) -> AdminChainRead:
    target_department = department or current_user.department
    if current_user.role != "super_admin" and target_department != current_user.department:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only view your department's admin chain.",
        )
    entries = read_admin_chain(session, target_department)
    return AdminChainRead(
        department=target_department,
        entries=[
            AdminChainEntryRead(
                position=chain_entry.position,
                email=user.email,
                name=user.name,
                role=user.role,
            )
            for chain_entry, user in entries
        ],
    )


@router.put("/admin/chain", response_model=AdminChainRead)
def update_admin_chain(
    payload: AdminChainUpdate,
    current_user: User = Depends(require_acting_admin("chain")),
    session: Session = Depends(get_db),
) -> AdminChainRead:
    try:
        entries = replace_admin_chain(
            session,
            current_user,
            payload.department,
            [(entry.position, str(entry.email)) for entry in payload.entries],
        )
    except AdminConflict as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    return AdminChainRead(
        department=payload.department,
        entries=[
            AdminChainEntryRead(
                position=chain_entry.position,
                email=user.email,
                name=user.name,
                role=user.role,
            )
            for chain_entry, user in entries
        ],
    )


@router.post("/leaves", response_model=LeaveRead)
def create_leave(
    payload: LeaveCreate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> LeaveRead:
    try:
        leave, absence_count = create_whole_day_leave(
            session,
            current_user,
            payload.date,
            payload.reason,
        )
    except AdminConflict as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return LeaveRead(
        user_id=leave.user_id,
        date=leave.date,
        absences_created=absence_count,
    )


@router.delete("/leaves/{leave_date}", status_code=status.HTTP_204_NO_CONTENT)
def delete_leave(
    leave_date: date,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> None:
    try:
        cancel_whole_day_leave(session, current_user, leave_date)
    except AdminNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
