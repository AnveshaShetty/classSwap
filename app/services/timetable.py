from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    Absence,
    FacultySubject,
    Room,
    Section,
    Subject,
    Substitution,
    Timetable,
    User,
)


CSV_COLUMNS = ("section", "day", "period", "subject", "faculty_email", "room")
DAY_NUMBERS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5}
DAY_NAMES = tuple(DAY_NUMBERS)
PERIODS_PER_DAY = {day: (4 if day == "Sat" else 7) for day in DAY_NAMES}


@dataclass(frozen=True)
class TimetableRow:
    row_number: int
    section: Section
    day: str
    period: int
    subject: Subject
    faculty: User
    room: Room

    @property
    def slot(self) -> tuple[int, int, int]:
        return (self.section.id, DAY_NUMBERS[self.day], self.period)


class TimetableCsvError(ValueError):
    def __init__(self, errors: list[dict[str, int | str]]) -> None:
        super().__init__("The timetable CSV contains invalid rows.")
        self.errors = errors


class TimetableHistoryConflict(ValueError):
    def __init__(self, errors: list[dict[str, int | str]]) -> None:
        super().__init__("The import would change timetable rows referenced by absence history.")
        self.errors = errors


def parse_timetable_csv(content: bytes) -> pd.DataFrame:
    try:
        frame = pd.read_csv(
            BytesIO(content),
            encoding="utf-8-sig",
            dtype=str,
            keep_default_na=False,
        )
    except (UnicodeDecodeError, pd.errors.EmptyDataError, pd.errors.ParserError) as error:
        raise TimetableCsvError([{"row": 1, "message": "Could not read the CSV file."}]) from error

    if tuple(frame.columns) != CSV_COLUMNS:
        raise TimetableCsvError([{
            "row": 1,
            "message": "Header must be: " + ",".join(CSV_COLUMNS),
        }])
    if frame.empty:
        raise TimetableCsvError([{"row": 1, "message": "The CSV has no timetable rows."}])
    return frame


def _validate_rows(session: Session, frame: pd.DataFrame) -> list[TimetableRow]:
    sections = {section.name: section for section in session.scalars(select(Section))}
    subjects = {subject.name: subject for subject in session.scalars(select(Subject))}
    faculty = {person.email.lower(): person for person in session.scalars(select(User))}
    rooms = {room.name: room for room in session.scalars(select(Room))}
    qualifications = set(session.execute(select(FacultySubject.faculty_id, FacultySubject.subject_id)))
    validated: list[TimetableRow] = []
    errors: list[dict[str, int | str]] = []
    section_slots: dict[tuple[int, str, int], int] = {}
    faculty_slots: dict[tuple[int, int], int] = {}
    room_slots: dict[tuple[int, int], int] = {}

    for offset, raw in enumerate(frame.to_dict(orient="records"), start=2):
        row_errors: list[str] = []
        section_name = raw["section"].strip()
        day = raw["day"].strip()
        subject_name = raw["subject"].strip()
        faculty_email = raw["faculty_email"].strip().lower()
        room_name = raw["room"].strip()
        section = sections.get(section_name)
        subject = subjects.get(subject_name)
        person = faculty.get(faculty_email)
        room = rooms.get(room_name)
        if section is None:
            row_errors.append("Unknown section '%s'." % section_name)
        if subject is None:
            row_errors.append("Unknown subject '%s'." % subject_name)
        if person is None:
            row_errors.append("Unknown faculty email '%s'." % faculty_email)
        if room is None:
            row_errors.append("Unknown room '%s'." % room_name)
        if day not in DAY_NUMBERS:
            row_errors.append("Day must be Mon, Tue, Wed, Thu, Fri, or Sat.")

        period: int | None
        try:
            period = int(raw["period"].strip())
        except ValueError:
            period = None
            row_errors.append("Period must be an integer.")
        if period is not None and day in PERIODS_PER_DAY:
            if not 1 <= period <= PERIODS_PER_DAY[day]:
                row_errors.append("Period is outside the available periods for %s." % day)

        if person is not None and not person.teaches:
            row_errors.append("This user is not eligible to teach.")
        if person is not None and subject is not None:
            if (person.id, subject.id) not in qualifications:
                row_errors.append("Faculty member is not qualified for this subject.")
        if room is not None and section is not None and room.capacity < section.strength:
            row_errors.append("Room capacity is below the section strength.")
        if room is not None and subject is not None:
            expected_room_type = "lab" if subject.kind == "lab" else "class"
            if room.type != expected_room_type:
                row_errors.append("Room type does not match the subject kind.")

        if period is not None and day in DAY_NUMBERS:
            day_number = DAY_NUMBERS[day]
            if section is not None:
                key = (section.id, day, period)
                previous = section_slots.get(key)
                if previous is not None:
                    row_errors.append("Section period conflicts with CSV row %d." % previous)
                else:
                    section_slots[key] = offset
            if person is not None:
                key = (person.id, day_number, period)
                previous = faculty_slots.get(key)
                if previous is not None:
                    row_errors.append("Faculty period conflicts with CSV row %d." % previous)
                else:
                    faculty_slots[key] = offset
            if room is not None:
                key = (room.id, day_number, period)
                previous = room_slots.get(key)
                if previous is not None:
                    row_errors.append("Room period conflicts with CSV row %d." % previous)
                else:
                    room_slots[key] = offset

        if row_errors:
            errors.extend({"row": offset, "message": message} for message in row_errors)
        elif section is not None and subject is not None and person is not None and room is not None and period is not None:
            validated.append(TimetableRow(offset, section, day, period, subject, person, room))

    if errors:
        raise TimetableCsvError(errors)
    return validated


