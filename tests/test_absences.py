from collections.abc import Iterator
from datetime import date, timedelta

import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from tests.conftest import configure_csrf_client
from app.config import settings
from app.core.totp import encrypt_totp_secret
from app.database import Base, get_db
from app.main import app
from app.models import Absence, AdminChain, AuditLog, Leave, Substitution, Timetable, User
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
    with TestClient(app, base_url="https://testserver") as client:
        configure_csrf_client(client)
        yield client, test_engine, current_faculty
    app.dependency_overrides.clear()
    test_engine.dispose()


def test_mark_absence_for_one_or_more_scheduled_periods(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, faculty = absence_context
    response = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Medical leave"},
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
        json={"date": "2026-11-30", "periods": [3, 7], "reason": "Personal work"},
    )

    assert response.status_code == 422
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Absence)) == 20


def test_faculty_cannot_mark_past_absence(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, faculty = absence_context
    with Session(test_engine) as session:
        existing_absences = session.scalar(
            select(func.count()).select_from(Absence).where(Absence.faculty_id == faculty.id)
        )

    response = client.post(
        "/absences",
        json={
            "date": (date.today() - timedelta(days=1)).isoformat(),
            "periods": [3],
            "reason": "Backdated absence",
        },
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 422
    with Session(test_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(Absence).where(Absence.faculty_id == faculty.id)
        ) == existing_absences


def test_csrf_less_absence_post_is_rejected(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context

    response = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Missing token"},
        headers={"X-CSRF-Token": ""},
    )

    assert response.status_code == 403
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Absence)) == 20


def test_cross_origin_absence_post_is_rejected(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context

    response = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Cross-origin"},
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Absence)) == 20


def test_suggestions_exclude_teachers_busy_in_target_slot(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Conference"},
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
                Timetable.day_of_week == date(2026, 11, 30).weekday(),
                Timetable.period_no == 3,
            )
        ))
        assert absent_class is not None
        assert absent.faculty_id not in suggestion_ids
        assert not suggestion_ids.intersection(busy_ids)


def test_absence_ids_are_hidden_from_another_faculty_member(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, owner = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Private absence"},
    )
    absence_id = created.json()[0]["id"]

    with Session(test_engine) as session:
        other = session.scalar(
            select(User).where(User.id != owner.id, User.role == "faculty").limit(1)
        )
        assert other is not None
        other_user = _copy_user(session, other.id)
    app.dependency_overrides[get_current_user] = lambda: other_user
    headers = {"Accept": "application/json"}

    assert client.get(
        f"/absences/{absence_id}/suggestions",
        headers=headers,
    ).status_code == 404
    assert client.get(
        "/rooms/free",
        params={"absence_id": absence_id},
        headers=headers,
    ).status_code == 404
    assert client.get(
        f"/absences/{absence_id}/suggestions/view",
        headers=headers,
    ).status_code == 404
    assert client.get(
        "/absences/999999/suggestions",
        headers=headers,
    ).status_code == 404


def test_substitution_response_is_hidden_from_non_candidate(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, owner = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Private absence"},
    )
    absence_id = created.json()[0]["id"]
    candidate_id = client.get(f"/absences/{absence_id}/suggestions").json()[0]["faculty_id"]
    request = client.post(
        "/substitutions",
        json={"absence_id": absence_id, "substitute_id": candidate_id},
    )
    assert request.status_code == 200

    with Session(test_engine) as session:
        other = session.scalar(
            select(User).where(
                User.id.not_in({owner.id, candidate_id}),
                User.role == "faculty",
            ).limit(1)
        )
        assert other is not None
        other_user = _copy_user(session, other.id)
    app.dependency_overrides[get_current_user] = lambda: other_user

    hidden = client.patch(
        f"/substitutions/{request.json()['id']}",
        json={"status": "accepted"},
        headers={"Accept": "application/json"},
    )
    unknown = client.patch(
        "/substitutions/999999",
        json={"status": "accepted"},
        headers={"Accept": "application/json"},
    )

    assert hidden.status_code == unknown.status_code == 404


