import csv
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from alembic import command
from alembic.config import Config
from passlib.context import CryptContext
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.database import Base, engine
from app.models import (
    Absence,
    AdminChain,
    FacultyAllocation,
    FacultySubject,
    Room,
    Section,
    Subject,
    Substitution,
    Timetable,
    User,
)


SEED_DIR = PROJECT_ROOT / "seed"
PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
DAY_NUMBERS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5}
COUNTED_MODELS = {
    "users": User,
    "subjects": Subject,
    "sections": Section,
    "rooms": Room,
    "faculty_subjects": FacultySubject,
    "faculty_allocations": FacultyAllocation,
    "timetable": Timetable,
    "absences": Absence,
    "substitutions": Substitution,
    "admin_chain": AdminChain,
}


def read_csv(seed_dir: Path, filename: str) -> list[dict[str, str]]:
    path = seed_dir / filename
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        return list(csv.DictReader(source))


def load_seed(session: Session, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    if session.scalar(select(User.id).limit(1)) is not None:
        raise ValueError("The database already contains users; refusing to seed duplicate data.")

    user_ids: dict[str, int] = {}
    for row in read_csv(seed_dir, "faculty.csv"):
        user = User(
            name=row["name"],
            email=row["email"].strip().lower(),
            password_hash=PASSWORD_CONTEXT.hash("demo123"),
            role=row["role"],
            department=row["department"],
            teaches=row["teaches"].strip().lower() == "true",
        )
        session.add(user)
        session.flush()
        user_ids[user.email] = user.id

    subject_ids: dict[str, int] = {}
    for row in read_csv(seed_dir, "subjects.csv"):
        subject = Subject(name=row["name"], department=row["department"], kind=row["kind"])
        session.add(subject)
        session.flush()
        subject_ids[subject.name] = subject.id

    section_ids: dict[str, int] = {}
    for row in read_csv(seed_dir, "sections.csv"):
        section = Section(
            name=row["name"],
            semester=int(row["semester"]),
            strength=int(row["strength"]),
        )
        session.add(section)
        session.flush()
        section_ids[section.name] = section.id

    room_ids: dict[str, int] = {}
    for row in read_csv(seed_dir, "rooms.csv"):
        room = Room(name=row["name"], type=row["type"], capacity=int(row["capacity"]))
        session.add(room)
        session.flush()
        room_ids[room.name] = room.id

    for row in read_csv(seed_dir, "faculty_subjects.csv"):
        session.add(FacultySubject(
            faculty_id=user_ids[row["faculty_email"].strip().lower()],
            subject_id=subject_ids[row["subject"]],
        ))

    for row in read_csv(seed_dir, "allocations.csv"):
        session.add(FacultyAllocation(
            faculty_id=user_ids[row["faculty_email"].strip().lower()],
            subject_id=subject_ids[row["subject"]],
            semester=int(row["semester"]),
            section_id=section_ids[row["section"]],
        ))

    timetable_by_slot: dict[tuple[str, int, int], Timetable] = {}
    timetable_rows = read_csv(seed_dir, "timetable.csv")
    for row in timetable_rows:
        day = row["day"]
        if day not in DAY_NUMBERS:
            raise ValueError("Unknown timetable day: %s" % day)
        timetable = Timetable(
            section_id=section_ids[row["section"]],
            subject_id=subject_ids[row["subject"]],
            faculty_id=user_ids[row["faculty_email"].strip().lower()],
            room_id=room_ids[row["room"]],
            day_of_week=DAY_NUMBERS[day],
            period_no=int(row["period"]),
        )
        session.add(timetable)
        timetable_by_slot[(row["section"], DAY_NUMBERS[day], int(row["period"]))] = timetable
    session.flush()

    for row in read_csv(seed_dir, "admin_chain.csv"):
        session.add(AdminChain(
            department=row["department"],
            position=row["position"],
            user_id=user_ids[row["email"].strip().lower()],
        ))

    absence_rows = read_csv(seed_dir, "absences.csv")
    absence_rows_by_id = {row["id"]: row for row in absence_rows}
    absence_ids: dict[str, int] = {}
    absence_timetables: dict[str, Timetable] = {}
    for row in absence_rows:
        absent_date = date.fromisoformat(row["date"])
        day_number = absent_date.weekday()
        timetable = timetable_by_slot.get((row["section"], day_number, int(row["period_no"])))
        if timetable is None or timetable.subject_id != subject_ids[row["subject"]] \
                or timetable.faculty_id != user_ids[row["faculty_email"].strip().lower()]:
            raise ValueError("Absence %s does not match the weekly timetable." % row["id"])
        absence = Absence(
            timetable_id=timetable.id,
            faculty_id=user_ids[row["faculty_email"].strip().lower()],
            date=absent_date,
            period_no=int(row["period_no"]),
            reason=row["reason"],
        )
        session.add(absence)
        session.flush()
        absence_ids[row["id"]] = absence.id
        absence_timetables[row["id"]] = timetable

    for row in read_csv(seed_dir, "substitutions.csv"):
        timetable = absence_timetables[row["absence_id"]]
        substitution_date = date.fromisoformat(row["date"])
        period_no = int(row["period_no"])
        absence_row = absence_rows_by_id[row["absence_id"]]
        if substitution_date.isoformat() != absence_row["date"] or period_no != int(absence_row["period_no"]):
            raise ValueError("Substitution %s does not match its absence." % row["absence_id"])
        session.add(Substitution(
            absence_id=absence_ids[row["absence_id"]],
            substitute_id=user_ids[row["substitute_email"].strip().lower()],
            room_id=timetable.room_id,
            date=substitution_date,
            period_no=period_no,
            status=row["status"].strip().lower(),
        ))

    session.flush()
    return {
        table_name: int(session.scalar(select(func.count()).select_from(model)) or 0)
        for table_name, model in COUNTED_MODELS.items()
    }


def seed_database(database_engine: Engine | None = None, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    target_engine = database_engine or engine
    if database_engine is None:
        alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
        command.upgrade(alembic_config, "head")
    else:
        Base.metadata.create_all(target_engine)

    with Session(target_engine, autoflush=False, expire_on_commit=False) as session:
        with session.begin():
            counts = load_seed(session, seed_dir)
    return counts


def main() -> None:
    counts = seed_database()
    for table_name, count in counts.items():
        print("%-20s %d" % (table_name, count))


if __name__ == "__main__":
    main()
