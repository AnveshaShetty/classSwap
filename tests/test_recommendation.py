import pytest
from datetime import date
from backend.app.models.user import User
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus
from backend.app.services.recommendation_engine import get_candidate_recommendations

def test_recommendation_scoring_and_ranking(db_session):
    # Alice is absent on Monday Period 3
    # Monday is 2026-11-16 (or any Monday date, e.g., 2026-11-16 is a Monday)
    test_monday = date(2026, 11, 16)
    alice = db_session.query(User).filter(User.email == "alice@test.edu").first()
    bob = db_session.query(User).filter(User.email == "bob@test.edu").first()
    charlie = db_session.query(User).filter(User.email == "charlie@test.edu").first()

    absence = Absence(
        faculty_id=alice.id,
        date=test_monday,
        period_no=3,
        reason="Sick Leave",
        status=AbsenceStatus.PENDING.value
    )
    db_session.add(absence)
    db_session.commit()

    # Bob has 0 substitutions completed this month
    # Charlie has 0 substitutions completed this month
    # Formula: Final = 0.5 * Subject + 0.3 * Fairness + 0.2 * Dept
    recs = get_candidate_recommendations(db_session, absence)

    assert len(recs) >= 2
    # Bob is in Computer Science (dept match 1.0) and teaches Database Systems in CS (subject match 0.5)
    # Charlie is in Electronics (dept match 0.0, subject match 0.0)
    top_candidate = recs[0]
    assert top_candidate.faculty_id == bob.id
    assert top_candidate.dept_match == 1.0
    assert top_candidate.subject_match == 0.5
    assert top_candidate.fairness_score == 1.0  # both have 0 subs, so max == min -> 1.0
    
    # Expected score: (0.5 * 0.5) + (0.3 * 1.0) + (0.2 * 1.0) = 0.25 + 0.30 + 0.20 = 0.75
    assert round(top_candidate.final_score, 2) == 0.75

def test_fairness_distribution(db_session):
    test_monday = date(2026, 11, 16)
    alice = db_session.query(User).filter(User.email == "alice@test.edu").first()
    bob = db_session.query(User).filter(User.email == "bob@test.edu").first()
    charlie = db_session.query(User).filter(User.email == "charlie@test.edu").first()

    # Give Bob 2 prior substitutions this month
    # Charlie has 0
    absence_old = Absence(
        faculty_id=alice.id,
        date=date(2026, 11, 2),
        period_no=1,
        status=AbsenceStatus.ARRANGED.value
    )
    db_session.add(absence_old)
    db_session.flush()

    sub1 = Substitution(
        absence_id=absence_old.id,
        timetable_id=1,
        substitute_id=bob.id,
        status=SubstitutionStatus.ACCEPTED.value
    )
    sub2 = Substitution(
        absence_id=absence_old.id,
        timetable_id=1,
        substitute_id=bob.id,
        status=SubstitutionStatus.COMPLETED.value
    )
    db_session.add_all([sub1, sub2])
    db_session.commit()

    new_absence = Absence(
        faculty_id=alice.id,
        date=test_monday,
        period_no=3,
        status=AbsenceStatus.PENDING.value
    )
    db_session.add(new_absence)
    db_session.commit()

    recs = get_candidate_recommendations(db_session, new_absence)
    bob_rec = next(c for c in recs if c.faculty_id == bob.id)
    charlie_rec = next(c for c in recs if c.faculty_id == charlie.id)

    # Charlie (0 substitutions) should get fairness score 1.0
    # Bob (2 substitutions) should get fairness score 0.0
    assert charlie_rec.fairness_score == 1.0
    assert bob_rec.fairness_score == 0.0
    assert bob_rec.monthly_substitutions == 2
    assert charlie_rec.monthly_substitutions == 0
