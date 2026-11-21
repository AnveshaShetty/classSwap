from collections import Counter
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    AdminChain,
    Section,
    Subject,
    Substitution,
    Timetable,
    User,
)
from app.services.admin import AdminNotFound, get_acting_admin


def _month_bounds(target: date) -> tuple[date, date]:
    first = target.replace(day=1)
    if first.month == 12:
        following = first.replace(year=first.year + 1, month=1)
    else:
        following = first.replace(month=first.month + 1)
    return first, following


def _coverage(substitutions: list[Substitution]) -> tuple[str, Substitution | None]:
    accepted = next((row for row in substitutions if row.status == "accepted"), None)
    if accepted is not None:
        return "accepted", accepted
    pending = next((row for row in substitutions if row.status == "pending"), None)
    if pending is not None:
        return "pending", pending
    if substitutions:
        return substitutions[0].status, substitutions[0]
    return "unrequested", None


def build_dashboard_data(
    session: Session,
    target_date: date,
    department: str | None,
) -> dict[str, Any]:
    first_of_month, first_of_next_month = _month_bounds(target_date)
    absence_statement = (
        select(Absence, Section.name, Subject.name, User.name, Substitution)
        .join(Timetable, Timetable.id == Absence.timetable_id)
        .join(Section, Section.id == Timetable.section_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .join(User, User.id == Absence.faculty_id)
        .outerjoin(Substitution, Substitution.absence_id == Absence.id)
        .where(Absence.date == target_date)
        .order_by(Absence.id, Substitution.id.desc())
    )
    if department:
        absence_statement = absence_statement.where(Subject.department == department)

    absence_groups: dict[int, dict[str, Any]] = {}
    substitutions_by_absence: dict[int, list[Substitution]] = {}
    for absence, section_name, subject_name, faculty_name, substitution in session.execute(absence_statement):
        absence_groups[absence.id] = {
            "id": absence.id,
            "section": section_name,
            "subject": subject_name,
            "faculty": faculty_name,
            "period": absence.period_no,
            "reason": absence.reason,
        }
        substitutions_by_absence.setdefault(absence.id, [])
        if substitution is not None:
            substitutions_by_absence[absence.id].append(substitution)

    today_absences = []
    for absence_id, row in absence_groups.items():
        status, substitution = _coverage(substitutions_by_absence[absence_id])
        row["status"] = status
        row["substitute"] = None
        if substitution is not None:
            row["substitute"] = session.scalar(
                select(User.name).where(User.id == substitution.substitute_id)
            )
        today_absences.append(row)

    scope_statement = (
        select(Substitution)
        .join(Absence, Absence.id == Substitution.absence_id)
        .join(Timetable, Timetable.id == Absence.timetable_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .where(
            Substitution.status == "accepted",
            Substitution.date >= first_of_month,
            Substitution.date < first_of_next_month,
        )
    )
    pending_statement = (
        select(func.count(Substitution.id))
        .join(Absence, Absence.id == Substitution.absence_id)
        .join(Timetable, Timetable.id == Absence.timetable_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .where(Substitution.status == "pending")
    )
    if department:
        scope_statement = scope_statement.where(Subject.department == department)
        pending_statement = pending_statement.where(Subject.department == department)
    accepted_this_month = list(session.scalars(scope_statement))
    pending_count = int(session.scalar(pending_statement) or 0)

    accepted_counts = Counter(row.substitute_id for row in accepted_this_month)
    faculty_statement = select(User).where(User.teaches.is_(True))
    if department:
        faculty_statement = faculty_statement.where(
            or_(
                User.department == department,
                User.id.in_(accepted_counts.keys()),
            )
        )
    faculty = list(session.scalars(faculty_statement.order_by(User.name)))
    fairness = [
        {
            "name": person.name,
            "email": person.email,
            "department": person.department,
            "accepted": accepted_counts.get(person.id, 0),
        }
        for person in faculty
    ]
    fairness.sort(key=lambda item: (item["accepted"], item["name"].casefold()))

    trend_start = target_date - timedelta(days=6)
    trend_statement = (
        select(Substitution.date, func.count(Substitution.id))
        .join(Absence, Absence.id == Substitution.absence_id)
        .join(Timetable, Timetable.id == Absence.timetable_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .where(
            Substitution.status == "accepted",
            Substitution.date >= trend_start,
            Substitution.date <= target_date,
        )
        .group_by(Substitution.date)
    )
    if department:
        trend_statement = trend_statement.where(Subject.department == department)
    trend_counts = dict(session.execute(trend_statement).all())
    trend = [
        {
            "date": (trend_start + timedelta(days=index)).isoformat(),
            "label": (trend_start + timedelta(days=index)).strftime("%a"),
            "count": int(trend_counts.get(trend_start + timedelta(days=index), 0)),
        }
        for index in range(7)
    ]

    admin_department = department
    if admin_department is None:
        admin_department = session.scalar(
            select(AdminChain.department).order_by(AdminChain.department).limit(1)
        )
    acting_admin: dict[str, str] | None = None
    if admin_department:
        try:
            acting, position = get_acting_admin(session, admin_department, target_date)
            acting_admin = {
                "name": acting.name,
                "email": acting.email,
                "position": position,
                "department": admin_department,
            }
        except AdminNotFound:
            acting_admin = None

    total_today = len(today_absences)
    accepted_today = sum(row["status"] == "accepted" for row in today_absences)
    return {
        "department": department,
        "selected_date": target_date.isoformat(),
        "today_absences": today_absences,
        "absence_count": total_today,
        "covered_today": accepted_today,
        "coverage_rate": round(accepted_today * 100 / total_today) if total_today else None,
        "pending_requests": pending_count,
        "substitutions_this_month": len(accepted_this_month),
        "periods_recovered": len(accepted_this_month),
        "fairness": fairness,
        "coverage_trend": trend,
        "acting_admin": acting_admin,
    }
