import os
import sys
from datetime import date, datetime, timedelta

# Ensure project root is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.database import SessionLocal, engine, Base
from backend.app.models.user import User, UserRole
from backend.app.models.academic import Subject, FacultySubject, Room, RoomType, Section
from backend.app.models.timetable import PeriodConfig, Timetable
from backend.app.models.substitution import Absence, AbsenceStatus, Substitution, SubstitutionStatus, DateOverride
from backend.app.models.notification import Notification
from backend.app.core.security import get_password_hash

def seed_database():
    print("Initializing ClassSwap database...")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check if already seeded
        if db.query(User).filter(User.email == "admin@classswap.edu").first():
            print("Database already has records. Cleaning and reseeding with fresh demo dataset...")
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)

        print("1. Creating Users (Admin & 15 Faculty Members)...")
        admin = User(
            name="Dr. Arvind Swaminathan (HOD)",
            email="admin@classswap.edu",
            password_hash=get_password_hash("Admin@123"),
            role=UserRole.ADMIN.value,
            department="Computer Science & Engineering",
            phone="+91 98765 43210",
            is_active=True
        )
        db.add(admin)

        faculty_data = [
            ("Dr. Rajesh Kumar", "rajesh.kumar@classswap.edu", "Computer Science & Engineering", "+91 98765 00001"),
            ("Dr. Anita Sharma", "anita.sharma@classswap.edu", "Computer Science & Engineering", "+91 98765 00002"),
            ("Prof. Vikram Singh", "vikram.singh@classswap.edu", "Computer Science & Engineering", "+91 98765 00003"),
            ("Dr. Priya Nair", "priya.nair@classswap.edu", "Computer Science & Engineering", "+91 98765 00004"),
            ("Prof. Suresh Menon", "suresh.menon@classswap.edu", "Computer Science & Engineering", "+91 98765 00005"),
            ("Dr. Deepa Iyer", "deepa.iyer@classswap.edu", "Computer Science & Engineering", "+91 98765 00006"),
            ("Dr. Rahul Joshi", "rahul.joshi@classswap.edu", "Computer Science & Engineering", "+91 98765 00007"),
            ("Prof. Pooja Mehta", "pooja.mehta@classswap.edu", "Computer Science & Engineering", "+91 98765 00008"),
            ("Dr. Neha Gupta", "neha.gupta@classswap.edu", "Computer Science & Engineering", "+91 98765 00009"),
            ("Dr. Arun Patel", "arun.patel@classswap.edu", "Electronics & Communication Engineering", "+91 98765 00010"),
            ("Prof. Kavita Reddy", "kavita.reddy@classswap.edu", "Electronics & Communication Engineering", "+91 98765 00011"),
            ("Dr. Manoj Verma", "manoj.verma@classswap.edu", "Electronics & Communication Engineering", "+91 98765 00012"),
            ("Prof. Sunita Deshmukh", "sunita.deshmukh@classswap.edu", "Electronics & Communication Engineering", "+91 98765 00013"),
            ("Dr. Amit Bhatt", "amit.bhatt@classswap.edu", "Electronics & Communication Engineering", "+91 98765 00014"),
            ("Prof. Sanjay Rao", "sanjay.rao@classswap.edu", "Electronics & Communication Engineering", "+91 98765 00015"),
        ]

        faculty_objs = {}
        for name, email, dept, phone in faculty_data:
            fac = User(
                name=name,
                email=email,
                password_hash=get_password_hash("Faculty@123"),
                role=UserRole.FACULTY.value,
                department=dept,
                phone=phone,
                is_active=True
            )
            db.add(fac)
            db.flush()
            faculty_objs[email] = fac

        print("2. Creating Period Configurations...")
        period_data = [
            (1, "Period 1", "09:00 AM", "09:50 AM", 50),
            (2, "Period 2", "09:55 AM", "10:45 AM", 50),
            (3, "Period 3", "11:00 AM", "11:50 AM", 50),
            (4, "Period 4", "11:55 AM", "12:45 PM", 50),
            (5, "Period 5", "01:30 PM", "02:20 PM", 50),
            (6, "Period 6", "02:25 PM", "03:15 PM", 50),
        ]
        for p_no, label, start, end, dur in period_data:
            db.add(PeriodConfig(period_no=p_no, label=label, start_time=start, end_time=end, duration_minutes=dur))

        print("3. Creating 10 Rooms (Classrooms & Labs)...")
        room_data = [
            ("LH-101", RoomType.CLASSROOM.value, 70, "Aryabhatta Block"),
            ("LH-102", RoomType.CLASSROOM.value, 70, "Aryabhatta Block"),
            ("LH-201", RoomType.CLASSROOM.value, 75, "Aryabhatta Block"),
            ("LH-202", RoomType.CLASSROOM.value, 65, "Aryabhatta Block"),
            ("CR-301", RoomType.CLASSROOM.value, 50, "Ramanujan Block"),
            ("CR-302", RoomType.CLASSROOM.value, 50, "Ramanujan Block"),
            ("AUD-01", RoomType.CLASSROOM.value, 120, "Central Academic Complex"),
            ("CS-LAB-1", RoomType.LABORATORY.value, 60, "Turing Computing Centre"),
            ("CS-LAB-2", RoomType.LABORATORY.value, 60, "Turing Computing Centre"),
            ("ECE-LAB-1", RoomType.LABORATORY.value, 50, "Marconi Electronics Complex"),
        ]
        room_objs = {}
        for name, rtype, cap, bldg in room_data:
            rm = Room(name=name, type=rtype, capacity=cap, building=bldg)
            db.add(rm)
            db.flush()
            room_objs[name] = rm

        print("4. Creating 8 Sections...")
        section_data = [
            ("CSE-A (3rd Sem)", 3, 60, "Computer Science & Engineering"),
            ("CSE-B (3rd Sem)", 3, 58, "Computer Science & Engineering"),
            ("CSE-A (5th Sem)", 5, 55, "Computer Science & Engineering"),
            ("CSE-B (5th Sem)", 5, 54, "Computer Science & Engineering"),
            ("CSE-A (7th Sem)", 7, 50, "Computer Science & Engineering"),
            ("ECE-A (3rd Sem)", 3, 48, "Electronics & Communication Engineering"),
            ("ECE-B (5th Sem)", 5, 45, "Electronics & Communication Engineering"),
            ("AI-DS (3rd Sem)", 3, 52, "Computer Science & Engineering"),
        ]
        section_objs = {}
        for name, sem, strength, dept in section_data:
            sec = Section(name=name, semester=sem, strength=strength, department=dept)
            db.add(sec)
            db.flush()
            section_objs[name] = sec

        print("5. Creating Subjects...")
        subject_data = [
            # CSE Subjects
            ("CS301", "Data Structures & Algorithms", "Computer Science & Engineering", False, 4),
            ("CS302", "Database Management Systems", "Computer Science & Engineering", False, 4),
            ("CS303", "Object Oriented Programming (Java)", "Computer Science & Engineering", False, 3),
            ("CS304", "Data Structures Lab", "Computer Science & Engineering", True, 2),
            ("CS501", "Computer Networks", "Computer Science & Engineering", False, 4),
            ("CS502", "Operating Systems", "Computer Science & Engineering", False, 4),
            ("CS503", "Software Engineering", "Computer Science & Engineering", False, 3),
            ("CS504", "Database & Networks Lab", "Computer Science & Engineering", True, 2),
            ("CS701", "Machine Learning & AI", "Computer Science & Engineering", False, 4),
            ("CS702", "Cloud Computing", "Computer Science & Engineering", False, 3),
            # ECE Subjects
            ("EC301", "Digital Electronics", "Electronics & Communication Engineering", False, 4),
            ("EC302", "Signals & Systems", "Electronics & Communication Engineering", False, 4),
            ("EC303", "Analog Circuits", "Electronics & Communication Engineering", False, 3),
            ("EC304", "Digital Electronics Lab", "Electronics & Communication Engineering", True, 2),
            ("EC501", "Microprocessors & Microcontrollers", "Electronics & Communication Engineering", False, 4),
            ("EC502", "Communication Engineering", "Electronics & Communication Engineering", False, 4),
        ]
        subject_objs = {}
        for code, name, dept, is_lab, cred in subject_data:
            sub = Subject(code=code, name=name, department=dept, is_lab=is_lab, credits=cred)
            db.add(sub)
            db.flush()
            subject_objs[name] = sub

        print("6. Mapping Faculty Subject Qualifications...")
        qual_mappings = [
            ("rajesh.kumar@classswap.edu", ["Data Structures & Algorithms", "Data Structures Lab", "Object Oriented Programming (Java)"]),
            ("anita.sharma@classswap.edu", ["Database Management Systems", "Database & Networks Lab", "Software Engineering"]),
            ("vikram.singh@classswap.edu", ["Computer Networks", "Database & Networks Lab", "Operating Systems"]),
            ("priya.nair@classswap.edu", ["Operating Systems", "Data Structures & Algorithms", "Data Structures Lab"]),
            ("suresh.menon@classswap.edu", ["Machine Learning & AI", "Data Structures & Algorithms"]),
            ("deepa.iyer@classswap.edu", ["Cloud Computing", "Computer Networks"]),
            ("rahul.joshi@classswap.edu", ["Object Oriented Programming (Java)", "Software Engineering"]),
            ("pooja.mehta@classswap.edu", ["Software Engineering", "Database Management Systems"]),
            ("neha.gupta@classswap.edu", ["Machine Learning & AI", "Data Structures & Algorithms"]),
            ("arun.patel@classswap.edu", ["Digital Electronics", "Digital Electronics Lab", "Microprocessors & Microcontrollers"]),
            ("kavita.reddy@classswap.edu", ["Microprocessors & Microcontrollers", "Digital Electronics Lab"]),
            ("manoj.verma@classswap.edu", ["Signals & Systems", "Analog Circuits"]),
            ("sunita.deshmukh@classswap.edu", ["Communication Engineering", "Signals & Systems"]),
            ("amit.bhatt@classswap.edu", ["Analog Circuits", "Signals & Systems"]),
            ("sanjay.rao@classswap.edu", ["Digital Electronics", "Analog Circuits"]),
        ]
        for email, sub_names in qual_mappings:
            fac = faculty_objs[email]
            for sname in sub_names:
                sub = subject_objs[sname]
                db.add(FacultySubject(faculty_id=fac.id, subject_id=sub.id, experience_years=4))

        print("7. Generating Realistic Weekly Timetable...")
        # Period 3 on Monday & Tuesday is carefully arranged:
        # Dr. Rajesh Kumar teaches Data Structures in LH-101 to CSE-A (3rd Sem)
        # Dr. Priya Nair, Dr. Anita Sharma, and Prof. Vikram Singh are FREE in Period 3!
        # This provides the exact substitution recommendation testbed.
        timetable_entries = [
            # Monday
            ("CSE-A (3rd Sem)", "Data Structures & Algorithms", "rajesh.kumar@classswap.edu", "LH-101", "Monday", 3),
            ("CSE-A (3rd Sem)", "Database Management Systems", "anita.sharma@classswap.edu", "LH-101", "Monday", 1),
            ("CSE-A (3rd Sem)", "Object Oriented Programming (Java)", "rahul.joshi@classswap.edu", "LH-101", "Monday", 2),
            ("CSE-B (3rd Sem)", "Database Management Systems", "pooja.mehta@classswap.edu", "LH-102", "Monday", 1),
            ("CSE-B (3rd Sem)", "Data Structures & Algorithms", "neha.gupta@classswap.edu", "LH-102", "Monday", 2),
            ("CSE-A (5th Sem)", "Computer Networks", "vikram.singh@classswap.edu", "LH-201", "Monday", 2),
            ("CSE-A (5th Sem)", "Operating Systems", "deepa.iyer@classswap.edu", "LH-201", "Monday", 4),
            ("CSE-A (7th Sem)", "Machine Learning & AI", "suresh.menon@classswap.edu", "LH-202", "Monday", 1),
            ("ECE-A (3rd Sem)", "Digital Electronics", "arun.patel@classswap.edu", "CR-301", "Monday", 1),
            ("ECE-A (3rd Sem)", "Signals & Systems", "manoj.verma@classswap.edu", "CR-301", "Monday", 2),
            ("ECE-B (5th Sem)", "Microprocessors & Microcontrollers", "kavita.reddy@classswap.edu", "CR-302", "Monday", 3),

            # Tuesday
            ("CSE-A (3rd Sem)", "Data Structures & Algorithms", "rajesh.kumar@classswap.edu", "LH-101", "Tuesday", 3),
            ("CSE-A (3rd Sem)", "Data Structures Lab", "priya.nair@classswap.edu", "CS-LAB-1", "Tuesday", 5),
            ("CSE-A (3rd Sem)", "Data Structures Lab", "priya.nair@classswap.edu", "CS-LAB-1", "Tuesday", 6),
            ("CSE-B (3rd Sem)", "Object Oriented Programming (Java)", "rahul.joshi@classswap.edu", "LH-102", "Tuesday", 2),
            ("CSE-A (5th Sem)", "Software Engineering", "pooja.mehta@classswap.edu", "LH-201", "Tuesday", 1),
            ("CSE-A (5th Sem)", "Computer Networks", "vikram.singh@classswap.edu", "LH-201", "Tuesday", 2),
            ("ECE-A (3rd Sem)", "Digital Electronics Lab", "arun.patel@classswap.edu", "ECE-LAB-1", "Tuesday", 4),
            ("ECE-A (3rd Sem)", "Digital Electronics Lab", "arun.patel@classswap.edu", "ECE-LAB-1", "Tuesday", 5),

            # Wednesday
            ("CSE-A (3rd Sem)", "Database Management Systems", "anita.sharma@classswap.edu", "LH-101", "Wednesday", 1),
            ("CSE-A (3rd Sem)", "Data Structures & Algorithms", "rajesh.kumar@classswap.edu", "LH-101", "Wednesday", 2),
            ("CSE-B (3rd Sem)", "Data Structures & Algorithms", "neha.gupta@classswap.edu", "LH-102", "Wednesday", 3),
            ("CSE-A (5th Sem)", "Operating Systems", "priya.nair@classswap.edu", "LH-201", "Wednesday", 1),
            ("CSE-A (7th Sem)", "Cloud Computing", "deepa.iyer@classswap.edu", "LH-202", "Wednesday", 2),
            ("ECE-B (5th Sem)", "Communication Engineering", "sunita.deshmukh@classswap.edu", "CR-302", "Wednesday", 1),

            # Thursday
            ("CSE-A (3rd Sem)", "Object Oriented Programming (Java)", "rahul.joshi@classswap.edu", "LH-101", "Thursday", 1),
            ("CSE-A (3rd Sem)", "Data Structures & Algorithms", "rajesh.kumar@classswap.edu", "LH-101", "Thursday", 4),
            ("CSE-A (5th Sem)", "Computer Networks", "vikram.singh@classswap.edu", "LH-201", "Thursday", 3),
            ("ECE-A (3rd Sem)", "Signals & Systems", "manoj.verma@classswap.edu", "CR-301", "Thursday", 2),

            # Friday
            ("CSE-A (3rd Sem)", "Database Management Systems", "anita.sharma@classswap.edu", "LH-101", "Friday", 2),
            ("CSE-B (3rd Sem)", "Data Structures & Algorithms", "neha.gupta@classswap.edu", "LH-102", "Friday", 1),
            ("CSE-A (5th Sem)", "Operating Systems", "priya.nair@classswap.edu", "LH-201", "Friday", 3),
            ("ECE-B (5th Sem)", "Microprocessors & Microcontrollers", "kavita.reddy@classswap.edu", "CR-302", "Friday", 2),
        ]

        for sname, subname, femail, rname, day, pno in timetable_entries:
            db.add(Timetable(
                section_id=section_objs[sname].id,
                subject_id=subject_objs[subname].id,
                faculty_id=faculty_objs[femail].id,
                room_id=room_objs[rname].id,
                day_of_week=day,
                period_no=pno
            ))
        db.flush()

        print("8. Seeding Historical Substitutions demonstrating Fairness & Idle Hours...")
        # Create a few prior completed substitutions in current month
        # Vikram Singh has 2 completed substitutions (Fairness lower)
        # Anita Sharma has 1 completed substitution (Fairness medium)
        # Priya Nair has 0 completed substitutions (Fairness highest!)
        today = date.today()
        prev_date_1 = today - timedelta(days=5)
        prev_date_2 = today - timedelta(days=8)

        # Absence 1: Neha Gupta was absent last week
        abs1 = Absence(
            faculty_id=faculty_objs["neha.gupta@classswap.edu"].id,
            date=prev_date_1,
            period_no=1,
            reason="Medical Checkup",
            status=AbsenceStatus.ARRANGED.value
        )
        db.add(abs1)
        db.flush()

        tt1 = db.query(Timetable).filter(
            Timetable.faculty_id == faculty_objs["neha.gupta@classswap.edu"].id,
            Timetable.period_no == 1
        ).first()

        sub1 = Substitution(
            absence_id=abs1.id,
            timetable_id=tt1.id if tt1 else 1,
            substitute_id=faculty_objs["vikram.singh@classswap.edu"].id,
            room_id=room_objs["LH-102"].id,
            status=SubstitutionStatus.ACCEPTED.value,
            score=0.88,
            subject_match_score=0.5,
            fairness_score=1.0,
            dept_match_score=1.0,
            notes="Covered successfully"
        )
        db.add(sub1)
        db.flush()

        # Absence 2: Deepa Iyer was absent
        abs2 = Absence(
            faculty_id=faculty_objs["deepa.iyer@classswap.edu"].id,
            date=prev_date_2,
            period_no=4,
            reason="Attending IEEE Conference",
            status=AbsenceStatus.ARRANGED.value
        )
        db.add(abs2)
        db.flush()

        tt2 = db.query(Timetable).filter(
            Timetable.faculty_id == faculty_objs["deepa.iyer@classswap.edu"].id,
            Timetable.period_no == 4
        ).first()

        sub2 = Substitution(
            absence_id=abs2.id,
            timetable_id=tt2.id if tt2 else 2,
            substitute_id=faculty_objs["vikram.singh@classswap.edu"].id,
            room_id=room_objs["LH-201"].id,
            status=SubstitutionStatus.ACCEPTED.value,
            score=0.92,
            subject_match_score=0.5,
            fairness_score=1.0,
            dept_match_score=1.0,
            notes="Covered successfully"
        )
        db.add(sub2)

        # Absence 3: Pooja Mehta was absent, covered by Anita Sharma
        abs3 = Absence(
            faculty_id=faculty_objs["pooja.mehta@classswap.edu"].id,
            date=prev_date_1,
            period_no=1,
            reason="Personal Emergency",
            status=AbsenceStatus.ARRANGED.value
        )
        db.add(abs3)
        db.flush()

        tt3 = db.query(Timetable).filter(
            Timetable.faculty_id == faculty_objs["pooja.mehta@classswap.edu"].id,
            Timetable.period_no == 1
        ).first()

        sub3 = Substitution(
            absence_id=abs3.id,
            timetable_id=tt3.id if tt3 else 3,
            substitute_id=faculty_objs["anita.sharma@classswap.edu"].id,
            room_id=room_objs["LH-102"].id,
            status=SubstitutionStatus.ACCEPTED.value,
            score=0.95,
            subject_match_score=1.0,
            fairness_score=1.0,
            dept_match_score=1.0,
            notes="Subject match direct coverage"
        )
        db.add(sub3)

        # 9. Create a pending substitution request for demonstration
        # So when Dr. Priya Nair logs in, she sees a pending request!
        abs4 = Absence(
            faculty_id=faculty_objs["deepa.iyer@classswap.edu"].id,
            date=today,
            period_no=2,
            reason="Family Function",
            status=AbsenceStatus.PROCESSING.value
        )
        db.add(abs4)
        db.flush()

        tt4 = db.query(Timetable).filter(
            Timetable.faculty_id == faculty_objs["deepa.iyer@classswap.edu"].id,
            Timetable.day_of_week == today.strftime("%A"),
            Timetable.period_no == 2
        ).first()

        sub4 = Substitution(
            absence_id=abs4.id,
            timetable_id=tt4.id if tt4 else (tt2.id if tt2 else 1),
            substitute_id=faculty_objs["priya.nair@classswap.edu"].id,
            room_id=room_objs["LH-201"].id,
            status=SubstitutionStatus.PENDING.value,
            score=0.96,
            subject_match_score=0.5,
            fairness_score=1.0,
            dept_match_score=1.0,
            notes="Please cover period 2 today."
        )
        db.add(sub4)

        # Add Notification for Priya Nair
        db.add(Notification(
            user_id=faculty_objs["priya.nair@classswap.edu"].id,
            title="Substitution Request Received",
            message="You have a pending substitution request from HOD for Period 2.",
            link="/faculty/requests"
        ))

        db.commit()
        print("ClassSwap Database successfully seeded with 15 Faculty, 8 Sections, 10 Rooms, and Timetables!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
