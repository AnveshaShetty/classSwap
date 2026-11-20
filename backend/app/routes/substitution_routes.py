from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from backend.app.database import get_db
from backend.app.core.dependencies import get_current_user, require_admin
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Room
from backend.app.models.timetable import Timetable
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus, DateOverride
from backend.app.schemas.substitution import (
    SubstitutionRequestCreate,
    SubstitutionAction,
    SubstitutionResponse
)
from backend.app.services.recommendation_engine import get_candidate_recommendations
from backend.app.services.notification_service import create_notification

router = APIRouter(prefix="/api/substitutions", tags=["Substitution Management"])

@router.post("/request", response_model=SubstitutionResponse)
def send_substitution_request(
    request_in: SubstitutionRequestCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Admin sends a substitution request to a recommended faculty member.
    """
    absence = db.query(Absence).filter(Absence.id == request_in.absence_id).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found.")

    substitute = db.query(User).filter(User.id == request_in.substitute_id).first()
    if not substitute or substitute.role != UserRole.FACULTY.value:
        raise HTTPException(status_code=404, detail="Substitute faculty not found.")

    day_of_week = absence.date.strftime("%A")
    tt = db.query(Timetable).filter(
        Timetable.faculty_id == absence.faculty_id,
        Timetable.day_of_week == day_of_week,
        Timetable.period_no == absence.period_no
    ).first()

    if not tt:
        raise HTTPException(status_code=400, detail="No scheduled class found for this absence.")

    # Determine room: use requested room, or default to original class room
    room_id = request_in.room_id if request_in.room_id else tt.room_id

    # Check if substitute is already requested or active on this slot
    existing = db.query(Substitution).filter(
        Substitution.absence_id == absence.id,
        Substitution.substitute_id == substitute.id,
        Substitution.status.in_([SubstitutionStatus.PENDING.value, SubstitutionStatus.ACCEPTED.value])
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"A request has already been sent to {substitute.name}.")

    # Calculate actual recommendation metrics for transparency & auditing
    recs = get_candidate_recommendations(db, absence, tt)
    match_rec = next((c for c in recs if c.faculty_id == substitute.id), None)
    
    score = match_rec.final_score if match_rec else 0.5
    sub_score = match_rec.subject_match if match_rec else 0.0
    fair_score = match_rec.fairness_score if match_rec else 0.5
    dept_score = match_rec.dept_match if match_rec else 0.0

    substitution = Substitution(
        absence_id=absence.id,
        timetable_id=tt.id,
        substitute_id=substitute.id,
        room_id=room_id,
        status=SubstitutionStatus.PENDING.value,
        score=score,
        subject_match_score=sub_score,
        fairness_score=fair_score,
        dept_match_score=dept_score,
        notes=request_in.notes
    )
    db.add(substitution)
    
    # Update absence status
    absence.status = AbsenceStatus.PROCESSING.value
    db.commit()
    db.refresh(substitution)

    # Notify Substitute Faculty
    create_notification(
        db=db,
        user_id=substitute.id,
        title="New Substitution Request",
        message=f"You have been requested to substitute for {tt.subject.name} on {absence.date} (Period {absence.period_no}, {tt.section.name}).",
        link="/faculty/requests"
    )

    return _build_substitution_response(substitution, tt, absence, substitute)

@router.post("/{sub_id}/action", response_model=SubstitutionResponse)
def handle_substitution_action(
    sub_id: int,
    action_in: SubstitutionAction,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Faculty accepts or declines a substitution request.
    Admins can also confirm or cancel on behalf of users.
    """
    sub = db.query(Substitution).filter(Substitution.id == sub_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution record not found.")

    # Permissions: must be target substitute or admin
    if current_user.role != UserRole.ADMIN.value and sub.substitute_id != current_user.id:
        raise HTTPException(status_code=403, detail="You are not authorized to respond to this request.")

    if sub.status != SubstitutionStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Request is already {sub.status}.")

    absence = sub.absence
    tt = sub.timetable_entry
    action_lower = action_in.action.lower()

    if action_lower == "accept":
        sub.status = SubstitutionStatus.ACCEPTED.value
        sub.updated_at = datetime.utcnow()
        if action_in.notes:
            sub.notes = action_in.notes

        # Create or update DateOverride record for the specific date
        # Never alters permanent weekly timetable!
        override = DateOverride(
            date=absence.date,
            period_no=absence.period_no,
            section_id=tt.section_id,
            subject_id=tt.subject_id,
            original_faculty_id=absence.faculty_id,
            substitute_faculty_id=sub.substitute_id,
            room_id=sub.room_id or tt.room_id,
            substitution_id=sub.id
        )
        db.add(override)

        # Mark absence as Arranged
        absence.status = AbsenceStatus.ARRANGED.value

        # Notify absent faculty
        create_notification(
            db=db,
            user_id=absence.faculty_id,
            title="Substitution Confirmed",
            message=f"{sub.substitute.name} accepted your substitution for {tt.subject.name} on {absence.date} (Period {absence.period_no}).",
            link="/faculty/dashboard"
        )

        # Notify Admins
        admins = db.query(User).filter(User.role == UserRole.ADMIN.value).all()
        for a in admins:
            create_notification(
                db=db,
                user_id=a.id,
                title="Substitution Accepted",
                message=f"{sub.substitute.name} accepted class for {tt.section.name} on {absence.date}.",
                link="/admin/substitutions"
            )

    elif action_lower == "decline":
        sub.status = SubstitutionStatus.DECLINED.value
        sub.updated_at = datetime.utcnow()
        if action_in.notes:
            sub.notes = action_in.notes

        # Revert absence status to Pending so admin can pick another candidate
        absence.status = AbsenceStatus.PENDING.value

        # Notify Admins to pick next candidate
        admins = db.query(User).filter(User.role == UserRole.ADMIN.value).all()
        for a in admins:
            create_notification(
                db=db,
                user_id=a.id,
                title="Substitution Request Declined",
                message=f"{sub.substitute.name} declined request for {absence.date} Period {absence.period_no}. Please select the next candidate.",
                link=f"/admin/absences"
            )

    else:
        raise HTTPException(status_code=400, detail="Invalid action. Must be 'accept' or 'decline'.")

    db.commit()
    db.refresh(sub)
    return _build_substitution_response(sub, tt, absence, sub.substitute)

@router.get("", response_model=List[SubstitutionResponse])
def list_substitutions(
    status_filter: Optional[str] = None,
    date_filter: Optional[date] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List substitution records with filters."""
    query = db.query(Substitution).join(Absence)

    if current_user.role == UserRole.FACULTY.value:
        # Faculty sees substitutions where they are substitute OR absent faculty
        query = query.filter(
            (Substitution.substitute_id == current_user.id) |
            (Absence.faculty_id == current_user.id)
        )

    if status_filter:
        query = query.filter(Substitution.status == status_filter)
    if date_filter:
        query = query.filter(Absence.date == date_filter)

    subs = query.order_by(Substitution.created_at.desc()).all()
    results = []
    for s in subs:
        tt = s.timetable_entry
        abs_rec = s.absence
        sub_fac = s.substitute
        results.append(_build_substitution_response(s, tt, abs_rec, sub_fac))
    return results

def _build_substitution_response(sub: Substitution, tt: Timetable, absence: Absence, substitute: User) -> SubstitutionResponse:
    return SubstitutionResponse(
        id=sub.id,
        absence_id=sub.absence_id,
        timetable_id=sub.timetable_id,
        substitute_id=sub.substitute_id,
        substitute_name=substitute.name if substitute else "Unknown",
        substitute_email=substitute.email if substitute else "",
        absent_faculty_name=absence.faculty.name if (absence and absence.faculty) else "Unknown",
        subject_name=tt.subject.name if (tt and tt.subject) else "Unknown",
        section_name=tt.section.name if (tt and tt.section) else "Unknown",
        date=absence.date if absence else date.today(),
        period_no=absence.period_no if absence else (tt.period_no if tt else 1),
        room_id=sub.room_id,
        room_name=sub.room.name if sub.room else (tt.room.name if (tt and tt.room) else "N/A"),
        status=sub.status,
        score=sub.score,
        subject_match_score=sub.subject_match_score,
        fairness_score=sub.fairness_score,
        dept_match_score=sub.dept_match_score,
        notes=sub.notes,
        created_at=sub.created_at,
        updated_at=sub.updated_at
    )
