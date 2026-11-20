from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.models import User
from scripts.seed import PASSWORD_CONTEXT, seed_database


def test_seed_loads_all_csvs_in_dependency_order(tmp_path: Path) -> None:
    database_engine = create_engine("sqlite:///" + str(tmp_path / "seed.db"))

    counts = seed_database(database_engine)

    assert counts == {
        "users": 13,
        "subjects": 22,
        "sections": 5,
        "rooms": 12,
        "faculty_subjects": 36,
        "faculty_allocations": 38,
        "timetable": 119,
        "absences": 20,
        "substitutions": 20,
        "admin_chain": 4,
    }
    with Session(database_engine) as session:
        hod = session.scalar(select(User).where(User.email == "meera.shenoy@demo.edu"))
        faculty = session.scalar(select(User).where(User.email == "ravi.kulal@demo.edu"))
        assert hod is not None and hod.role == "hod"
        assert faculty is not None and faculty.role == "faculty"
        assert PASSWORD_CONTEXT.verify("demo123", hod.password_hash)
        assert PASSWORD_CONTEXT.verify("demo123", faculty.password_hash)

    database_engine.dispose()


def test_seed_refuses_duplicate_load_without_partial_changes(tmp_path: Path) -> None:
    database_engine = create_engine("sqlite:///" + str(tmp_path / "seed.db"))
    seed_database(database_engine)

    with pytest.raises(ValueError, match="already contains users"):
        seed_database(database_engine)

    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 13
    database_engine.dispose()
