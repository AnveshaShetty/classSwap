from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Absence, AuditLog, Room, Section, Subject, Substitution, Timetable, User
from app.services.suggestion import Suggestion, suggest_candidates


class SubstitutionNotFound(LookupError):
    pass


class SubstitutionForbidden(PermissionError):
    pass


class SubstitutionConflict(ValueError):
    pass


Result = TypeVar("Result")


def _get_absence(session: Session, absence_id: int, lock: bool = False) -> Absence:
    statement = select(Absence).where(Absence.id == absence_id)
    if lock:
        statement = statement.with_for_update()
    absence = session.scalar(statement)
    if absence is None:
        raise SubstitutionNotFound("Absence not found.")
    return absence


def _check_candidate_slot(
    session: Session,
    absence: Absence,
    candidate_id: int,
    current_substitution_id: int | None = None,
) -> None:
    candidate = session.get(User, candidate_id)
    if candidate is None or not candidate.teaches or candidate_id == absence.faculty_id:
        raise SubstitutionConflict("This faculty member cannot cover the absence.")

    day_number = absence.date.weekday()
    has_class = session.scalar(
        select(Timetable.id).where(
            Timetable.faculty_id == candidate_id,
            Timetable.day_of_week == day_number,
            Timetable.period_no == absence.period_no,
        ).limit(1)
    )
    has_absence = session.scalar(
        select(Absence.id).where(
            Absence.faculty_id == candidate_id,
            Absence.date == absence.date,
            Absence.period_no == absence.period_no,
        ).limit(1)
    )
    active_statement = select(Substitution.id).where(
        Substitution.substitute_id == candidate_id,
        Substitution.date == absence.date,
        Substitution.period_no == absence.period_no,
        Substitution.status.in_(("pending", "accepted")),
    )
    if current_substitution_id is not None:
        active_statement = active_statement.where(Substitution.id != current_substitution_id)
    has_active_substitution = session.scalar(active_statement.limit(1))
    if has_class or has_absence or has_active_substitution:
        raise SubstitutionConflict("This faculty member is no longer free in that period.")


def _create_request(
    session: Session,
    absence_id: int,
    substitute_id: int,
    requester_id: int,
    enforce_owner: bool = True,
) -> Substitution:
    absence = _get_absence(session, absence_id, lock=True)
    if enforce_owner and absence.faculty_id != requester_id:
        raise SubstitutionForbidden("Only the absent faculty member can request a substitute.")
    already_covered = session.scalar(
        select(Substitution.id).where(
            Substitution.absence_id == absence_id,
            Substitution.status.in_(("pending", "accepted")),
        ).limit(1)
    )
    if already_covered:
        raise SubstitutionConflict("This absence already has an active substitution request.")

    suggestions = suggest_candidates(session, absence_id)
    if substitute_id not in {suggestion.faculty_id for suggestion in suggestions}:
        raise SubstitutionConflict("Choose one of the currently eligible suggested substitutes.")
    _check_candidate_slot(session, absence, substitute_id)
    timetable = session.get(Timetable, absence.timetable_id)
    if timetable is None:
        raise SubstitutionConflict("The absence is not linked to a timetable class.")
    request = Substitution(
        absence_id=absence.id,
        substitute_id=substitute_id,
        room_id=timetable.room_id,
        date=absence.date,
        period_no=absence.period_no,
        status="pending",
    )
    session.add(request)
    session.flush()
    return request


def _run_transaction(session: Session, action: Callable[[], Result]) -> Result:
    try:
        if session.in_transaction():
            with session.begin_nested():
                result = action()
            session.commit()
            return result
        with session.begin():
            return action()
    except IntegrityError as error:
        session.rollback()
        raise SubstitutionConflict("A scheduling clash occurred; refresh and try again.") from error


def create_substitution(
    session: Session,
    absence_id: int,
    substitute_id: int,
    requester_id: int,
) -> Substitution:
    return _run_transaction(
        session,
        lambda: _create_request(session, absence_id, substitute_id, requester_id),
    )


def auto_request_for_hod_absence(session: Session, absence: Absence) -> Substitution | None:
    suggestions = suggest_candidates(session, absence.id)
    if not suggestions:
        return None
    def create_auto_request() -> Substitution:
        request = _create_request(
            session,
            absence.id,
            suggestions[0].faculty_id,
            absence.faculty_id,
            enforce_owner=False,
        )
        session.add(AuditLog(
            user_id=absence.faculty_id,
            acting_as="hod",
            action="substitution.auto_requested",
            target="absence:%d substitute:%d" % (absence.id, request.substitute_id),
        ))
        session.flush()
        return request

    return _run_transaction(session, create_auto_request)


