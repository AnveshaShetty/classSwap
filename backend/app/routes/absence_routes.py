from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime

from backend.app.database import get_db
from backend.app.core.dependencies import get_current_user, require_admin
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, Section, Room
from backend.app.models.timetable import Timetable
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus
from backend.app.schemas.substitution import AbsenceCreate, AbsenceResponse, RecommendationResponse
from backend.app.services.recommendation_engine import get_candidate_recommendations
from backend.app.services.room_finder import find_available_rooms
from backend.app.services.notification_service import create_notification

router = APIRouter(prefix="/api/absences", tags=["Absence Management"])

@router.post("", response_model=List[AbsenceResponse])
def create_absence(
    absence_in: AbsenceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Submit an absence for one or more periods.
    Faculty can submit for themselves; Admins can submit on behalf of any faculty member.
    """
    # Determine target faculty
    if current_user.role == UserRole.ADMIN.value and absence_in.faculty_id:
        target_faculty_id = absence_in.faculty_id
    else:
        target_faculty_id = current_user.id

    target_faculty = db.query(User).filter(User.id == target_faculty_id).first()
    if not target_faculty:
        raise HTTPException(status_code=404, detail="Faculty member not found.")

    day_of_week = absence_in.date.strftime("%A")
    created_absences = []

    for p_no in absence_in.period_nos:
        # Check duplicate
        existing = db.query(Absence).filter(
            Absence.faculty_id == target_faculty_id,
            Absence.date == absence_in.date,
            Absence.period_no == p_no
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Absence already recorded for {target_faculty.name} on {absence_in.date} for Period {p_no}."
            )

        absence = Absence(
            faculty_id=target_faculty_id,
            date=absence_in.date,
            period_no=p_no,
            reason=absence_in.reason,
            status=AbsenceStatus.PENDING.value
        )
        db.add(absence)
        db.flush()  # to get absence.id

        # Check if there is an affected timetable class
        tt = db.query(Timetable).filter(
            Timetable.faculty_id == target_faculty_id,
            Timetable.day_of_week == day_of_week,
            Timetable.period_no == p_no
        ).first()

        created_absences.append(
            AbsenceResponse(
                id=absence.id,
                faculty_id=absence.faculty_id,
                faculty_name=target_faculty.name,
                date=absence.date,
                period_no=absence.period_no,
                reason=absence.reason,
                status=absence.status,
                created_at=absence.created_at,
                timetable_id=tt.id if tt else None,
                subject_name=tt.subject.name if tt else None,
                section_name=tt.section.name if tt else None,
                room_name=tt.room.name if tt else None
            )
        )

    db.commit()

    # Notify Admins about the absence
    admins = db.query(User).filter(User.role == UserRole.ADMIN.value).all()
    for admin in admins:
        create_notification(
            db=db,
            user_id=admin.id,
            title="Faculty Absence Reported",
            message=f"{target_faculty.name} marked absent on {absence_in.date} for period(s): {', '.join(map(str, absence_in.period_nos))}",
            link=f"/admin/absences"
        )

    return created_absences

@router.get("", response_model=List[AbsenceResponse])
def list_absences(
    date_filter: Optional[date] = None,
    faculty_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List absences with optional filtering."""
    query = db.query(Absence)
    
    # If faculty user, restrict to their own absences unless admin
    if current_user.role == UserRole.FACULTY.value:
        query = query.filter(Absence.faculty_id == current_user.id)
    elif faculty_id:
        query = query.filter(Absence.faculty_id == faculty_id)

    if date_filter:
        query = query.filter(Absence.date == date_filter)
    if status_filter:
        query = query.filter(Absence.status == status_filter)

    absences = query.order_by(Absence.date.desc(), Absence.period_no).all()
    
    results = []
    for a in absences:
        day_of_week = a.date.strftime("%A")
        tt = db.query(Timetable).filter(
            Timetable.faculty_id == a.faculty_id,
            Timetable.day_of_week == day_of_week,
            Timetable.period_no == a.period_no
        ).first()

        results.append(
            AbsenceResponse(
                id=a.id,
                faculty_id=a.faculty_id,
                faculty_name=a.faculty.name if a.faculty else "Unknown",
                date=a.date,
                period_no=a.period_no,
                reason=a.reason,
                status=a.status,
                created_at=a.created_at,
                timetable_id=tt.id if tt else None,
                subject_name=tt.subject.name if tt else "No regular class scheduled",
                section_name=tt.section.name if tt else "N/A",
                room_name=tt.room.name if tt else "N/A"
            )
        )
    return results

@router.get("/{absence_id}/recommendations", response_model=RecommendationResponse)
def get_recommendations_for_absence(
    absence_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get ranked substitute faculty recommendations and suitable free classrooms
    for an absence using the Intelligent Substitute Recommendation Engine.
    """
    absence = db.query(Absence).filter(Absence.id == absence_id).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence record not found.")

    day_of_week = absence.date.strftime("%A")
    tt = db.query(Timetable).filter(
        Timetable.faculty_id == absence.faculty_id,
        Timetable.day_of_week == day_of_week,
        Timetable.period_no == absence.period_no
    ).first()

    if not tt:
        raise HTTPException(
            status_code=400,
            detail=f"No scheduled timetable class found for {absence.faculty.name} on {day_of_week} Period {absence.period_no}."
        )

    # 1. Run Recommendation Engine
    candidates = get_candidate_recommendations(db, absence, tt)

    # 2. Run Free Room Finder
    suitable_rooms = find_available_rooms(
        db=db,
        query_date=absence.date,
        period_no=absence.period_no,
        section_id=tt.section_id,
        is_lab=tt.subject.is_lab if tt.subject else False,
        allow_lab_for_theory=False,
        exclude_room_id=None
    )

    return RecommendationResponse(
        absence_id=absence.id,
        timetable_id=tt.id,
        date=absence.date,
        period_no=absence.period_no,
        subject_name=tt.subject.name,
        subject_code=tt.subject.code,
        is_lab=tt.subject.is_lab,
        section_name=tt.section.name,
        section_strength=tt.section.strength,
        current_room_name=tt.room.name,
        candidates=candidates[:5],  # top 5 candidates
        suitable_rooms=suitable_rooms[:4]  # top 4 suitable rooms
    )

@router.delete("/{absence_id}")
def cancel_absence(
    absence_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel an absence request."""
    absence = db.query(Absence).filter(Absence.id == absence_id).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found.")

    if current_user.role != UserRole.ADMIN.value and absence.faculty_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this absence.")

    db.delete(absence)
    db.commit()
    return {"message": "Absence cancelled successfully."}
