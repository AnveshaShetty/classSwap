from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    Absence,
    FacultyAllocation,
    FacultySubject,
    Section,
    Subject,
    Substitution,
    Timetable,
    User,
)
from app.services.absence import get_absence


@dataclass(frozen=True)
class ScoreWeights:
    subject_match: float = settings.subject_match_weight
    adjacent_free: float = settings.adjacent_free_weight
    fairness: float = settings.fairness_weight
    same_semester: float = settings.same_semester_weight
    same_department: float = settings.same_department_weight


@dataclass(frozen=True)
class CandidateFeatures:
    faculty_id: int
    name: str
    email: str
    subject_match: float
    adjacent_free: float
    fairness: float
    same_semester: float
    same_department: float
    monthly_substitutions: int


@dataclass(frozen=True)
class Suggestion:
    faculty_id: int
    name: str
    email: str
    score: float
    reason: str


def subject_match_score(same_subject: bool, related_subject_in_department: bool) -> float:
    if same_subject:
        return 1.0
    if related_subject_in_department:
        return 0.5
    return 0.0


def fairness_score(monthly_substitutions: int, highest_count: int) -> float:
    if monthly_substitutions < 0 or highest_count < 0:
        raise ValueError("Substitution counts cannot be negative.")
    if highest_count == 0:
        return 1.0
    return max(0.0, min(1.0, 1.0 - monthly_substitutions / highest_count))


def adjacent_free_score(
    period: int,
    max_period: int,
    busy_periods: set[int],
    break_after: tuple[int, ...],
) -> float:
    if not 1 <= period <= max_period:
        raise ValueError("Period is outside the configured day.")

    busy_sides = 0
    if period > 1 and period - 1 not in break_after and period - 1 in busy_periods:
        busy_sides += 1
    if period < max_period and period not in break_after and period + 1 in busy_periods:
        busy_sides += 1
    return 1.0 - busy_sides / 2.0


def calculate_score(features: CandidateFeatures, weights: ScoreWeights = ScoreWeights()) -> float:
    values = (
        features.subject_match,
        features.adjacent_free,
        features.fairness,
        features.same_semester,
        features.same_department,
    )
    if any(value < 0 or value > 1 for value in values):
        raise ValueError("Suggestion score components must be between 0 and 1.")
    weight_values = (
        weights.subject_match,
        weights.adjacent_free,
        weights.fairness,
        weights.same_semester,
        weights.same_department,
    )
    if any(weight < 0 for weight in weight_values):
        raise ValueError("Suggestion weights cannot be negative.")
    result = sum(value * weight for value, weight in zip(values, weight_values))
    return max(0.0, min(1.0, result))


def _reason(features: CandidateFeatures) -> str:
    if features.subject_match == 1:
        subject_reason = "teaches the same subject"
    elif features.subject_match == 0.5:
        subject_reason = "teaches a related subject in this department"
    else:
        subject_reason = "no subject match"

    if features.adjacent_free == 1:
        load_reason = "no back-to-back load"
    elif features.adjacent_free == 0.5:
        load_reason = "one adjacent period is busy"
    else:
        load_reason = "both adjacent periods are busy"
    return "Free this period; %s; %s; %d substitution(s) this month." % (
        subject_reason,
        load_reason,
        features.monthly_substitutions,
    )


def rank_candidates(
    candidates: Iterable[CandidateFeatures],
    weights: ScoreWeights = ScoreWeights(),
) -> list[Suggestion]:
    scored = []
    for candidate in candidates:
        score = calculate_score(candidate, weights)
        scored.append((
            score,
            Suggestion(
                faculty_id=candidate.faculty_id,
                name=candidate.name,
                email=candidate.email,
                score=score,
                reason=_reason(candidate),
            ),
        ))
    scored.sort(key=lambda result: (-result[0], result[1].email))
    return [suggestion for _, suggestion in scored]


def _month_bounds(target: date) -> tuple[date, date]:
    first = target.replace(day=1)
    if first.month == 12:
        following_month = first.replace(year=first.year + 1, month=1)
    else:
        following_month = first.replace(month=first.month + 1)
    return first, following_month


