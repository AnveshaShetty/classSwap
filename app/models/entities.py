from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('faculty', 'hod', 'super_admin')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="faculty")
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    teaches: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        CheckConstraint("kind IN ('theory', 'lab')", name="ck_subjects_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, unique=True)
    department: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)


class FacultySubject(Base):
    __tablename__ = "faculty_subjects"

    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True)


class Section(Base):
    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    semester: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    strength: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class FacultyAllocation(Base):
    __tablename__ = "faculty_allocations"
    __table_args__ = (
        UniqueConstraint("faculty_id", "subject_id", "section_id", name="uq_faculty_allocation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    semester: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        CheckConstraint("type IN ('class', 'lab')", name="ck_rooms_type"),
        CheckConstraint("capacity > 0", name="ck_rooms_capacity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(10), nullable=False)
    capacity: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class Timetable(Base):
    __tablename__ = "timetable"
    __table_args__ = (
        UniqueConstraint("faculty_id", "day_of_week", "period_no", name="uq_timetable_faculty_slot"),
        UniqueConstraint("room_id", "day_of_week", "period_no", name="uq_timetable_room_slot"),
        UniqueConstraint("section_id", "day_of_week", "period_no", name="uq_timetable_section_slot"),
        CheckConstraint("day_of_week BETWEEN 0 AND 5", name="ck_timetable_day"),
        CheckConstraint("period_no BETWEEN 1 AND 7", name="ck_timetable_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    period_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class Absence(Base):
    __tablename__ = "absences"
    __table_args__ = (
        UniqueConstraint("faculty_id", "date", "period_no", name="uq_absence_faculty_date_period"),
        CheckConstraint("period_no BETWEEN 1 AND 7", name="ck_absences_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_id: Mapped[int] = mapped_column(ForeignKey("timetable.id"), nullable=False)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    period_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)


class Substitution(Base):
    __tablename__ = "substitutions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'accepted', 'declined', 'expired')",
            name="ck_substitutions_status",
        ),
        CheckConstraint("period_no BETWEEN 1 AND 7", name="ck_substitutions_period"),
        Index(
            "uq_substitutions_active_candidate_slot",
            "substitute_id",
            "date",
            "period_no",
            unique=True,
            postgresql_where=text("status IN ('pending', 'accepted')"),
            sqlite_where=text("status IN ('pending', 'accepted')"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    absence_id: Mapped[int] = mapped_column(ForeignKey("absences.id", ondelete="CASCADE"), nullable=False)
    substitute_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    period_no: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Leave(Base):
    __tablename__ = "leaves"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)


class AdminChain(Base):
    __tablename__ = "admin_chain"

    department: Mapped[str] = mapped_column(String(120), primary_key=True)
    position: Mapped[str] = mapped_column(String(80), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    acting_as: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