def test_faculty_cannot_create_substitution_for_another_facultys_absence(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, owner = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Private absence"},
    )
    absence_id = created.json()[0]["id"]
    candidate_id = client.get(f"/absences/{absence_id}/suggestions").json()[0]["faculty_id"]

    with Session(test_engine) as session:
        other = session.scalar(
            select(User).where(User.id != owner.id, User.role == "faculty").limit(1)
        )
        assert other is not None
        other_user = _copy_user(session, other.id)
    app.dependency_overrides[get_current_user] = lambda: other_user

    response = client.post(
        "/substitutions",
        json={"absence_id": absence_id, "substitute_id": candidate_id},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 404


def test_candidate_pending_request_limit_is_enforced(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Too many pending requests"},
    )
    assert created.status_code == 200
    absence_id = created.json()[0]["id"]
    candidate_id = client.get(f"/absences/{absence_id}/suggestions").json()[0]["faculty_id"]

    with Session(test_engine) as session:
        absence = session.get(Absence, absence_id)
        assert absence is not None
        timetable = session.get(Timetable, absence.timetable_id)
        assert timetable is not None
        other_absence_ids = list(
            session.scalars(select(Absence.id).where(Absence.id != absence_id).limit(5))
        )
        assert len(other_absence_ids) == 5
        session.add_all(
            [
                Substitution(
                    absence_id=other_absence_ids[index - 1],
                    substitute_id=candidate_id,
                    room_id=timetable.room_id,
                    date=date(2030, 1, index),
                    period_no=1,
                    status="pending",
                )
                for index in range(1, 6)
            ]
        )
        session.commit()

    response = client.post(
        "/substitutions",
        json={"absence_id": absence_id, "substitute_id": candidate_id},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 409
    assert "too many pending requests" in response.json()["detail"]


def test_absence_create_rejects_mass_assignment(absence_context: tuple[TestClient, Engine, User]) -> None:
    client, test_engine, _ = absence_context

    response = client.post(
        "/absences",
        json={
            "date": "2026-11-30",
            "periods": [3],
            "reason": "Unauthorized owner",
            "faculty_id": 1,
        },
    )

    assert response.status_code == 422
    with Session(test_engine) as session:
        assert session.scalar(select(func.count()).select_from(Absence)) == 20


def test_acting_admin_lookup_cannot_cross_departments(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, _, _ = absence_context

    response = client.get(
        "/admin/acting",
        params={"department": "Unrelated Department"},
    )

    assert response.status_code == 404


@pytest.mark.parametrize("status", ["pending", "accepted"])
def test_suggestions_exclude_active_substitutes_in_target_slot(
    absence_context: tuple[TestClient, Engine, User],
    status: str,
) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Medical leave"},
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
            Timetable.day_of_week == date(2026, 11, 30).weekday(),
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


def _copy_user(session: Session, user_id: int) -> User:
    user = session.get(User, user_id)
    assert user is not None
    return User(
        id=user.id,
        name=user.name,
        email=user.email,
        password_hash=user.password_hash,
        role=user.role,
        department=user.department,
        teaches=user.teaches,
    )


def test_substitution_request_inbox_decline_offers_next_candidate(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Conference"},
    )
    suggestions = client.get("/absences/%d/suggestions" % created.json()[0]["id"]).json()
    assert len(suggestions) >= 2
    selected_id = suggestions[0]["faculty_id"]

    request = client.post(
        "/substitutions",
        json={"absence_id": created.json()[0]["id"], "substitute_id": selected_id},
    )

    assert request.status_code == 200
    assert request.json()["status"] == "pending"
    with Session(test_engine) as session:
        candidate = _copy_user(session, selected_id)
    app.dependency_overrides[get_current_user] = lambda: candidate

    inbox = client.get("/substitutions/inbox")
    assert inbox.status_code == 200
    assert [item["substitution"]["id"] for item in inbox.json()] == [request.json()["id"]]
    declined = client.patch(
        "/substitutions/%d" % request.json()["id"],
        json={"status": "declined"},
    )

    assert declined.status_code == 200
    assert declined.json()["substitution"]["status"] == "declined"
    assert declined.json()["next_request"] is not None
    assert declined.json()["next_request"]["substitute_id"] != selected_id


def test_substitution_request_can_be_accepted(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Training programme"},
    )
    selected_id = client.get(
        "/absences/%d/suggestions" % created.json()[0]["id"]
    ).json()[0]["faculty_id"]
    request = client.post(
        "/substitutions",
        json={"absence_id": created.json()[0]["id"], "substitute_id": selected_id},
    )
    assert request.status_code == 200

    with Session(test_engine) as session:
        candidate = _copy_user(session, selected_id)
    app.dependency_overrides[get_current_user] = lambda: candidate
    accepted = client.patch(
        "/substitutions/%d" % request.json()["id"],
        json={"status": "accepted"},
    )

    assert accepted.status_code == 200
    assert accepted.json()["substitution"]["status"] == "accepted"
    assert accepted.json()["next_request"] is None
    repeated = client.patch(
        "/substitutions/%d" % request.json()["id"],
        json={"status": "accepted"},
    )
    assert repeated.status_code == 200
    assert repeated.json()["substitution"]["status"] == "accepted"
    assert repeated.json()["next_request"] is None


def test_hod_absence_automatically_requests_top_suggestion(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    with Session(test_engine) as session:
        hod = session.scalar(select(User).where(User.role == "hod"))
        assert hod is not None
        hod_user = _copy_user(session, hod.id)
        scheduled_class = session.scalar(
            select(Timetable).where(
                Timetable.faculty_id == hod.id,
                Timetable.day_of_week == 0,
            ).limit(1)
        )
        assert scheduled_class is not None
        period = scheduled_class.period_no
    app.dependency_overrides[get_current_user] = lambda: hod_user

    created = client.post(
        "/absences",
        json={
            "date": "2026-11-30",
            "periods": [period],
            "reason": "Medical leave",
        },
    )

    assert created.status_code == 200
    with Session(test_engine) as session:
        requests = list(session.scalars(
            select(Substitution).where(Substitution.absence_id == created.json()[0]["id"])
        ))
        assert len(requests) == 1
        assert requests[0].status == "pending"


def test_same_substitute_cannot_be_requested_for_two_classes_in_one_slot(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    first_absence = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Medical leave"},
    ).json()[0]
    suggestions = client.get(
        "/absences/%d/suggestions" % first_absence["id"]
    ).json()
    substitute_id = suggestions[0]["faculty_id"]
    first_request = client.post(
        "/substitutions",
        json={"absence_id": first_absence["id"], "substitute_id": substitute_id},
    )
    assert first_request.status_code == 200

    with Session(test_engine) as session:
        scheduled_class = session.scalar(
            select(Timetable).where(
                Timetable.day_of_week == 0,
                Timetable.period_no == 3,
                Timetable.section_id != session.scalar(
                    select(Timetable.section_id).where(
                        Timetable.id == first_absence["timetable_id"]
                    )
                ),
            ).limit(1)
        )
        assert scheduled_class is not None
        second_absence = Absence(
            timetable_id=scheduled_class.id,
            faculty_id=scheduled_class.faculty_id,
            date=date(2026, 11, 30),
            period_no=3,
            reason="Personal work",
        )
        session.add(second_absence)
        session.flush()
        second_absence_id = second_absence.id
        second_owner = _copy_user(session, scheduled_class.faculty_id)
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: second_owner

    conflicting_request = client.post(
        "/substitutions",
        json={"absence_id": second_absence_id, "substitute_id": substitute_id},
    )

    assert conflicting_request.status_code == 409


def test_free_room_lookup_respects_class_type_and_section_capacity(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    created = client.post(
        "/absences",
        json={"date": "2026-11-30", "periods": [3], "reason": "Training programme"},
    ).json()[0]

    rooms = client.get("/rooms/free", params={"absence_id": created["id"]})

    assert rooms.status_code == 200
    with Session(test_engine) as session:
        timetable = session.get(Timetable, created["timetable_id"])
        assert timetable is not None
        original_room = timetable.room_id
    assert all(room["type"] == "class" for room in rooms.json())
    assert all(room["id"] != original_room for room in rooms.json())


def test_whole_day_leave_creates_absences_and_audit_entry(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, faculty = absence_context
    days_until_monday = (7 - date.today().weekday()) % 7 or 7
    leave_date = date.today() + timedelta(days=days_until_monday)

    response = client.post(
        "/leaves",
        json={"date": leave_date.isoformat(), "reason": "Conference"},
    )

    assert response.status_code == 200
    assert response.json()["absences_created"] > 0
    with Session(test_engine) as session:
        assert session.get(Leave, (faculty.id, leave_date)) is not None
        assert session.scalar(
            select(func.count()).select_from(Absence).where(
                Absence.faculty_id == faculty.id,
                Absence.date == leave_date,
            )
        ) == response.json()["absences_created"]
        assert session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "leave.created")
        ) == 1
    marked_absence = client.post(
        "/absences",
        json={"date": leave_date.isoformat(), "periods": [3], "reason": "Personal work"},
    )
    assert marked_absence.status_code == 409


def test_cancelling_whole_day_leave_removes_its_absences(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, faculty = absence_context
    days_until_monday = (7 - date.today().weekday()) % 7 or 7
    leave_date = date.today() + timedelta(days=days_until_monday)
    created = client.post(
        "/leaves",
        json={"date": leave_date.isoformat(), "reason": "Personal work"},
    )
    assert created.status_code == 200

    deleted = client.delete("/leaves/%s" % leave_date.isoformat())
    repeated = client.delete("/leaves/%s" % leave_date.isoformat())

    assert deleted.status_code == 204
    assert repeated.status_code == 204
    with Session(test_engine) as session:
        assert session.get(Leave, (faculty.id, leave_date)) is None
        assert session.scalar(
            select(func.count()).select_from(Absence).where(
                Absence.faculty_id == faculty.id,
                Absence.date == leave_date,
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "leave.cancelled")
        ) == 1


def test_acting_admin_falls_back_to_first_available_chain_member(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    with Session(test_engine) as session:
        for chain_entry, user in session.execute(
            select(AdminChain, User).join(User, User.id == AdminChain.user_id)
        ):
            session.add(Leave(user_id=user.id, date=date.today()))
        session.commit()

    acting = client.get("/admin/acting")

    assert acting.status_code == 200
    assert acting.json()["email"] == "principal.demo@demo.edu"
    assert acting.json()["role"] == "super_admin"


def test_stand_in_admin_cannot_import_timetable(
    absence_context: tuple[TestClient, Engine, User],
) -> None:
    client, test_engine, _ = absence_context
    with Session(test_engine) as session:
        hod = session.scalar(select(User).where(User.role == "hod"))
        assert hod is not None
        session.add(Leave(user_id=hod.id, date=date.today()))
        stand_in = session.scalar(
            select(User).where(User.email == "arjun.kulkarni@demo.edu")
        )
        assert stand_in is not None
        stand_in_user = _copy_user(session, stand_in.id)
        session.commit()
    app.dependency_overrides[get_current_user] = lambda: stand_in_user

    acting = client.get("/admin/acting")
    response = client.post(
        "/timetable/import",
        files={"file": ("empty.csv", b"section,day,period,subject,faculty_email,room\n", "text/csv")},
    )

    assert acting.status_code == 200
    assert acting.json()["email"] == "arjun.kulkarni@demo.edu"
    assert response.status_code == 403


def test_acting_hod_cannot_edit_admin_chain(
    absence_context: tuple[TestClient, Engine, User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, test_engine, _ = absence_context
    with Session(test_engine) as session:
        hod = session.scalar(select(User).where(User.role == "hod"))
        assert hod is not None
        secret = pyotp.random_base32()
        monkeypatch.setattr(
            settings,
            "totp_encryption_key",
            Fernet.generate_key().decode("ascii"),
        )
        hod_user = _copy_user(session, hod.id)
        hod_user.totp_secret_encrypted = encrypt_totp_secret(secret)
        hod_user.totp_enabled = True
        chain = [
            {"position": entry.position, "email": user.email}
            for entry, user in session.execute(
                select(AdminChain, User).join(User, User.id == AdminChain.user_id)
            )
        ]
    app.dependency_overrides[get_current_user] = lambda: hod_user
    client.headers["X-TOTP-Code"] = pyotp.TOTP(secret).now()

    response = client.put(
        "/admin/chain",
        json={"department": "Computer Science and Design", "entries": chain},
    )

    assert response.status_code == 403
    with Session(test_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.action == "admin_chain.updated"
            )
        ) == 0
