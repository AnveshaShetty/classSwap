import re
from collections.abc import Callable
from datetime import date
import secrets
from typing import TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.authorization import can_access_department
from app.core.audit import append_audit
from app.models import (
    Absence,
    AdminChain,
    FacultyAllocation,
    FacultySubject,
    Leave,
    PasswordResetToken,
    Substitution,
    Timetable,
    TotpBackupCode,
    User,
)
from app.core.security import hash_password
from app.services.substitution import auto_request_for_hod_absence


class AdminNotFound(LookupError):
    pass


class AdminConflict(ValueError):
    pass


Result = TypeVar("Result")


def _position_order(position: str) -> tuple[int, object]:
    normalized = position.strip().casefold()
    if normalized == "hod":
        return (0, 0)
    senior = re.fullmatch(r"senior faculty\s*(\d+)", normalized)
    if senior:
        return (1, int(senior.group(1)))
    if normalized == "principal":
        return (3, 0)
    return (2, normalized)


def get_acting_admin(
    session: Session,
    department: str,
    on_date: date | None = None,
) -> tuple[User, str]:
    acting_date = on_date or date.today()
    chain = list(session.execute(
        select(AdminChain, User)
        .join(User, User.id == AdminChain.user_id)
        .where(AdminChain.department == department)
    ))
    chain.sort(key=lambda entry: _position_order(entry[0].position))
    on_leave = set(session.scalars(
        select(Leave.user_id).where(
            Leave.date == acting_date,
            Leave.user_id.in_(user.id for _, user in chain),
        )
    )) if chain else set()

    for chain_entry, user in chain:
        if user.id not in on_leave:
            return user, chain_entry.position

    super_admin = session.scalar(
        select(User).where(User.role == "super_admin").order_by(User.id).limit(1)
    )
    if super_admin is None:
        raise AdminNotFound("No super administrator is configured.")
    return super_admin, "Super admin fallback"


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
        raise AdminConflict("The admin or leave record conflicts with existing data.") from error


def _audit(session: Session, actor: User, action: str, target: str) -> None:
    append_audit(session, actor, action, target)


def read_admin_chain(session: Session, department: str) -> list[tuple[AdminChain, User]]:
    entries = [
        (chain_entry, user)
        for chain_entry, user in session.execute(
        select(AdminChain, User)
        .join(User, User.id == AdminChain.user_id)
        .where(AdminChain.department == department)
        )
    ]
    entries.sort(key=lambda entry: _position_order(entry[0].position))
    return entries


def replace_admin_chain(
    session: Session,
    actor: User,
    department: str,
    entries: list[tuple[str, str]],
) -> list[tuple[AdminChain, User]]:
    if not department.strip():
        raise AdminConflict("Department is required.")
    positions = [position.strip() for position, _ in entries]
    emails = [email.strip().lower() for _, email in entries]
    if any(not position for position in positions):
        raise AdminConflict("Every chain entry needs a position.")
    if len(set(positions)) != len(positions) or len(set(emails)) != len(emails):
        raise AdminConflict("Positions and faculty emails must be unique.")

    def replace() -> list[tuple[AdminChain, User]]:
        if not can_access_department(actor, department):
            raise AdminConflict("You can only edit the admin chain for your department.")
        users_by_email = {
            user.email: user
            for user in session.scalars(select(User).where(User.email.in_(emails)))
        } if emails else {}
        missing = [email for email in emails if email not in users_by_email]
        if missing:
            raise AdminConflict("Unknown faculty email(s): %s." % ", ".join(missing))
        invalid_department = [
            user.email for user in users_by_email.values()
            if user.department != department and user.role != "super_admin"
        ]
        if invalid_department:
            raise AdminConflict("Chain members must belong to the selected department.")

        session.execute(delete(AdminChain).where(AdminChain.department == department))
        for position, email in zip(positions, emails):
            session.add(AdminChain(
                department=department,
                position=position,
                user_id=users_by_email[email].id,
            ))
        _audit(
            session,
            actor,
            "admin_chain.updated",
            "%s: %s" % (department, ", ".join(positions)),
        )
        session.flush()
        return read_admin_chain(session, department)

    return _run_transaction(session, replace)


