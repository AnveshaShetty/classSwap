from collections.abc import Iterator
from datetime import date

import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from tests.conftest import configure_csrf_client
from app.config import settings
from app.core.totp import encrypt_totp_secret
from app.database import Base, get_db
from app.main import app
from app.models import Absence, Substitution, Timetable, User
from app.services.suggestion import suggest_candidates
from scripts.seed import load_seed


@pytest.fixture
def dashboard_context() -> Iterator[tuple[TestClient, Engine, User]]:
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    with Session(test_engine) as session:
        with session.begin():
            load_seed(session)
        seeded_user = session.scalar(select(User).where(User.email == "ravi.kulal@demo.edu"))
        assert seeded_user is not None
        current_user = User(
            id=seeded_user.id,
            name=seeded_user.name,
            email=seeded_user.email,
            password_hash=seeded_user.password_hash,
            role=seeded_user.role,
            department=seeded_user.department,
            teaches=seeded_user.teaches,
        )

    def override_get_db() -> Iterator[Session]:
        with Session(test_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: current_user
    with TestClient(app, base_url="https://testserver") as client:
        configure_csrf_client(client)
        yield client, test_engine, current_user
    app.dependency_overrides.clear()
    test_engine.dispose()


def _act_as_hod(
    client: TestClient,
    test_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with Session(test_engine) as session:
        hod = session.scalar(select(User).where(User.role == "hod"))
        assert hod is not None
        secret = pyotp.random_base32()
        monkeypatch.setattr(
            settings,
            "totp_encryption_key",
            Fernet.generate_key().decode("ascii"),
        )
        current_user = User(
            id=hod.id,
            name=hod.name,
            email=hod.email,
            password_hash=hod.password_hash,
            role=hod.role,
            department=hod.department,
            teaches=hod.teaches,
            totp_secret_encrypted=encrypt_totp_secret(secret),
            totp_enabled=True,
        )
    app.dependency_overrides[get_current_user] = lambda: current_user
    client.headers["X-TOTP-Code"] = pyotp.TOTP(secret).now()


def test_dashboard_api_and_page_use_stored_absence_data(
    dashboard_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, faculty = dashboard_context
    target_date = date(2026, 11, 23)
    with Session(test_engine) as session:
        scheduled_class = session.scalar(
            select(Timetable).where(
                Timetable.day_of_week == target_date.weekday(),
                Timetable.period_no == 1,
            ).limit(1)
        )
        assert scheduled_class is not None
        faculty = session.get(User, scheduled_class.faculty_id)
        assert faculty is not None
        absence = Absence(
            timetable_id=scheduled_class.id,
            faculty_id=faculty.id,
            date=target_date,
            period_no=scheduled_class.period_no,
            reason="Medical leave",
        )
        session.add(absence)
        session.commit()

    response = client.get("/stats/dashboard", params={"date": target_date.isoformat()})

    assert response.status_code == 200
    data = response.json()
    assert data["absence_count"] == 1
    assert data["today_absences"][0]["reason"] == "Medical leave"
    assert data["today_absences"][0]["status"] == "unrequested"
    page = client.get("/dashboard", params={"date": target_date.isoformat()})
    assert page.status_code == 200
    assert "Absence register" in page.text
    assert "Medical leave" in page.text


def test_stored_user_content_is_html_escaped(
    dashboard_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, current_user = dashboard_context
    current_user.name = '<img src=x onerror="alert(1)">'
    with Session(test_engine) as session:
        timetable = session.scalar(
            select(Timetable).where(
                Timetable.faculty_id == current_user.id,
                Timetable.day_of_week == 0,
                Timetable.period_no == 3,
            )
        )
        assert timetable is not None
        session.add(Absence(
            timetable_id=timetable.id,
            faculty_id=current_user.id,
            date=date(2026, 11, 30),
            period_no=3,
            reason='<script>alert("stored")</script>',
        ))
        session.commit()

    response = client.get("/dashboard", params={"date": "2026-11-30"})

    assert response.status_code == 200
    assert '<img src=x onerror="alert(1)">' not in response.text
    assert "&lt;img" in response.text
    assert '<script>alert("stored")</script>' not in response.text
    assert "&lt;script&gt;" in response.text


def test_monthly_report_csv_contains_seeded_rows_and_statuses(
    dashboard_context: tuple[TestClient, Engine, User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, test_engine, _ = dashboard_context
    assert client.get("/reports").status_code == 403
    _act_as_hod(client, test_engine, monkeypatch)

    response = client.get("/reports/monthly", params={"month": "2026-11"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment;" in response.headers["content-disposition"]
    lines = response.text.splitlines()
    assert lines[0].startswith("absence_id,date,department,section,semester,subject")
    assert len(lines) == 9
    assert ",accepted," in response.text

    page = client.get("/reports", params={"month": "2026-11"})
    assert page.status_code == 200
    assert "Monthly report" in page.text
    assert "2026-11-02" in page.text


@pytest.mark.parametrize("month", ["2026-13", "November 2026", "2026-2"])
def test_monthly_report_rejects_invalid_month(
    dashboard_context: tuple[TestClient, Engine, User],
    month: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, test_engine, _ = dashboard_context
    _act_as_hod(client, test_engine, monkeypatch)

    response = client.get("/reports/monthly", params={"month": month})

    assert response.status_code == 422


def test_ui_routes_render_without_external_images(
    dashboard_context: tuple[TestClient, Engine, User],
) -> None:
    client, _, _ = dashboard_context
    login = client.get("/login")
    absence = client.get("/absence/new")
    inbox = client.get("/requests")
    timetable = client.get("/timetable")

    assert login.status_code == 200
    assert "Sign in" in login.text
    assert all(response.status_code == 200 for response in (absence, inbox, timetable))
    assert "<img" not in login.text.lower()
    assert "<img" not in absence.text.lower()


def test_custom_error_page_and_favicon(
    dashboard_context: tuple[TestClient, Engine, User],
) -> None:
    client, _, _ = dashboard_context

    missing = client.get("/this-page-does-not-exist")
    favicon = client.get("/static/favicon.svg")

    assert missing.status_code == 404
    assert "We couldn’t find that page" in missing.text
    assert favicon.status_code == 200
    assert "image/svg+xml" in favicon.headers["content-type"]


def test_inbox_responds_with_htmx_fragment_without_page_reload(
    dashboard_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, faculty = dashboard_context
    target_date = date(2026, 11, 23)
    with Session(test_engine) as session:
        scheduled_class = session.scalar(
            select(Timetable).where(
                Timetable.day_of_week == target_date.weekday(),
                Timetable.period_no == 3,
                Timetable.faculty_id == faculty.id,
            )
        )
        assert scheduled_class is not None
        absence = Absence(
            timetable_id=scheduled_class.id,
            faculty_id=scheduled_class.faculty_id,
            date=target_date,
            period_no=scheduled_class.period_no,
            reason="Conference",
        )
        session.add(absence)
        session.flush()
        suggestion = suggest_candidates(session, absence.id)[0]
        substitution = Substitution(
            absence_id=absence.id,
            substitute_id=suggestion.faculty_id,
            room_id=scheduled_class.room_id,
            date=target_date,
            period_no=scheduled_class.period_no,
            status="pending",
        )
        session.add(substitution)
        session.flush()
        substitution_id = substitution.id
        candidate_row = session.get(User, suggestion.faculty_id)
        assert candidate_row is not None
        candidate = User(
            id=candidate_row.id,
            name=candidate_row.name,
            email=candidate_row.email,
            password_hash=candidate_row.password_hash,
            role=candidate_row.role,
            department=candidate_row.department,
            teaches=candidate_row.teaches,
        )
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: candidate

    inbox = client.get("/requests")
    response = client.post(
        "/requests/%d/respond" % substitution_id,
        data={"status": "accepted"},
    )

    assert inbox.status_code == 200
    assert 'hx-post="/requests/%d/respond"' % substitution_id in inbox.text
    assert response.status_code == 200
    assert "You accepted this class" in response.text
