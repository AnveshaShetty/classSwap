import csv
from collections import Counter
from datetime import date
from io import StringIO
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Absence, Section, Subject, Substitution, Timetable, User
from app.services.dashboard import _coverage
from app.services.dashboard import portrait_url


REPORT_COLUMNS = (
    "absence_id",
    "date",
    "department",
    "section",
    "semester",
    "subject",
    "absent_faculty",
    "period",
    "reason",
    "status",
    "substitute",
    "substitute_email",
)


def _month_bounds(month: date) -> tuple[date, date]:
    first = month.replace(day=1)
    if first.month == 12:
        following = first.replace(year=first.year + 1, month=1)
    else:
        following = first.replace(month=first.month + 1)
    return first, following


def build_monthly_report(
    session: Session,
    month: date,
    department: str | None,
) -> dict[str, Any]:
    first, following = _month_bounds(month)
    statement = (
        select(Absence, Section, Subject, User, Substitution)
        .join(Timetable, Timetable.id == Absence.timetable_id)
        .join(Section, Section.id == Timetable.section_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .join(User, User.id == Absence.faculty_id)
        .outerjoin(Substitution, Substitution.absence_id == Absence.id)
        .where(Absence.date >= first, Absence.date < following)
        .order_by(Absence.date, Absence.id, Substitution.id.desc())
    )
    if department:
        statement = statement.where(Subject.department == department)

    absence_rows: dict[int, dict[str, Any]] = {}
    substitutions: dict[int, list[Substitution]] = {}
    for absence, section, subject, absent_faculty, substitution in session.execute(statement):
        absence_rows[absence.id] = {
            "absence_id": absence.id,
            "date": absence.date.isoformat(),
            "department": subject.department,
            "section": section.name,
            "semester": section.semester,
            "subject": subject.name,
            "absent_faculty": absent_faculty.name,
            "period": absence.period_no,
            "reason": absence.reason,
        }
        substitutions.setdefault(absence.id, [])
        if substitution is not None:
            substitutions[absence.id].append(substitution)

    rows: list[dict[str, Any]] = []
    accepted_counts: Counter[int] = Counter()
    substitute_ids: set[int] = set()
    for absence_id, row in absence_rows.items():
        status, substitution = _coverage(substitutions[absence_id])
        substitute = session.get(User, substitution.substitute_id) if substitution else None
        row["status"] = status
        row["substitute"] = substitute.name if substitute else ""
        row["substitute_email"] = substitute.email if substitute else ""
        if status == "accepted" and substitute is not None:
            accepted_counts[substitute.id] += 1
            substitute_ids.add(substitute.id)
        rows.append(row)

    total = len(rows)
    covered = sum(row["status"] == "accepted" for row in rows)
    pending = sum(row["status"] == "pending" for row in rows)
    fairness = []
    if substitute_ids:
        for person in session.scalars(
            select(User).where(User.id.in_(substitute_ids)).order_by(User.name)
        ):
            fairness.append({
                "name": person.name,
                "email": person.email,
                "accepted": accepted_counts[person.id],
                "photo": portrait_url(person.email),
            })
        fairness.sort(key=lambda item: (item["accepted"], item["name"].casefold()))

    return {
        "month": first.strftime("%Y-%m"),
        "month_label": first.strftime("%B %Y"),
        "department": department,
        "rows": rows,
        "total_absences": total,
        "covered": covered,
        "pending": pending,
        "uncovered": total - covered - pending,
        "coverage_rate": round(covered * 100 / total) if total else None,
        "fairness": fairness,
    }


def render_monthly_csv(report: dict[str, Any]) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in report["rows"]:
        safe_row = {
            column: _spreadsheet_safe(str(row.get(column, "")))
            for column in REPORT_COLUMNS
        }
        writer.writerow(safe_row)
    return output.getvalue()


def _spreadsheet_safe(value: str) -> str:
    if value.startswith(("=", "+", "-", "@", "\t", "\r", "\n")) or value.lstrip(
        " \t\r\n"
    ).startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