def _offer_next_candidate(session: Session, absence: Absence) -> Substitution | None:
    suggestions: list[Suggestion] = suggest_candidates(session, absence.id)
    for candidate in suggestions:
        try:
            return _create_request(
                session,
                absence.id,
                candidate.faculty_id,
                absence.faculty_id,
                enforce_owner=False,
            )
        except SubstitutionConflict:
            continue
    return None


def _transition(
    session: Session,
    substitution_id: int,
    actor_id: int,
    target_status: str,
) -> tuple[Substitution, Substitution | None]:
    substitution = session.scalar(
        select(Substitution)
        .where(Substitution.id == substitution_id)
        .with_for_update()
    )
    if substitution is None:
        raise SubstitutionNotFound("Substitution request not found.")
    if substitution.substitute_id != actor_id:
        raise SubstitutionForbidden("Only the assigned substitute can respond to this request.")
    if substitution.status != "pending":
        raise SubstitutionConflict("This request is no longer pending.")

    absence = _get_absence(session, substitution.absence_id, lock=True)
    if target_status == "accepted":
        _check_candidate_slot(session, absence, actor_id, substitution.id)
    substitution.status = target_status
    substitution.responded_at = datetime.now(timezone.utc)
    session.flush()
    next_request = _offer_next_candidate(session, absence) if target_status == "declined" else None
    return substitution, next_request


def respond_to_substitution(
    session: Session,
    substitution_id: int,
    actor_id: int,
    target_status: str,
) -> tuple[Substitution, Substitution | None]:
    return _run_transaction(
        session,
        lambda: _transition(session, substitution_id, actor_id, target_status),
    )


def expire_substitution(session: Session, substitution_id: int) -> Substitution | None:
    def expire() -> tuple[Substitution, Substitution | None]:
        substitution = session.scalar(
            select(Substitution)
            .where(Substitution.id == substitution_id)
            .with_for_update()
        )
        if substitution is None:
            raise SubstitutionNotFound("Substitution request not found.")
        if substitution.status != "pending":
            raise SubstitutionConflict("Only pending requests can expire.")
        absence = _get_absence(session, substitution.absence_id, lock=True)
        substitution.status = "expired"
        substitution.responded_at = datetime.now(timezone.utc)
        session.flush()
        return substitution, _offer_next_candidate(session, absence)

    _, next_request = _run_transaction(session, expire)
    return next_request


def get_inbox(session: Session, faculty_id: int) -> list[dict[str, object]]:
    rows = session.execute(
        select(Substitution, User.name, Subject.name, Section.name)
        .join(Absence, Absence.id == Substitution.absence_id)
        .join(User, User.id == Absence.faculty_id)
        .join(Timetable, Timetable.id == Absence.timetable_id)
        .join(Subject, Subject.id == Timetable.subject_id)
        .join(Section, Section.id == Timetable.section_id)
        .where(
            Substitution.substitute_id == faculty_id,
            Substitution.status == "pending",
        )
        .order_by(Substitution.created_at, Substitution.id)
    )
    return [
        {
            "substitution": substitution,
            "absent_faculty": absent_name,
            "subject": subject_name,
            "section": section_name,
        }
        for substitution, absent_name, subject_name, section_name in rows
    ]


def find_free_rooms(session: Session, absence_id: int) -> list[Room]:
    absence = _get_absence(session, absence_id)
    timetable = session.get(Timetable, absence.timetable_id)
    section = session.get(Section, timetable.section_id) if timetable is not None else None
    subject = session.get(Subject, timetable.subject_id) if timetable is not None else None
    if timetable is None or section is None or subject is None:
        raise SubstitutionConflict("The absence is not linked to a complete timetable class.")

    busy_room_ids = select(Timetable.room_id).where(
        Timetable.day_of_week == absence.date.weekday(),
        Timetable.period_no == absence.period_no,
    )
    active_room_ids = select(Substitution.room_id).where(
        Substitution.date == absence.date,
        Substitution.period_no == absence.period_no,
        Substitution.status.in_(("pending", "accepted")),
    )
    return list(session.scalars(
        select(Room).where(
            Room.type == ("lab" if subject.kind == "lab" else "class"),
            Room.capacity >= section.strength,
            Room.id.not_in(busy_room_ids),
            Room.id.not_in(active_room_ids),
        ).order_by(Room.name)
    ))
