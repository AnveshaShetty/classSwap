from datetime import date
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, FacultySubject, Room, Section
from backend.app.models.timetable import Timetable
from backend.app.models.substitution import Absence, Substitution, SubstitutionStatus, DateOverride
from backend.app.schemas.substitution import CandidateRecommendation

def get_candidate_recommendations(
    db: Session,
    absence: Absence,
    timetable_entry: Optional[Timetable] = None
) -> List[CandidateRecommendation]:
    """
    Intelligent Substitute Recommendation Engine.
    Implements the exact multi-factor ranking formula:
    Final Score = (0.5 * Subject Match) + (0.3 * Fairness Score) + (0.2 * Department Match)
    All components normalized between 0.0 and 1.0.
    """
    # 1. Determine date and day of week
    absence_date: date = absence.date
    period_no: int = absence.period_no
    day_of_week: str = absence_date.strftime("%A")
    absent_faculty_id: int = absence.faculty_id

    # If timetable entry not passed, retrieve it
    if not timetable_entry:
        timetable_entry = db.query(Timetable).filter(
            Timetable.faculty_id == absent_faculty_id,
            Timetable.day_of_week == day_of_week,
            Timetable.period_no == period_no
        ).first()

    target_subject_id: Optional[int] = timetable_entry.subject_id if timetable_entry else None
    target_subject: Optional[Subject] = db.query(Subject).filter(Subject.id == target_subject_id).first() if target_subject_id else None
    
    absent_user = db.query(User).filter(User.id == absent_faculty_id).first()
    target_department: str = target_subject.department if target_subject else (absent_user.department if absent_user else "")

    # STEP 1: Identify Available Faculty
    # All active faculty members
    all_faculty = db.query(User).filter(
        User.role == UserRole.FACULTY.value,
        User.is_active == True,
        User.id != absent_faculty_id
    ).all()

    # IDs of faculty who have a scheduled timetable class in this period
    busy_timetable_ids = {
        row[0] for row in db.query(Timetable.faculty_id).filter(
            Timetable.day_of_week == day_of_week,
            Timetable.period_no == period_no
        ).all()
    }

    # IDs of faculty committed to an accepted substitution in this (date, period_no)
    busy_substitute_ids = {
        row[0] for row in db.query(Substitution.substitute_id).join(Absence).filter(
            Absence.date == absence_date,
            Absence.period_no == period_no,
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).all()
    }

    # IDs of faculty who are themselves absent on this (date, period_no)
    absent_today_ids = {
        row[0] for row in db.query(Absence.faculty_id).filter(
            Absence.date == absence_date,
            Absence.period_no == period_no
        ).all()
    }

    # Filter out busy faculty
    eligible_faculty = [
        f for f in all_faculty
        if f.id not in busy_timetable_ids
        and f.id not in busy_substitute_ids
        and f.id not in absent_today_ids
    ]

    if not eligible_faculty:
        return []

    # STEP 2: Calculate Recommendation Scores
    first_day_of_month = date(absence_date.year, absence_date.month, 1)

    # Pre-fetch monthly completed substitutions for fairness calculation
    # Count substitutions completed or accepted during the current month
    monthly_counts: Dict[int, int] = {}
    for f in eligible_faculty:
        cnt = db.query(func.count(Substitution.id)).join(Absence).filter(
            Substitution.substitute_id == f.id,
            Absence.date >= first_day_of_month,
            Absence.date <= absence_date,
            Substitution.status.in_([SubstitutionStatus.ACCEPTED.value, SubstitutionStatus.COMPLETED.value])
        ).scalar() or 0
        monthly_counts[f.id] = cnt

    counts_list = [monthly_counts[f.id] for f in eligible_faculty]
    min_count = min(counts_list) if counts_list else 0
    max_count = max(counts_list) if counts_list else 0

    # Pre-fetch subject qualifications for all eligible faculty
    faculty_ids = [f.id for f in eligible_faculty]
    qualified_rows = db.query(FacultySubject.faculty_id, FacultySubject.subject_id).filter(
        FacultySubject.faculty_id.in_(faculty_ids)
    ).all()
    
    faculty_subjects_map: Dict[int, set] = {f_id: set() for f_id in faculty_ids}
    for f_id, sub_id in qualified_rows:
        faculty_subjects_map[f_id].add(sub_id)

    # Department subjects mapping to check if faculty teaches any subject in same department
    dept_subject_ids = {
        row[0] for row in db.query(Subject.id).filter(Subject.department == target_department).all()
    }

    scored_candidates = []
    for f in eligible_faculty:
        # 1. Subject Match Score:
        # - 1.0 if qualified for exact subject
        # - 0.5 if faculty teaches a subject in the same department/area
        # - 0.0 otherwise
        f_sub_ids = faculty_subjects_map.get(f.id, set())
        if target_subject_id and target_subject_id in f_sub_ids:
            subject_match = 1.0
            relevance_msg = f"Qualified to teach {target_subject.name} (Direct Match)"
        elif bool(f_sub_ids.intersection(dept_subject_ids)):
            subject_match = 0.5
            relevance_msg = f"Teaches related subjects in {target_department}"
        else:
            subject_match = 0.0
            relevance_msg = "Different specialization area"

        # 2. Fairness Score:
        # Normalized based on completed monthly substitutions.
        # Faculty with fewer substitutions get higher scores.
        # Handle case where all faculty have the same count:
        c_i = monthly_counts[f.id]
        if max_count == min_count:
            fairness_score = 1.0
        else:
            fairness_score = round(1.0 - ((c_i - min_count) / (max_count - min_count)), 4)

        # 3. Department Match:
        # - 1.0 for same department
        # - 0.0 otherwise
        dept_match = 1.0 if (f.department and f.department.strip().lower() == target_department.strip().lower()) else 0.0

        # Final Score Formula:
        final_score = round((0.5 * subject_match) + (0.3 * fairness_score) + (0.2 * dept_match), 4)

        details = f"{relevance_msg} | Monthly Subs: {c_i} | Dept: {f.department}"

        candidate = CandidateRecommendation(
            faculty_id=f.id,
            faculty_name=f.name,
            email=f.email,
            department=f.department,
            monthly_substitutions=c_i,
            subject_match=subject_match,
            fairness_score=fairness_score,
            dept_match=dept_match,
            final_score=final_score,
            relevance_details=details,
            is_top_choice=False
        )
        scored_candidates.append(candidate)

    # STEP 3: Rank Candidates
    # Sort descending by final_score, then fairness_score, then name
    scored_candidates.sort(key=lambda c: (c.final_score, c.fairness_score, -c.monthly_substitutions), reverse=True)

    if scored_candidates:
        scored_candidates[0].is_top_choice = True

    return scored_candidates
