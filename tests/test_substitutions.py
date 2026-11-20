import pytest
from datetime import date
from backend.app.models.user import User
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus, DateOverride
from backend.app.models.timetable import Timetable
from backend.app.services.timetable_service import get_date_specific_timetable

def test_substitution_acceptance_and_date_override(db_session):
    test_date = date(2026, 11, 16)  # Monday
    alice = db_session.query(User).filter(User.email == "alice@test.edu").first()
    bob = db_session.query(User).filter(User.email == "bob@test.edu").first()

    # Alice is absent on Monday P3
    absence = Absence(
        faculty_id=alice.id,
        date=test_date,
        period_no=3,
        status=AbsenceStatus.PROCESSING.value
    )
    db_session.add(absence)
    db_session.flush()

    tt = db_session.query(Timetable).filter(
        Timetable.faculty_id == alice.id,
        Timetable.day_of_week == "Monday",
        Timetable.period_no == 3
    ).first()

    # Admin requests Bob
    sub = Substitution(
        absence_id=absence.id,
        timetable_id=tt.id,
        substitute_id=bob.id,
        room_id=tt.room_id,
        status=SubstitutionStatus.PENDING.value,
        score=0.85
    )
    db_session.add(sub)
    db_session.commit()

    # Bob accepts substitution
    sub.status = SubstitutionStatus.ACCEPTED.value
    absence.status = AbsenceStatus.ARRANGED.value

    # Date override is registered
    override = DateOverride(
        date=test_date,
        period_no=3,
        section_id=tt.section_id,
        subject_id=tt.subject_id,
        original_faculty_id=alice.id,
        substitute_faculty_id=bob.id,
        room_id=tt.room_id,
        substitution_id=sub.id
    )
    db_session.add(override)
    db_session.commit()

    # Verify that original permanent timetable still has Alice!
    permanent_tt = db_session.query(Timetable).filter(Timetable.id == tt.id).first()
    assert permanent_tt.faculty_id == alice.id

    # Verify that date-specific merged timetable shows Bob as substitute!
    date_schedule = get_date_specific_timetable(db_session, target_date=test_date, section_id=tt.section_id)
    assert len(date_schedule) == 1
    assert date_schedule[0]["is_substituted"] is True
    assert "Substitute" in date_schedule[0]["faculty_name"]
    assert date_schedule[0]["faculty_id"] == bob.id
