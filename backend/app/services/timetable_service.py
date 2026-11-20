import io
import pandas as pd
from typing import List, Dict, Any, Tuple, Optional
from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from backend.app.models.user import User, UserRole
from backend.app.models.academic import Section, Subject, Room
from backend.app.models.timetable import Timetable, PeriodConfig
from backend.app.models.substitution import Absence, Substitution, SubstitutionStatus, DateOverride
from backend.app.schemas.timetable import TimetableUploadPreviewItem, TimetableUploadResponse

VALID_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

def validate_timetable_csv(file_content: bytes, db: Session) -> Tuple[List[Dict[str, Any]], List[TimetableUploadPreviewItem]]:
    """
    Parse and validate uploaded CSV timetable.
    Returns (valid_entries_dict_list, preview_items_list).
    """
    df = pd.read_csv(io.BytesIO(file_content))

    required_columns = ["section_name", "subject_name", "faculty_email", "room_name", "day_of_week", "period_no"]
    missing_cols = [c for c in required_columns if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in CSV: {', '.join(missing_cols)}")

    # Pre-fetch lookup caches for fast validation
    sections = {s.name.strip().lower(): s for s in db.query(Section).all()}
    subjects = {s.name.strip().lower(): s for s in db.query(Subject).all()}
    faculties = {f.email.strip().lower(): f for f in db.query(User).filter(User.role == UserRole.FACULTY.value).all()}
    rooms = {r.name.strip().lower(): r for r in db.query(Room).all()}

    preview_items: List[TimetableUploadPreviewItem] = []
    valid_entries: List[Dict[str, Any]] = []

    # Track within-batch clashes to avoid internal duplicates in CSV
    seen_faculty_slots = set()
    seen_room_slots = set()
    seen_section_slots = set()

    for idx, row in df.iterrows():
        errors = []
        sec_name = str(row.get("section_name", "")).strip()
        sub_name = str(row.get("subject_name", "")).strip()
        fac_email = str(row.get("faculty_email", "")).strip()
        rm_name = str(row.get("room_name", "")).strip()
        day = str(row.get("day_of_week", "")).strip().capitalize()
        
        try:
            p_no = int(row.get("period_no", 0))
        except (ValueError, TypeError):
            p_no = 0
            errors.append("period_no must be a valid integer.")

        if p_no < 1 or p_no > 8:
            errors.append(f"period_no {p_no} is out of typical range (1-8).")

        if day not in VALID_DAYS:
            errors.append(f"Invalid day_of_week '{day}'. Must be one of: {', '.join(VALID_DAYS)}")

        sec_obj = sections.get(sec_name.lower())
        if not sec_obj:
            errors.append(f"Section '{sec_name}' does not exist in database.")

        sub_obj = subjects.get(sub_name.lower())
        if not sub_obj:
            errors.append(f"Subject '{sub_name}' does not exist in database.")

        fac_obj = faculties.get(fac_email.lower())
        if not fac_obj:
            errors.append(f"Faculty with email '{fac_email}' not found.")

        rm_obj = rooms.get(rm_name.lower())
        if not rm_obj:
            errors.append(f"Room '{rm_name}' does not exist in database.")

        # In-batch duplicate clash check
        if fac_obj and day and p_no:
            fac_slot = (fac_obj.id, day, p_no)
            if fac_slot in seen_faculty_slots:
                errors.append(f"Conflict: Faculty {fac_email} scheduled multiple times on {day} Period {p_no}.")
            else:
                seen_faculty_slots.add(fac_slot)

        if rm_obj and day and p_no:
            rm_slot = (rm_obj.id, day, p_no)
            if rm_slot in seen_room_slots:
                errors.append(f"Conflict: Room {rm_name} booked multiple times on {day} Period {p_no}.")
            else:
                seen_room_slots.add(rm_slot)

        if sec_obj and day and p_no:
            sec_slot = (sec_obj.id, day, p_no)
            if sec_slot in seen_section_slots:
                errors.append(f"Conflict: Section {sec_name} has multiple classes on {day} Period {p_no}.")
            else:
                seen_section_slots.add(sec_slot)

        # Database existing clash check
        if not errors and sec_obj and sub_obj and fac_obj and rm_obj:
            existing_fac_clash = db.query(Timetable).filter(
                Timetable.faculty_id == fac_obj.id,
                Timetable.day_of_week == day,
                Timetable.period_no == p_no
            ).first()
            if existing_fac_clash:
                errors.append(f"Faculty {fac_email} already has a class in DB on {day} P{p_no}.")

            existing_rm_clash = db.query(Timetable).filter(
                Timetable.room_id == rm_obj.id,
                Timetable.day_of_week == day,
                Timetable.period_no == p_no
            ).first()
            if existing_rm_clash:
                errors.append(f"Room {rm_name} already occupied in DB on {day} P{p_no}.")

            existing_sec_clash = db.query(Timetable).filter(
                Timetable.section_id == sec_obj.id,
                Timetable.day_of_week == day,
                Timetable.period_no == p_no
            ).first()
            if existing_sec_clash:
                errors.append(f"Section {sec_name} already has a class in DB on {day} P{p_no}.")

        is_valid = len(errors) == 0
        if is_valid:
            valid_entries.append({
                "section_id": sec_obj.id,
                "subject_id": sub_obj.id,
                "faculty_id": fac_obj.id,
                "room_id": rm_obj.id,
                "day_of_week": day,
                "period_no": p_no
            })

        preview_items.append(
            TimetableUploadPreviewItem(
                section_name=sec_name,
                subject_name=sub_name,
                faculty_email=fac_email,
                room_name=rm_name,
                day_of_week=day,
                period_no=p_no,
                is_valid=is_valid,
                errors=errors
            )
        )

    return valid_entries, preview_items

def commit_timetable_entries(valid_entries: List[Dict[str, Any]], db: Session) -> int:
    """Save validated timetable rows to database with rollback protection."""
    saved_count = 0
    try:
        for item in valid_entries:
            entry = Timetable(
                section_id=item["section_id"],
                subject_id=item["subject_id"],
                faculty_id=item["faculty_id"],
                room_id=item["room_id"],
                day_of_week=item["day_of_week"],
                period_no=item["period_no"]
            )
            db.add(entry)
            saved_count += 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    return saved_count

def get_date_specific_timetable(
    db: Session,
    target_date: date,
    section_id: Optional[int] = None,
    faculty_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve timetable for a specific calendar date, seamlessly merging
    the permanent weekly schedule with temporary substitution overrides and absence flags.
    Never overwrites permanent timetable data.
    """
    day_of_week = target_date.strftime("%A")

    query = db.query(Timetable).filter(Timetable.day_of_week == day_of_week)
    if section_id:
        query = query.filter(Timetable.section_id == section_id)
    if faculty_id:
        # Match where faculty is original OR where faculty is substitute in date override
        query = query.filter(Timetable.faculty_id == faculty_id)

    regular_entries = query.order_by(Timetable.period_no).all()

    # Fetch date overrides for this date
    overrides_query = db.query(DateOverride).filter(DateOverride.date == target_date)
    if section_id:
        overrides_query = overrides_query.filter(DateOverride.section_id == section_id)
    overrides = overrides_query.all()
    override_by_section_period = {
        (o.section_id, o.period_no): o for o in overrides
    }

    # Fetch absences for this date
    absences = db.query(Absence).filter(Absence.date == target_date).all()
    absence_by_faculty_period = {
        (a.faculty_id, a.period_no): a for a in absences
    }

    # Fetch any substitutions where faculty_id is the substitute on this date (even if not in regular timetable)
    substitute_classes = []
    if faculty_id:
        sub_overrides = db.query(DateOverride).filter(
            DateOverride.date == target_date,
            DateOverride.substitute_faculty_id == faculty_id
        ).all()
        for sov in sub_overrides:
            substitute_classes.append({
                "timetable_id": None,
                "section_id": sov.section_id,
                "section_name": sov.section.name if sov.section else "",
                "subject_id": sov.subject_id,
                "subject_name": sov.subject.name if sov.subject else "",
                "subject_code": sov.subject.code if sov.subject else "",
                "faculty_id": sov.substitute_faculty_id,
                "faculty_name": f"{sov.substitute_faculty.name} (Substitute)",
                "original_faculty_name": sov.original_faculty.name if sov.original_faculty else "",
                "room_id": sov.room_id,
                "room_name": sov.room.name if sov.room else "",
                "day_of_week": day_of_week,
                "period_no": sov.period_no,
                "is_substituted": True,
                "is_substitute_duty": True,
                "is_absent": False,
                "status_badge": "Substitute Duty"
            })

    results = []
    for entry in regular_entries:
        sec_id = entry.section_id
        p_no = entry.period_no
        fac_id = entry.faculty_id

        # Check if an override exists for this section and period
        override = override_by_section_period.get((sec_id, p_no))
        absence = absence_by_faculty_period.get((fac_id, p_no))

        if override:
            results.append({
                "timetable_id": entry.id,
                "section_id": sec_id,
                "section_name": entry.section.name,
                "subject_id": override.subject_id,
                "subject_name": override.subject.name,
                "subject_code": override.subject.code,
                "faculty_id": override.substitute_faculty_id,
                "faculty_name": f"{override.substitute_faculty.name} (Substitute)",
                "original_faculty_name": override.original_faculty.name,
                "room_id": override.room_id,
                "room_name": override.room.name,
                "day_of_week": day_of_week,
                "period_no": p_no,
                "is_substituted": True,
                "is_substitute_duty": (faculty_id == override.substitute_faculty_id),
                "is_absent": False,
                "status_badge": "Substituted"
            })
        elif absence:
            results.append({
                "timetable_id": entry.id,
                "section_id": sec_id,
                "section_name": entry.section.name,
                "subject_id": entry.subject_id,
                "subject_name": entry.subject.name,
                "subject_code": entry.subject.code,
                "faculty_id": fac_id,
                "faculty_name": entry.faculty.name,
                "original_faculty_name": entry.faculty.name,
                "room_id": entry.room_id,
                "room_name": entry.room.name,
                "day_of_week": day_of_week,
                "period_no": p_no,
                "is_substituted": False,
                "is_substitute_duty": False,
                "is_absent": True,
                "absence_status": absence.status,
                "status_badge": f"Faculty Absent ({absence.status})"
            })
        else:
            results.append({
                "timetable_id": entry.id,
                "section_id": sec_id,
                "section_name": entry.section.name,
                "subject_id": entry.subject_id,
                "subject_name": entry.subject.name,
                "subject_code": entry.subject.code,
                "faculty_id": fac_id,
                "faculty_name": entry.faculty.name,
                "original_faculty_name": entry.faculty.name,
                "room_id": entry.room_id,
                "room_name": entry.room.name,
                "day_of_week": day_of_week,
                "period_no": p_no,
                "is_substituted": False,
                "is_substitute_duty": False,
                "is_absent": False,
                "status_badge": "Scheduled"
            })

    # Add any substitute duties if filtering by faculty
    results.extend(substitute_classes)
    results.sort(key=lambda x: x["period_no"])
    return results
