import pytest
from datetime import date
from backend.app.models.user import User
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus
from backend.app.services.report_service import calculate_monthly_analytics, generate_pdf_report, generate_csv_report

def test_monthly_analytics_and_idle_hours(db_session):
    alice = db_session.query(User).filter(User.email == "alice@test.edu").first()
    bob = db_session.query(User).filter(User.email == "bob@test.edu").first()

    # Create 2 absences in November 2026
    # 1 accepted, 1 declined
    abs1 = Absence(
        faculty_id=alice.id,
        date=date(2026, 11, 10),
        period_no=1,
        status=AbsenceStatus.ARRANGED.value
    )
    abs2 = Absence(
        faculty_id=alice.id,
        date=date(2026, 11, 11),
        period_no=2,
        status=AbsenceStatus.PENDING.value
    )
    db_session.add_all([abs1, abs2])
    db_session.flush()

    sub1 = Substitution(
        absence_id=abs1.id,
        timetable_id=1,
        substitute_id=bob.id,
        status=SubstitutionStatus.ACCEPTED.value
    )
    sub2 = Substitution(
        absence_id=abs2.id,
        timetable_id=1,
        substitute_id=bob.id,
        status=SubstitutionStatus.DECLINED.value
    )
    db_session.add_all([sub1, sub2])
    db_session.commit()

    report = calculate_monthly_analytics(db_session, year=2026, month=11)
    
    assert report.total_absences == 2
    assert report.substitutions_requested == 2
    assert report.substitutions_accepted == 1
    assert report.substitutions_declined == 1
    assert report.classes_recovered == 1
    # 1 class recovered * (50 min / 60 min) = 0.83 hrs
    assert report.idle_hours_saved == 0.83

    # Test PDF generation
    pdf_bytes = generate_pdf_report(report)
    assert len(pdf_bytes) > 500
    assert pdf_bytes.startswith(b"%PDF")

    # Test CSV generation
    csv_str = generate_csv_report(report)
    assert "EXECUTIVE SUMMARY" in csv_str
    assert "Classes Recovered" in csv_str
    assert "0.83 hours" in csv_str
