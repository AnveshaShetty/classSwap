import pytest
from backend.app.services.timetable_service import validate_timetable_csv, commit_timetable_entries
from backend.app.models.timetable import Timetable

def test_valid_csv_import(db_session):
    valid_csv = (
        "section_name,subject_name,faculty_email,room_name,day_of_week,period_no\n"
        "CS-B,Database Systems,bob@test.edu,LH-102,Tuesday,1\n"
        "CS-A,Database Systems,bob@test.edu,LH-101,Tuesday,2\n"
    ).encode("utf-8")

    valid_entries, preview_items = validate_timetable_csv(valid_csv, db_session)
    assert len(valid_entries) == 2
    assert all(item.is_valid for item in preview_items)

    count = commit_timetable_entries(valid_entries, db_session)
    assert count == 2
    assert db_session.query(Timetable).count() == 3  # 1 initial + 2 new

def test_csv_conflict_detection(db_session):
    # Try importing a class where Bob is double-booked on same day & period
    conflict_csv = (
        "section_name,subject_name,faculty_email,room_name,day_of_week,period_no\n"
        "CS-A,Database Systems,bob@test.edu,LH-101,Wednesday,1\n"
        "CS-B,Database Systems,bob@test.edu,LH-102,Wednesday,1\n"
    ).encode("utf-8")

    valid_entries, preview_items = validate_timetable_csv(conflict_csv, db_session)
    # The second entry should fail due to internal batch faculty conflict
    assert len(valid_entries) == 1
    assert preview_items[1].is_valid is False
    assert any("Conflict" in err for err in preview_items[1].errors)

def test_csv_missing_entity_detection(db_session):
    invalid_csv = (
        "section_name,subject_name,faculty_email,room_name,day_of_week,period_no\n"
        "NonExistentSection,Database Systems,bob@test.edu,LH-101,Thursday,1\n"
        "CS-A,NonExistentSubject,bob@test.edu,LH-101,Thursday,2\n"
        "CS-A,Database Systems,nonexistent@test.edu,LH-101,Thursday,3\n"
    ).encode("utf-8")

    valid_entries, preview_items = validate_timetable_csv(invalid_csv, db_session)
    assert len(valid_entries) == 0
    assert len(preview_items) == 3
    assert all(item.is_valid is False for item in preview_items)
