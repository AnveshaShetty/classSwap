from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Absence, Leave, Timetable, User


class AbsenceSelectionError(ValueError):
    pass


class AbsenceConflict(ValueError):
    pass


class AbsenceNotFound(LookupError):
    pass


def _create_absences(
    session: Session,
    faculty_id: int,
    absence_date: date,
    periods: list[int],
    reason: str,
) -> list[Absence]:
    if absence_date.weekday() == 6:
        raise AbsenceSelectionError("Absences cannot be marked on Sunday.")
    if not periods or len(set(periods)) != len(periods):
        raise AbsenceSelectionError("Select one or more distinct periods.")
    if any(period < 1 or period > 7 for period in periods):
        raise AbsenceSelectionError("Periods must be between 1 and 7.")
    if not reason.strip():
        raise AbsenceSelectionError("Please provide a reason for the absence.")
    if session.get(Leave, (faculty_id, absence_date)) is not None:
        raise AbsenceConflict("A whole-day leave is already recorded for this date.")

    scheduled_classes = list(session.scalars(
        select(Timetable).where(
            Timetable.faculty_id == faculty_id,
            Timetable.day_of_week == absence_date.weekday(),
            Timetable.period_no.in_(periods),
        )
    ))
    scheduled_periods = {row.period_no for row in scheduled_classes}
    missing_periods = sorted(set(periods) - scheduled_periods)
    if missing_periods:
        raise AbsenceSelectionError(
            "You do not have a scheduled class in period(s): %s."
            % ", ".join(str(period) for period in missing_periods)
        )

    existing_periods = set(session.scalars(
        select(Absence.period_no).where(
            Absence.faculty_id == faculty_id,
            Absence.date == absence_date,
            Absence.period_no.in_(periods),
        )
    ))
    duplicate_periods = sorted(existing_periods.intersection(periods))
    if duplicate_periods:
        raise AbsenceConflict(
            "An absence is already recorded for period(s): %s."
            % ", ".join(str(period) for period in duplicate_periods)
        )

    absences = [
        Absence(
            timetable_id=scheduled_class.id,
            faculty_id=faculty_id,
            date=absence_date,
            period_no=scheduled_class.period_no,
            reason=reason.strip(),
        )
        for scheduled_class in scheduled_classes
    ]
    session.add_all(absences)
    session.flush()
    return absences


def mark_absence(
    session: Session,
    faculty: User,
    absence_date: date,
    periods: list[int],
    reason: str,
) -> list[Absence]:
    if not faculty.teaches:
        raise AbsenceSelectionError("This account is not eligible to mark teaching absences.")
    if absence_date < date.today() and faculty.role != "super_admin":
        raise AbsenceSelectionError("Past absences require a full administrator.")
    if session.in_transaction():
        with session.begin_nested():
            absences = _create_absences(session, faculty.id, absence_date, periods, reason)
        session.commit()
        return absences

    with session.begin():
        return _create_absences(session, faculty.id, absence_date, periods, reason)


def get_absence(session: Session, absence_id: int) -> Absence:
    absence = session.get(Absence, absence_id)
    if absence is None:
        raise AbsenceNotFound("Absence not found.")
    return absence
