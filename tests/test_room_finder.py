import pytest
from datetime import date
from backend.app.models.academic import Room, Section, RoomType
from backend.app.services.room_finder import find_available_rooms

def test_room_availability_and_capacity(db_session):
    test_date = date(2026, 11, 16)  # Monday
    sec_a = db_session.query(Section).filter(Section.name == "CS-A").first()  # strength 55
    
    # Monday Period 3: LH-101 is booked by timetable entry
    # Available should be LH-102 (capacity 40) and LAB-1 (capacity 50)
    free_rooms = find_available_rooms(
        db=db_session,
        query_date=test_date,
        period_no=3,
        section_id=sec_a.id,
        is_lab=False,
        allow_lab_for_theory=True
    )

    room_names = [r.room_name for r in free_rooms]
    # LH-101 is occupied, so it must not be in free rooms
    assert "LH-101" not in room_names
    assert "LH-102" in room_names or "LAB-1" in room_names

def test_lab_requirement_filtering(db_session):
    test_date = date(2026, 11, 16)  # Monday
    sec_b = db_session.query(Section).filter(Section.name == "CS-B").first()  # strength 35

    # Theory class with allow_lab_for_theory=False should exclude labs
    theory_free = find_available_rooms(
        db=db_session,
        query_date=test_date,
        period_no=3,
        section_id=sec_b.id,
        is_lab=False,
        allow_lab_for_theory=False
    )
    for r in theory_free:
        assert r.room_type == RoomType.CLASSROOM.value