def create_whole_day_leave(
    session: Session,
    faculty: User,
    leave_date: date,
    reason: str,
) -> tuple[Leave, int]:
    if leave_date < date.today() and faculty.role != "super_admin":
        raise AdminConflict("Past leave requires a full administrator.")
    if leave_date.weekday() == 6:
        raise AdminConflict("Whole-day leave cannot be marked on Sunday.")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise AdminConflict("Please provide a reason for the leave.")

    def create() -> tuple[Leave, int]:
        existing_leave = session.get(Leave, (faculty.id, leave_date))
        if existing_leave is not None:
            raise AdminConflict("Whole-day leave is already recorded for this date.")
        scheduled = list(session.scalars(
            select(Timetable).where(
                Timetable.faculty_id == faculty.id,
                Timetable.day_of_week == leave_date.weekday(),
            )
        ))
        existing_absences = set(session.scalars(
            select(Absence.period_no).where(
                Absence.faculty_id == faculty.id,
                Absence.date == leave_date,
            )
        ))
        if existing_absences:
            raise AdminConflict("An absence is already recorded for this date.")

        leave = Leave(user_id=faculty.id, date=leave_date)
        session.add(leave)
        session.flush()
        for scheduled_class in scheduled:
            session.add(Absence(
                timetable_id=scheduled_class.id,
                faculty_id=faculty.id,
                date=leave_date,
                period_no=scheduled_class.period_no,
                reason=normalized_reason,
            ))
        _audit(session, faculty, "leave.created", "user:%d on %s" % (faculty.id, leave_date))
        session.flush()
        return leave, len(scheduled)

    leave, absence_count = _run_transaction(session, create)
    if faculty.role == "hod":
        for absence in session.scalars(
            select(Absence).where(
                Absence.faculty_id == faculty.id,
                Absence.date == leave_date,
            )
        ):
            auto_request_for_hod_absence(session, absence)
    return leave, absence_count


def cancel_whole_day_leave(session: Session, faculty: User, leave_date: date) -> None:
    def cancel() -> None:
        leave = session.get(Leave, (faculty.id, leave_date))
        if leave is None:
            return
        absence_ids = list(session.scalars(
            select(Absence.id).where(
                Absence.faculty_id == faculty.id,
                Absence.date == leave_date,
            )
        ))
        if absence_ids:
            session.execute(
                delete(Substitution).where(Substitution.absence_id.in_(absence_ids))
            )
            session.execute(delete(Absence).where(Absence.id.in_(absence_ids)))
        session.delete(leave)
        _audit(session, faculty, "leave.cancelled", "user:%d on %s" % (faculty.id, leave_date))
        session.flush()

    _run_transaction(session, cancel)


def anonymize_user(session: Session, actor: User, user_id: int) -> User:
    def anonymize() -> User:
        target = session.scalar(select(User).where(User.id == user_id).with_for_update())
        if target is None:
            raise AdminNotFound("User not found.")
        if target.id == actor.id:
            raise AdminConflict("You cannot anonymize your own account.")
        if target.role == "super_admin":
            administrator_count = session.scalar(
                select(func.count()).select_from(User).where(User.role == "super_admin")
            ) or 0
            if administrator_count <= 1:
                raise AdminConflict("The last super administrator cannot be anonymized.")

        session.execute(delete(AdminChain).where(AdminChain.user_id == target.id))
        session.execute(delete(FacultyAllocation).where(FacultyAllocation.faculty_id == target.id))
        session.execute(delete(FacultySubject).where(FacultySubject.faculty_id == target.id))
        session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == target.id))
        session.execute(delete(TotpBackupCode).where(TotpBackupCode.user_id == target.id))
        target.name = "Deleted user %d" % target.id
        target.email = "anonymized-%d-%s@invalid.example" % (target.id, secrets.token_hex(8))
        target.department = "Deleted"
        target.password_hash = hash_password(secrets.token_urlsafe(32))
        target.role = "faculty"
        target.teaches = False
        target.must_change_password = True
        target.token_version += 1
        target.totp_secret_encrypted = None
        target.totp_pending_secret_encrypted = None
        target.totp_enabled = False
        append_audit(session, actor, "user.anonymized", "user:%d" % target.id)
        session.flush()
        return target

    return _run_transaction(session, anonymize)