def _import_in_transaction(session: Session, content: bytes) -> int:
    frame = parse_timetable_csv(content)
    rows = _validate_rows(session, frame)
    incoming_by_slot = {row.slot: row for row in rows}

    existing_rows = list(session.scalars(select(Timetable)))
    referenced_ids = set(session.scalars(select(Absence.timetable_id).distinct()))
    history_errors: list[dict[str, int | str]] = []
    preserved_slots: set[tuple[int, int, int]] = set()

    for existing in existing_rows:
        if existing.id not in referenced_ids:
            continue
        slot = (existing.section_id, existing.day_of_week, existing.period_no)
        replacement = incoming_by_slot.get(slot)
        if replacement is None:
            history_errors.append({
                "row": 1,
                "message": "Cannot remove section/day/period %s because absence history references it." % (slot,),
            })
            continue
        if (
            replacement.subject.id != existing.subject_id
            or replacement.faculty.id != existing.faculty_id
            or replacement.room.id != existing.room_id
        ):
            history_errors.append({
                "row": replacement.row_number,
                "message": "Cannot change this timetable row because absence history references it.",
            })
        else:
            preserved_slots.add(slot)
    if history_errors:
        raise TimetableHistoryConflict(history_errors)

    removable_ids = [row.id for row in existing_rows if row.id not in referenced_ids]
    if removable_ids:
        session.execute(delete(Timetable).where(Timetable.id.in_(removable_ids)))
        session.flush()

    for row in rows:
        if row.slot in preserved_slots:
            continue
        session.add(Timetable(
            section_id=row.section.id,
            subject_id=row.subject.id,
            faculty_id=row.faculty.id,
            room_id=row.room.id,
            day_of_week=DAY_NUMBERS[row.day],
            period_no=row.period,
        ))
    session.flush()
    return len(rows)


def import_timetable_csv(session: Session, content: bytes) -> int:
    if session.in_transaction():
        with session.begin_nested():
            imported_rows = _import_in_transaction(session, content)
        session.commit()
        return imported_rows

    with session.begin():
        return _import_in_transaction(session, content)


def build_timetable_grid(
    session: Session,
    selected_date: date,
    section_name: str | None = None,
    faculty_email: str | None = None,
) -> dict[str, object]:
    statement = (
        select(Timetable, Section, Subject, User, Room)
        .join(Section, Timetable.section_id == Section.id)
        .join(Subject, Timetable.subject_id == Subject.id)
        .join(User, Timetable.faculty_id == User.id)
        .join(Room, Timetable.room_id == Room.id)
    )
    if section_name:
        statement = statement.where(Section.name == section_name)
    if faculty_email:
        statement = statement.where(User.email == faculty_email.strip().lower())

    accepted_substitutions = select(Absence.timetable_id).join(
        Substitution, Substitution.absence_id == Absence.id
    ).where(
        Substitution.date == selected_date,
        Substitution.status == "accepted",
    )
    covered_timetable_ids = set(session.scalars(accepted_substitutions))

    grid: dict[str, list[dict[str, object]]] = {
        day: [
            {"number": period, "entries": []}
            for period in range(1, PERIODS_PER_DAY[day] + 1)
        ]
        for day in DAY_NAMES
    }
    result_rows = session.execute(
        statement.order_by(Timetable.day_of_week, Timetable.period_no, Section.name)
    )
    for timetable, section, subject, person, room in result_rows:
        entry = {
            "section": section.name,
            "subject": subject.name,
            "faculty": person.name,
            "faculty_email": person.email,
            "room": room.name,
            "substituted": timetable.id in covered_timetable_ids,
        }
        periods = grid[DAY_NAMES[timetable.day_of_week]]
        periods[timetable.period_no - 1]["entries"].append(entry)

    return {
        "days": [
            {"name": day, "periods": grid[day]}
            for day in DAY_NAMES
        ],
        "sections": list(session.scalars(select(Section).order_by(Section.name))),
        "faculty": list(session.scalars(select(User).where(User.teaches.is_(True)).order_by(User.name))),
        "selected_date": selected_date,
        "selected_section": section_name or "",
        "selected_faculty": faculty_email or "",
    }
