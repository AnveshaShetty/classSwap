import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.database import Base
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, FacultySubject, Room, RoomType, Section
from backend.app.models.timetable import PeriodConfig, Timetable
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus, DateOverride
from backend.app.core.security import get_password_hash

# In-memory SQLite for testing
TEST_DATABASE_URL = "sqlite:///:memory:"

@pytest.fixture(scope="function")
def db_session():
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()

    # Seed minimal baseline data
    admin = User(
        name="Admin Test",
        email="admin@test.edu",
        password_hash=get_password_hash("AdminPass123"),
        role=UserRole.ADMIN.value,
        department="Computer Science",
        is_active=True
    )
    fac1 = User(
        name="Prof. Alice",
        email="alice@test.edu",
        password_hash=get_password_hash("FacPass123"),
        role=UserRole.FACULTY.value,
        department="Computer Science",
        is_active=True
    )
    fac2 = User(
        name="Prof. Bob",
        email="bob@test.edu",
        password_hash=get_password_hash("FacPass123"),
        role=UserRole.FACULTY.value,
        department="Computer Science",
        is_active=True
    )
    fac3 = User(
        name="Prof. Charlie",
        email="charlie@test.edu",
        password_hash=get_password_hash("FacPass123"),
        role=UserRole.FACULTY.value,
        department="Electronics",
        is_active=True
    )
    session.add_all([admin, fac1, fac2, fac3])
    session.flush()

    # Periods
    session.add(PeriodConfig(period_no=1, label="Period 1", start_time="09:00 AM", end_time="09:50 AM", duration_minutes=50))
    session.add(PeriodConfig(period_no=2, label="Period 2", start_time="09:55 AM", end_time="10:45 AM", duration_minutes=50))
    session.add(PeriodConfig(period_no=3, label="Period 3", start_time="11:00 AM", end_time="11:50 AM", duration_minutes=50))

    # Subjects
    sub_ds = Subject(code="CS101", name="Data Structures", department="Computer Science", is_lab=False, credits=4)
    sub_db = Subject(code="CS102", name="Database Systems", department="Computer Science", is_lab=False, credits=4)
    sub_lab = Subject(code="CS103", name="Computing Lab", department="Computer Science", is_lab=True, credits=2)
    session.add_all([sub_ds, sub_db, sub_lab])
    session.flush()

    # Faculty Subjects
    # Alice: qualified in Data Structures
    # Bob: qualified in Database Systems
    session.add(FacultySubject(faculty_id=fac1.id, subject_id=sub_ds.id, experience_years=3))
    session.add(FacultySubject(faculty_id=fac2.id, subject_id=sub_db.id, experience_years=2))

    # Rooms
    r101 = Room(name="LH-101", type=RoomType.CLASSROOM.value, capacity=60, building="Main Block")
    r102 = Room(name="LH-102", type=RoomType.CLASSROOM.value, capacity=40, building="Main Block")
    lab1 = Room(name="LAB-1", type=RoomType.LABORATORY.value, capacity=50, building="Tech Block")
    session.add_all([r101, r102, lab1])

    # Sections
    sec_a = Section(name="CS-A", semester=3, strength=55, department="Computer Science")
    sec_b = Section(name="CS-B", semester=3, strength=35, department="Computer Science")
    session.add_all([sec_a, sec_b])
    session.flush()

    # Timetable: Alice teaches CS-A Data Structures on Monday Period 3 in LH-101
    tt1 = Timetable(
        section_id=sec_a.id,
        subject_id=sub_ds.id,
        faculty_id=fac1.id,
        room_id=r101.id,
        day_of_week="Monday",
        period_no=3
    )
    session.add(tt1)
    session.commit()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
