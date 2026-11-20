from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import Base, get_db
from app.main import app
from app.models import Absence, Substitution, Timetable, User
from scripts.seed import load_seed


@pytest.fixture
def absence_context() -> Iterator[tuple[TestClient, Engine, User]]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        with session.begin():
            load_seed(session)
        faculty = session.scalar(select(User).where(User.email == "ravi.kulal@demo.edu"))
        assert faculty is not None
        current_faculty = User(
            id=faculty.id,
            name=faculty.name,
            email=faculty.email,
            password_hash=faculty.password_hash,
            role=faculty.role,
            department=faculty.department,
            teaches=faculty.teaches,
        )

    def override_get_db() -> Iterator[Session]:
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: current_faculty
    with TestClient(app) as client:
        yield client, test_engine, current_faculty
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_mark_absence_for_one_or_more_scheduled_periods(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, faculty = absence_context
    response = client.post(
        "/absences",
        json={"date": "2026-11-23", "periods": [3], "reason": "Medical leave"},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["faculty_id"] == faculty.id
    assert response.json()[0]["period_no"] == 3
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Absence)) == 21


def test_absence_with_unscheduled_period_creates_no_rows(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, _ = absence_context
    response = client.post(
        "/absences",
        json={"date": "2026-11-23", "periods": [3, 7], "reason": "Personal work"},
    )

    assert response.status_code == 422
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Absence)) == 20


def test_suggestions_exclude_teachers_busy_in_target_slot(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-23", "periods": [3], "reason": "Conference"},
    )
    assert created.status_code == 200

    response = client.get("/absences/%d/suggestions" % created.json()[0]["id"])

    assert response.status_code == 200
    assert 0 < len(response.json()) <= 3
    suggestion_ids = {candidate["faculty_id"] for candidate in response.json()}
    with Session(test_engine) as session:
        absent = session.get(Absence, created.json()[0]["id"])
        absent_class = session.get(Timetable, absent.timetable_id)
        busy_ids = set(session.scalars(
            select(Timetable.faculty_id).where(
                Timetable.day_of_week == date(2026, 11, 23).weekday(),
                Timetable.period_no == 3,
            )
        ))
        assert absent_class is not None
        assert absent.faculty_id not in suggestion_ids
        assert not suggestion_ids.intersection(busy_ids)


@pytest.mark.parametrize("status", ["pending", "accepted"])
def test_suggestions_exclude_active_substitutes_in_target_slot(
    absence_context: tuple[TestClient, Engine, User],
    status: str,
) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-23", "periods": [3], "reason": "Medical leave"},
    )
    assert created.status_code == 200

    with Session(test_engine) as session:
        absence = session.get(Absence, created.json()[0]["id"])
        historical_absence = session.scalar(
            select(Absence).where(Absence.id != created.json()[0]["id"]).limit(1)
        )
        assert absence is not None
        assert historical_absence is not None
        absence_class = session.get(Timetable, absence.timetable_id)
        assert absence_class is not None
        busy_faculty_ids = select(Timetable.faculty_id).where(
            Timetable.day_of_week == date(2026, 11, 23).weekday(),
            Timetable.period_no == 3,
        )
        substitute = session.scalar(
            select(User).where(
                User.teaches.is_(True),
                User.id != absence.faculty_id,
                ~User.id.in_(busy_faculty_ids),
            ).limit(1)
        )
        assert substitute is not None
        substitute_id = substitute.id
        session.add(Substitution(
            absence_id=historical_absence.id,
            substitute_id=substitute.id,
            room_id=absence_class.room_id,
            date=absence.date,
            period_no=absence.period_no,
            status=status,
        ))
        session.commit()

    response = client.get("/absences/%d/suggestions" % created.json()[0]["id"])

    assert response.status_code == 200
    assert substitute_id not in {candidate["faculty_id"] for candidate in response.json()}
