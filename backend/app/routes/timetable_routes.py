import io
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date

from backend.app.database import get_db
from backend.app.core.dependencies import get_current_user, require_admin
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Section, Subject, Room
from backend.app.models.timetable import Timetable, PeriodConfig
from backend.app.schemas.timetable import (
    TimetableCreate,
    TimetableUpdate,
    TimetableResponse,
    TimetableUploadResponse,
    PeriodConfigResponse
)
from backend.app.services.timetable_service import (
    validate_timetable_csv,
    commit_timetable_entries,
    get_date_specific_timetable,
    VALID_DAYS
)

router = APIRouter(prefix="/api/timetable", tags=["Timetable Management"])

@router.get("/template")
def download_csv_template():
    """Download the official ClassSwap Timetable CSV template."""
    csv_content = (
        "section_name,subject_name,faculty_email,room_name,day_of_week,period_no\n"
        "CSE-A (3rd Sem),Data Structures & Algorithms,rajesh.kumar@classswap.edu,LH-101,Monday,1\n"
        "CSE-A (3rd Sem),Database Management Systems,anita.sharma@classswap.edu,LH-101,Monday,2\n"
        "CSE-B (5th Sem),Computer Networks,vikram.singh@classswap.edu,LH-102,Monday,1\n"
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=classswap_timetable_template.csv"}
    )

@router.post("/upload", response_model=TimetableUploadResponse)
async def upload_timetable_csv(
    file: UploadFile = File(...),
    commit: bool = False,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """
    Upload CSV timetable file.
    If commit=False: validates and returns preview with any row-level errors.
    If commit=True: validates and saves valid rows into database.
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files (.csv) are accepted.")

    content = await file.read()
    try:
        valid_entries, preview_items = validate_timetable_csv(content, db)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    error_count = sum(1 for item in preview_items if not item.is_valid)
    valid_count = len(valid_entries)

    saved_count = 0
    message = f"Validated {len(preview_items)} rows: {valid_count} valid, {error_count} errors."

    if commit and valid_count > 0:
        saved_count = commit_timetable_entries(valid_entries, db)
        message = f"Successfully imported {saved_count} timetable entries into the database!"

    return TimetableUploadResponse(
        total_rows=len(preview_items),
        valid_rows=valid_count,
        error_rows=error_count,
        preview=preview_items[:50],  # preview top 50 rows
        message=message
    )

@router.get("", response_model=List[TimetableResponse])
def get_timetable(
    section_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    day_of_week: Optional[str] = None,
    period_no: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Retrieve permanent timetable entries with relational details."""
    query = db.query(Timetable)
    if section_id:
        query = query.filter(Timetable.section_id == section_id)
    if faculty_id:
        query = query.filter(Timetable.faculty_id == faculty_id)
    if day_of_week:
        query = query.filter(Timetable.day_of_week == day_of_week)
    if period_no:
        query = query.filter(Timetable.period_no == period_no)

    entries = query.order_by(Timetable.day_of_week, Timetable.period_no).all()
    
    results = []
    for e in entries:
        results.append(
            TimetableResponse(
                id=e.id,
                section_id=e.section_id,
                subject_id=e.subject_id,
                faculty_id=e.faculty_id,
                room_id=e.room_id,
                day_of_week=e.day_of_week,
                period_no=e.period_no,
                section_name=e.section.name if e.section else None,
                subject_name=e.subject.name if e.subject else None,
                subject_code=e.subject.code if e.subject else None,
                faculty_name=e.faculty.name if e.faculty else None,
                room_name=e.room.name if e.room else None
            )
        )
    return results

@router.post("", response_model=TimetableResponse)
def add_timetable_entry(
    entry_in: TimetableCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Manually add a timetable entry with conflict verification."""
    # Check Section existence
    sec = db.query(Section).filter(Section.id == entry_in.section_id).first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found.")

    sub = db.query(Subject).filter(Subject.id == entry_in.subject_id).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Subject not found.")

    fac = db.query(User).filter(User.id == entry_in.faculty_id, User.role == UserRole.FACULTY.value).first()
    if not fac:
        raise HTTPException(status_code=404, detail="Faculty member not found.")

    rm = db.query(Room).filter(Room.id == entry_in.room_id).first()
    if not rm:
        raise HTTPException(status_code=404, detail="Room not found.")

    # Conflict check 1: Faculty clash
    fac_clash = db.query(Timetable).filter(
        Timetable.faculty_id == entry_in.faculty_id,
        Timetable.day_of_week == entry_in.day_of_week,
        Timetable.period_no == entry_in.period_no
    ).first()
    if fac_clash:
        raise HTTPException(status_code=400, detail=f"Faculty {fac.name} already assigned to another class on {entry_in.day_of_week} Period {entry_in.period_no}.")

    # Conflict check 2: Room clash
    rm_clash = db.query(Timetable).filter(
        Timetable.room_id == entry_in.room_id,
        Timetable.day_of_week == entry_in.day_of_week,
        Timetable.period_no == entry_in.period_no
    ).first()
    if rm_clash:
        raise HTTPException(status_code=400, detail=f"Room {rm.name} is already booked on {entry_in.day_of_week} Period {entry_in.period_no}.")

    # Conflict check 3: Section clash
    sec_clash = db.query(Timetable).filter(
        Timetable.section_id == entry_in.section_id,
        Timetable.day_of_week == entry_in.day_of_week,
        Timetable.period_no == entry_in.period_no
    ).first()
    if sec_clash:
        raise HTTPException(status_code=400, detail=f"Section {sec.name} already has a class on {entry_in.day_of_week} Period {entry_in.period_no}.")

    new_entry = Timetable(
        section_id=entry_in.section_id,
        subject_id=entry_in.subject_id,
        faculty_id=entry_in.faculty_id,
        room_id=entry_in.room_id,
        day_of_week=entry_in.day_of_week,
        period_no=entry_in.period_no
    )
    db.add(new_entry)
    db.commit()
    db.refresh(new_entry)

    return TimetableResponse(
        id=new_entry.id,
        section_id=new_entry.section_id,
        subject_id=new_entry.subject_id,
        faculty_id=new_entry.faculty_id,
        room_id=new_entry.room_id,
        day_of_week=new_entry.day_of_week,
        period_no=new_entry.period_no,
        section_name=sec.name,
        subject_name=sub.name,
        subject_code=sub.code,
        faculty_name=fac.name,
        room_name=rm.name
    )

@router.delete("/{entry_id}")
def delete_timetable_entry(
    entry_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a timetable entry."""
    entry = db.query(Timetable).filter(Timetable.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found.")
    db.delete(entry)
    db.commit()
    return {"message": "Timetable entry deleted successfully."}

@router.get("/date-specific")
def get_date_timetable(
    target_date: date,
    section_id: Optional[int] = None,
    faculty_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Retrieve timetable for a specific calendar date, showing regular classes,
    absent markers, and accepted substitute classes.
    """
    entries = get_date_specific_timetable(
        db=db,
        target_date=target_date,
        section_id=section_id,
        faculty_id=faculty_id
    )
    return entries

@router.get("/periods", response_model=List[PeriodConfigResponse])
def get_periods(db: Session = Depends(get_db)):
    """Retrieve list of period configurations (timings, labels)."""
    configs = db.query(PeriodConfig).order_by(PeriodConfig.period_no).all()
    return configs
