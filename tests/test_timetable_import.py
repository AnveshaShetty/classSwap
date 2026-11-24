from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.config import settings
from app.core.totp import encrypt_totp_secret
from app.database import Base, get_db
from app.main import app
from app.models import Leave, Room, Section, Timetable, User
from scripts.seed import load_seed


@pytest.fixture
def timetable_context(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, Engine]]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        with session.begin():
            load_seed(session)

    def override_get_db() -> Iterator[Session]:
        with Session(test_engine) as session:
            yield session

    secret = pyotp.random_base32()
    monkeypatch.setattr(settings, "totp_encryption_key", Fernet.generate_key().decode("ascii"))
    with Session(test_engine) as session:
        admin_row = session.scalar(select(User).where(User.role == "super_admin"))
        assert admin_row is not None
        admin_row.totp_secret_encrypted = encrypt_totp_secret(secret)
        admin_row.totp_enabled = True
        admin = User(
            id=admin_row.id,
            name=admin_row.name,
            email=admin_row.email,
            password_hash=admin_row.password_hash,
            role=admin_row.role,
            department=admin_row.department,
            teaches=admin_row.teaches,
            totp_secret_encrypted=admin_row.totp_secret_encrypted,
            totp_enabled=True,
        )
        session.commit()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: admin
    with TestClient(app, base_url="https://testserver") as client:
        client.headers["X-TOTP-Code"] = pyotp.TOTP(secret).now()
        yield client, test_engine
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_invalid_csv_reports_row_and_imports_nothing(timetable_context: tuple[TestClient, Engine]) -> None:
    client, test_engine = timetable_context
    csv_path = Path(__file__).resolve().parents[1] / "seed" / "timetable.csv"
    content = csv_path.read_bytes() + (
        b"Missing,Mon,1,Data Structures and Algorithms,"
        b"arjun.kulkarni@demo.edu,CSD-3A\n"
    )

    response = client.post(
        "/timetable/import",
        files={"file": ("bad.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    errors = response.json()["detail"]["errors"]
    assert any(error["row"] == 121 and "Unknown section" in error["message"] for error in errors)
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Timetable)) == 119


def test_valid_csv_import_preserves_absence_history(timetable_context: tuple[TestClient, Engine]) -> None:
    client, test_engine = timetable_context
    csv_path = Path(__file__).resolve().parents[1] / "seed" / "timetable.csv"
    app.dependency_overrides.pop(get_current_user)
    login_response = client.post(
        "/auth/login",
        json={"email": "principal.demo@demo.edu", "password": "demo123"},
    )
    assert login_response.status_code == 200

    response = client.post(
        "/timetable/import",
        files={"file": ("timetable.csv", csv_path.read_bytes(), "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {"imported_rows": 119}
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Timetable)) == 119


def test_import_rejects_changes_to_absence_referenced_slots(timetable_context: tuple[TestClient, Engine]) -> None:
    client, test_engine = timetable_context
    csv_path = Path(__file__).resolve().parents[1] / "seed" / "timetable.csv"
    original = (
        "3A,Mon,1,Computer Organization and Architecture,"
        "kavya.menon@demo.edu,CSD-3A"
    )
    changed = original[:-len("CSD-3A")] + "Seminar-201"
    content = csv_path.read_text(encoding="utf-8").replace(original, changed, 1).encode("utf-8")

    response = client.post(
        "/timetable/import",
        files={"file": ("changed.csv", content, "text/csv")},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["errors"][0]["row"] == 2
    with Session(test_engine) as session:
        timetable_row = session.scalar(
            select(Timetable)
            .join(Section, Timetable.section_id == Section.id)
            .where(Section.name == "3A", Timetable.day_of_week == 0, Timetable.period_no == 1)
        )
        assert timetable_row is not None
        assert session.get(Room, timetable_row.room_id).name == "CSD-3A"


def test_weekly_grid_filters_and_marks_accepted_cover(timetable_context: tuple[TestClient, Engine]) -> None:
    client, _ = timetable_context

    response = client.get("/timetable?section=3A&date=2026-10-19")

    assert response.status_code == 200
    assert 'data-section="3A"' in response.text
    assert 'data-section="3B"' not in response.text
    assert "Substitute accepted" in response.text


def test_faculty_cannot_import_timetable(timetable_context: tuple[TestClient, Engine]) -> None:
    client, _ = timetable_context
    app.dependency_overrides[get_current_user] = lambda: User(
        id=2,
        name="Demo Faculty",
        email="ravi.kulal@demo.edu",
        password_hash="",
        role="faculty",
        department="Computer Science and Design",
        teaches=True,
    )
    csv_path = Path(__file__).resolve().parents[1] / "seed" / "timetable.csv"

    response = client.post(
        "/timetable/import",
        files={"file": ("timetable.csv", csv_path.read_bytes(), "text/csv")},
    )

    assert response.status_code == 403


def test_stand_in_admin_cannot_import_timetable(
    timetable_context: tuple[TestClient, Engine],
) -> None:
    client, test_engine = timetable_context
    with Session(test_engine) as session:
        hod = session.scalar(select(User).where(User.email == "meera.shenoy@demo.edu"))
        stand_in = session.scalar(select(User).where(User.email == "arjun.kulkarni@demo.edu"))
        assert hod is not None and stand_in is not None
        session.add(Leave(user_id=hod.id, date=date.today()))
        acting_user = User(
            id=stand_in.id,
            name=stand_in.name,
            email=stand_in.email,
            password_hash=stand_in.password_hash,
            role=stand_in.role,
            department=stand_in.department,
            teaches=stand_in.teaches,
        )
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: acting_user
    csv_path = Path(__file__).resolve().parents[1] / "seed" / "timetable.csv"

    response = client.post(
        "/timetable/import",
        files={"file": ("timetable.csv", csv_path.read_bytes(), "text/csv")},
    )

    assert response.status_code == 403