def suggest_candidates(session: Session, absence_id: int) -> list[Suggestion]:
    absence = get_absence(session, absence_id)
    timetable = session.get(Timetable, absence.timetable_id)
    if timetable is None:
        raise ValueError("The absence is not linked to a timetable class.")
    subject = session.get(Subject, timetable.subject_id)
    section = session.get(Section, timetable.section_id)
    if subject is None or section is None:
        raise ValueError("The absence timetable class is incomplete.")

    candidates = list(session.scalars(
        select(User).where(
            User.teaches.is_(True),
            User.id != absence.faculty_id,
        )
    ))
    if not candidates:
        return []

    candidate_ids = {candidate.id for candidate in candidates}
    day_number = absence.date.weekday()
    busy_timetable = set(session.execute(
        select(Timetable.faculty_id, Timetable.period_no).where(
            Timetable.faculty_id.in_(candidate_ids),
            Timetable.day_of_week == day_number,
        )
    ))
    busy_absences = set(session.scalars(
        select(Absence.faculty_id).where(
            Absence.faculty_id.in_(candidate_ids),
            Absence.date == absence.date,
            Absence.period_no == absence.period_no,
        )
    ))
    active_substitutions = set(session.scalars(
        select(Substitution.substitute_id).where(
            Substitution.substitute_id.in_(candidate_ids),
            Substitution.date == absence.date,
            Substitution.period_no == absence.period_no,
            Substitution.status.in_(("pending", "accepted")),
        )
    ))
    prior_candidates = set(session.scalars(
        select(Substitution.substitute_id).where(Substitution.absence_id == absence.id)
    ))
    busy_ids = busy_absences | active_substitutions
    busy_slots = {(faculty_id, period) for faculty_id, period in busy_timetable}
    eligible = [
        candidate for candidate in candidates
        if candidate.id not in busy_ids
        and candidate.id not in prior_candidates
        and (candidate.id, absence.period_no) not in busy_slots
    ]
    if not eligible:
        return []

    eligible_ids = {candidate.id for candidate in eligible}
    qualifications_by_faculty: dict[int, set[int]] = {faculty_id: set() for faculty_id in eligible_ids}
    departments_by_subject: dict[int, str] = {}
    for faculty_id, subject_id, department in session.execute(
        select(FacultySubject.faculty_id, Subject.id, Subject.department)
        .join(Subject, Subject.id == FacultySubject.subject_id)
        .where(FacultySubject.faculty_id.in_(eligible_ids))
    ):
        qualifications_by_faculty[faculty_id].add(subject_id)
        departments_by_subject[subject_id] = department

    qualified_subject_ids = set(departments_by_subject)
    same_semester_ids = set(session.scalars(
        select(FacultyAllocation.faculty_id).where(
            FacultyAllocation.faculty_id.in_(eligible_ids),
            FacultyAllocation.semester == section.semester,
        ).distinct()
    ))
    first_day, following_month = _month_bounds(absence.date)
    monthly_counts: dict[int, int] = {
        faculty_id: int(count)
        for faculty_id, count in session.execute(
            select(Substitution.substitute_id, func.count(Substitution.id))
            .where(
                Substitution.substitute_id.in_(eligible_ids),
                Substitution.status == "accepted",
                Substitution.date >= first_day,
                Substitution.date < following_month,
            )
            .group_by(Substitution.substitute_id)
        ).all()
    }

    busy_periods: dict[int, set[int]] = {faculty_id: set() for faculty_id in eligible_ids}
    for faculty_id, period in busy_timetable:
        if faculty_id in busy_periods:
            busy_periods[faculty_id].add(period)
    neighbor_substitutions = session.execute(
        select(Substitution.substitute_id, Substitution.period_no).where(
            Substitution.substitute_id.in_(eligible_ids),
            Substitution.date == absence.date,
            Substitution.status.in_(("pending", "accepted")),
        )
    )
    for faculty_id, period in neighbor_substitutions:
        busy_periods[faculty_id].add(period)

    max_period = 4 if day_number == 5 else settings.max_period
    highest_monthly_count = max((monthly_counts.get(candidate.id, 0) for candidate in eligible), default=0)
    features = []
    for candidate in eligible:
        candidate_subjects = qualifications_by_faculty[candidate.id]
        same_subject = timetable.subject_id in candidate_subjects
        related_subject = any(
            departments_by_subject.get(subject_id) == subject.department
            for subject_id in candidate_subjects & qualified_subject_ids
        )
        count = int(monthly_counts.get(candidate.id, 0))
        features.append(CandidateFeatures(
            faculty_id=candidate.id,
            name=candidate.name,
            email=candidate.email,
            subject_match=subject_match_score(same_subject, related_subject),
            adjacent_free=adjacent_free_score(
                absence.period_no,
                max_period,
                busy_periods[candidate.id],
                settings.break_periods,
            ),
            fairness=fairness_score(count, highest_monthly_count),
            same_semester=1.0 if candidate.id in same_semester_ids else 0.0,
            same_department=1.0 if candidate.department == subject.department else 0.0,
            monthly_substitutions=count,
        ))
    return rank_candidates(features)[:3]
