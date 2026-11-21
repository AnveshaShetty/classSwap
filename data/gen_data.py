#!/usr/bin/env python3
"""Generate and validate fictional college timetable and substitution seed CSVs."""

import csv
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path


DEPARTMENT = "Computer Science and Design"
DEPARTMENT_CODE = "CSD"
BASE_SEED = 20261120
MAX_SCHEDULE_ATTEMPTS = 250
OUTPUT_DIR = Path(__file__).resolve().parent
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
DAY_PERIODS = {day: (7 if day != "Sat" else 4) for day in DAYS}
PERIOD_SEGMENTS = ((1, 2), (3, 4), (5, 6, 7))
ABSENCE_START = date(2026, 10, 19)
ABSENCE_END = date(2026, 11, 12)


FACULTY = [
    {"name": "Dr. Aditi Rao", "email": "aditi.rao@demo.edu", "role": "hod", "department": DEPARTMENT, "teaches": True},
    {"name": "Dr. Arjun Kulkarni", "email": "arjun.kulkarni@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Prof. Meera Iyer", "email": "meera.iyer@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Dr. Rohan Desai", "email": "rohan.desai@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Prof. Kavya Menon", "email": "kavya.menon@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Dr. Ishaan Kapoor", "email": "ishaan.kapoor@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Dr. Nisha Reddy", "email": "nisha.reddy@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Prof. Vivek Nair", "email": "vivek.nair@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Dr. Tara Banerjee", "email": "tara.banerjee@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Prof. Aditya Joshi", "email": "aditya.joshi@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Dr. Sanjana Pillai", "email": "sanjana.pillai@demo.edu", "role": "faculty", "department": DEPARTMENT, "teaches": True},
    {"name": "Prof. Leela Srinivasan", "email": "leela.srinivasan@demo.edu", "role": "faculty", "department": "Mathematics", "teaches": True},
    {"name": "Principal (Demo)", "email": "principal.demo@demo.edu", "role": "super_admin", "department": "Administration", "teaches": False},
]

TEACHING_EMAILS = [person["email"] for person in FACULTY if person["teaches"]]
HOD_EMAIL = next(person["email"] for person in FACULTY if person["role"] == "hod")
MATH_EMAIL = "leela.srinivasan@demo.edu"

SECTIONS = [
    {"name": "3A", "semester": 3, "strength": 58, "room": "CSD-3A"},
    {"name": "3B", "semester": 3, "strength": 56, "room": "CSD-3B"},
    {"name": "5A", "semester": 5, "strength": 60, "room": "CSD-5A"},
    {"name": "5B", "semester": 5, "strength": 55, "room": "CSD-5B"},
    {"name": "7A", "semester": 7, "strength": 57, "room": "CSD-7A"},
]

ROOMS = [
    {"name": "CSD-3A", "type": "class", "capacity": 60},
    {"name": "CSD-3B", "type": "class", "capacity": 60},
    {"name": "CSD-5A", "type": "class", "capacity": 60},
    {"name": "CSD-5B", "type": "class", "capacity": 60},
    {"name": "CSD-7A", "type": "class", "capacity": 60},
    {"name": "Seminar-201", "type": "class", "capacity": 70},
    {"name": "Tutorial-104", "type": "class", "capacity": 40},
    {"name": "Main-Seminar-Hall", "type": "class", "capacity": 120},
    {"name": "CSD-Lab-1", "type": "lab", "capacity": 60},
    {"name": "CSD-Lab-2", "type": "lab", "capacity": 60},
    {"name": "CSD-Lab-3", "type": "lab", "capacity": 60},
    {"name": "CSD-Lab-4", "type": "lab", "capacity": 60},
]

# (code, subject name, semester, kind, weekly periods, assigned faculty)
COURSES = [
    ("CSD301", "Data Structures and Algorithms", 3, "theory", 4, "arjun.kulkarni@demo.edu"),
    ("CSD302", "Computer Organization and Architecture", 3, "theory", 4, "kavya.menon@demo.edu"),
    ("CSD303", "Object-Oriented Programming", 3, "theory", 3, "ishaan.kapoor@demo.edu"),
    ("CSD304", "Discrete Mathematics", 3, "theory", 3, MATH_EMAIL),
    ("CSD305", "Web Technologies", 3, "theory", 3, "aditya.joshi@demo.edu"),
    ("CSD306", "Engineering Communication", 3, "theory", 2, "nisha.reddy@demo.edu"),
    ("CSD307", "Data Structures Laboratory", 3, "lab", 3, "arjun.kulkarni@demo.edu"),
    ("CSD308", "Digital Systems Laboratory", 3, "lab", 3, "kavya.menon@demo.edu"),
    ("CSD501", "Operating Systems", 5, "theory", 4, "meera.iyer@demo.edu"),
    ("CSD502", "Database Management Systems", 5, "theory", 4, "rohan.desai@demo.edu"),
    ("CSD503", "Computer Networks", 5, "theory", 3, "rohan.desai@demo.edu"),
    ("CSD504", "Theory of Computation", 5, "theory", 3, "nisha.reddy@demo.edu"),
    ("CSD505", "Software Engineering", 5, "theory", 3, HOD_EMAIL),
    ("CSD506", "Probability and Statistics", 5, "theory", 2, MATH_EMAIL),
    ("CSD507", "Operating Systems Laboratory", 5, "lab", 3, "meera.iyer@demo.edu"),
    ("CSD508", "Database and Networks Laboratory", 5, "lab", 3, "sanjana.pillai@demo.edu"),
    ("CSD701", "Machine Learning", 7, "theory", 4, "tara.banerjee@demo.edu"),
    ("CSD702", "Cloud Computing", 7, "theory", 4, "vivek.nair@demo.edu"),
    ("CSD703", "Distributed Systems", 7, "theory", 3, "vivek.nair@demo.edu"),
    ("CSD704", "Cybersecurity Fundamentals", 7, "theory", 3, "tara.banerjee@demo.edu"),
    ("CSD705", "Entrepreneurship in Computing", 7, "theory", 2, HOD_EMAIL),
    ("CSD706", "Capstone Design Project", 7, "theory", 3, "vivek.nair@demo.edu"),
]

RELATED_QUALIFICATIONS = {
    "aditi.rao@demo.edu": {"Entrepreneurship in Computing"},
    "arjun.kulkarni@demo.edu": {"Computer Organization and Architecture"},
    "meera.iyer@demo.edu": {"Computer Networks"},
    "rohan.desai@demo.edu": {"Database and Networks Laboratory"},
    "kavya.menon@demo.edu": {"Data Structures Laboratory"},
    "ishaan.kapoor@demo.edu": {"Web Technologies", "Software Engineering"},
    "nisha.reddy@demo.edu": {"Cybersecurity Fundamentals", "Software Engineering"},
    "vivek.nair@demo.edu": {"Computer Networks"},
    "tara.banerjee@demo.edu": {"Cloud Computing"},
    "aditya.joshi@demo.edu": {"Object-Oriented Programming", "Entrepreneurship in Computing"},
    "sanjana.pillai@demo.edu": {"Operating Systems Laboratory", "Digital Systems Laboratory"},
    MATH_EMAIL: set(),
}

ADMIN_CHAIN = [
    {"department": DEPARTMENT, "position": "HOD", "email": HOD_EMAIL},
    {"department": DEPARTMENT, "position": "Senior Faculty 1", "email": "arjun.kulkarni@demo.edu"},
    {"department": DEPARTMENT, "position": "Senior Faculty 2", "email": "meera.iyer@demo.edu"},
    {"department": DEPARTMENT, "position": "Principal", "email": "principal.demo@demo.edu"},
]


def day_name(value):
    return DAYS[value.weekday()]


def courses_by_name():
    return {
        name: {
            "code": code,
            "name": name,
            "semester": semester,
            "kind": kind,
            "periods": periods,
            "faculty": faculty,
        }
        for code, name, semester, kind, periods, faculty in COURSES
    }


def qualifications():
    by_email = {email: set() for email in TEACHING_EMAILS}
    for _, name, _, _, _, email in COURSES:
        by_email[email].add(name)
    for email, subjects in RELATED_QUALIFICATIONS.items():
        by_email[email].update(subjects)
    return by_email


def make_lessons():
    catalog = courses_by_name()
    lessons = []
    for section in SECTIONS:
        for course in COURSES:
            _, name, semester, kind, periods, faculty = course
            if semester != section["semester"]:
                continue
            block = kind == "lab" or name == "Capstone Design Project"
            occurrences = 1 if block else periods
            for occurrence in range(occurrences):
                lessons.append({
                    "section": section["name"],
                    "subject": name,
                    "faculty": faculty,
                    "duration": periods if block else 1,
                    "block": block,
                    "lab": kind == "lab",
                    "periods_per_week": periods,
                    "occurrence": occurrence,
                    "course": catalog[name],
                })
    return lessons


def longest_run(periods):
    occupied = set(periods)
    longest = 0
    for segment in PERIOD_SEGMENTS:
        run = 0
        for period in segment:
            if period in occupied:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
    return longest


def gap_count(periods):
    occupied = set(periods)
    gaps = 0
    for segment in PERIOD_SEGMENTS:
        used = [period for period in segment if period in occupied]
        if used:
            gaps += used[-1] - used[0] + 1 - len(used)
    return gaps


def make_schedule(seed):
    rng = random.Random(seed)
    section_by_name = {section["name"]: section for section in SECTIONS}
    labs = [room for room in ROOMS if room["type"] == "lab"]
    class_rooms = [room for room in ROOMS if room["type"] == "class" and room["capacity"] >= 55]

    section_slots = set()
    section_subject_days = set()
    faculty_slots = set()
    faculty_daily_count = Counter()
    room_slots = set()
    section_day_periods = defaultdict(set)
    faculty_day_periods = defaultdict(set)
    placed = []
    lessons = make_lessons()
    total_periods = Counter()
    for item in lessons:
        total_periods[item["faculty"]] += item["duration"]

    def room_options(item):
        section = section_by_name[item["section"]]
        if item["lab"]:
            options = labs
        else:
            options = class_rooms
        valid = [
            room for room in options
            if room["capacity"] >= section["strength"]
        ]
        if item["lab"]:
            rng.shuffle(valid)
            return valid
        home = section["room"]
        valid.sort(key=lambda room: (room["name"] != home, room["name"]))
        return valid

    def candidate_slots(item):
        if item["block"]:
            return [(day, 5) for day in DAYS[:5]]
        slots = [
            (day, period)
            for day in DAYS
            for period in range(1, DAY_PERIODS[day] + 1)
        ]
        rng.shuffle(slots)
        return slots

    def can_place(item, day, start, room):
        key = (item["section"], day)
        if (key, item["subject"]) in section_subject_days:
            return False
        periods = range(start, start + item["duration"])
        if any(period > DAY_PERIODS[day] for period in periods):
            return False
        if item["lab"] and (day == "Sat" or start < 5 or start + item["duration"] - 1 > 7):
            return False
        if item["block"] and (day == "Sat" or start != 5):
            return False
        if any((item["section"], day, period) in section_slots for period in periods):
            return False
        if any((item["faculty"], day, period) in faculty_slots for period in periods):
            return False
        if any((room["name"], day, period) in room_slots for period in periods):
            return False
        count = faculty_daily_count[(item["faculty"], day)] + item["duration"]
        if count > 5:
            return False
        existing = faculty_day_periods[(item["faculty"], day)]
        if longest_run(existing.union(periods)) > 3:
            return False
        return True

    def placement_score(item, day, start, room):
        periods = set(range(start, start + item["duration"]))
        section_key = (item["section"], day)
        old_section = section_day_periods[section_key]
        new_section = old_section | periods
        score = 5 * (gap_count(new_section) - gap_count(old_section))
        if not item["block"]:
            score += 2.2 if start >= 5 else 0
        target = 25 / 6 if item["section"] != "7A" else 19 / 6
        before = len(old_section)
        after = len(new_section)
        score += 0.22 * ((after - target) ** 2 - (before - target) ** 2)
        faculty_key = (item["faculty"], day)
        faculty_before = faculty_daily_count[faculty_key]
        faculty_target = min(4.0, total_periods[item["faculty"]] / 6)
        score += 0.08 * ((faculty_before + item["duration"] - faculty_target) ** 2
                         - (faculty_before - faculty_target) ** 2)
        score += 0.15 if room["name"] != section_by_name[item["section"]]["room"] else 0
        return score + rng.random() * 0.7

    def add(item, day, start, room):
        periods = set(range(start, start + item["duration"]))
        for period in periods:
            section_slots.add((item["section"], day, period))
            faculty_slots.add((item["faculty"], day, period))
            room_slots.add((room["name"], day, period))
            section_day_periods[(item["section"], day)].add(period)
            faculty_day_periods[(item["faculty"], day)].add(period)
        section_subject_days.add(((item["section"], day), item["subject"]))
        faculty_daily_count[(item["faculty"], day)] += item["duration"]
        placed.append({
            "section": item["section"],
            "day": day,
            "periods": tuple(sorted(periods)),
            "subject": item["subject"],
            "faculty_email": item["faculty"],
            "room": room["name"],
        })

    def remove(item, day, start, room):
        periods = set(range(start, start + item["duration"]))
        for period in periods:
            section_slots.remove((item["section"], day, period))
            faculty_slots.remove((item["faculty"], day, period))
            room_slots.remove((room["name"], day, period))
            section_day_periods[(item["section"], day)].remove(period)
            faculty_day_periods[(item["faculty"], day)].remove(period)
        section_subject_days.remove(((item["section"], day), item["subject"]))
        faculty_daily_count[(item["faculty"], day)] -= item["duration"]
        placed.pop()

    def order_key(item):
        block_rank = 0 if item["block"] else 1
        return (
            block_rank,
            -item["periods_per_week"],
            -total_periods[item["faculty"]],
            item["section"],
            item["subject"],
            item["occurrence"],
        )

    lessons.sort(key=order_key)
    # Shuffle equivalent lessons so retries explore different legal placements.
    ordered = []
    index = 0
    while index < len(lessons):
        end = index + 1
        while end < len(lessons) and order_key(lessons[end])[:-1] == order_key(lessons[index])[:-1]:
            end += 1
        group = lessons[index:end]
        rng.shuffle(group)
        ordered.extend(group)
        index = end

    search_nodes = [0]
    search_limit = 1800

    def search(index):
        if index == len(ordered):
            return True
        search_nodes[0] += 1
        if search_nodes[0] > search_limit:
            return False
        item = ordered[index]
        options = []
        for day, start in candidate_slots(item):
            for room in room_options(item):
                if can_place(item, day, start, room):
                    options.append((placement_score(item, day, start, room), day, start, room))
        if not options:
            return False
        options.sort(key=lambda option: option[0])
        # A small backtracking window avoids committing to an early slot that
        # blocks a later lab, faculty day limit, or constrained 4-period course.
        for _, day, start, room in options[:8]:
            add(item, day, start, room)
            if search(index + 1):
                return True
            remove(item, day, start, room)
        return False

    if not search(0):
        return None

    rows = []
    for meeting in placed:
        for period in meeting["periods"]:
            rows.append({
                "section": meeting["section"],
                "day": meeting["day"],
                "period": period,
                "subject": meeting["subject"],
                "faculty_email": meeting["faculty_email"],
                "room": meeting["room"],
            })
    rows.sort(key=lambda row: (DAYS.index(row["day"]), row["period"], row["section"]))
    return rows


def schedule_gaps(rows):
    by_section_day = defaultdict(set)
    for row in rows:
        by_section_day[(row["section"], row["day"])].add(row["period"])
    return sum(gap_count(periods) for periods in by_section_day.values())


def make_absences(rows, quals, seed):
    rng = random.Random(seed)
    eligible_dates = []
    current = ABSENCE_START
    while current <= ABSENCE_END:
        if current.weekday() != 6:
            eligible_dates.append(current)
        current += timedelta(days=1)
    selected_dates = sorted(rng.sample(eligible_dates, 20))

    schedule_at = defaultdict(list)
    for row in rows:
        schedule_at[(row["day"], row["period"])].append(row)
    substitute_counts = Counter()
    absences = []
    substitutions = []
    reason_cycle = [
        "Medical leave", "Conference", "Personal work", "Training programme",
    ]

    for index, absent_date in enumerate(selected_dates, start=1):
        day = day_name(absent_date)
        candidates = []
        for row in schedule_at.items():
            (scheduled_day, period), entries = row
            if scheduled_day != day:
                continue
            for entry in entries:
                subject_qualified = [
                    email for email in TEACHING_EMAILS
                    if email != entry["faculty_email"]
                    and entry["subject"] in quals[email]
                    and not any(
                        occupied["faculty_email"] == email
                        for occupied in schedule_at[(day, period)]
                    )
                ]
                available = [
                    email for email in TEACHING_EMAILS
                    if email != entry["faculty_email"]
                    and not any(
                        occupied["faculty_email"] == email
                        for occupied in schedule_at[(day, period)]
                    )
                ]
                subs = subject_qualified or available
                if subs:
                    candidates.append((entry, period, subs))
        if not candidates:
            raise RuntimeError("No free substitute candidate for " + absent_date.isoformat())
        rng.shuffle(candidates)
        # Choose a random lesson from options whose best-qualified candidate
        # currently has the smallest substitution count.
        lowest_count = min(min(substitute_counts[email] for email in option[2]) for option in candidates)
        candidates = [
            option for option in candidates
            if min(substitute_counts[email] for email in option[2]) == lowest_count
        ]
        entry, period, subs = rng.choice(candidates)
        sub_email = min(subs, key=lambda email: (substitute_counts[email], rng.random()))
        substitute_counts[sub_email] += 1
        absence_id = "ABS%03d" % index
        absences.append({
            "id": absence_id,
            "faculty_email": entry["faculty_email"],
            "date": absent_date.isoformat(),
            "period_no": period,
            "section": entry["section"],
            "subject": entry["subject"],
            "reason": reason_cycle[(index - 1) % len(reason_cycle)],
        })
        substitutions.append({
            "absence_id": absence_id,
            "substitute_email": sub_email,
            "date": absent_date.isoformat(),
            "period_no": period,
            "status": "accepted",
        })
    return absences, substitutions


def validation_failures(data):
    rows = data["timetable"]
    failures = {}

    def record(name, bad_rows):
        failures[name] = list(bad_rows)

    faculty_collisions = defaultdict(list)
    room_collisions = defaultdict(list)
    section_collisions = defaultdict(list)
    for row in rows:
        key = (row["day"], row["period"])
        faculty_collisions[(row["faculty_email"],) + key].append(row)
        room_collisions[(row["room"],) + key].append(row)
        section_collisions[(row["section"],) + key].append(row)
    record("1. Faculty timetable clashes", [
        group for group in faculty_collisions.values() if len(group) > 1
    ])
    record("2. Room timetable clashes", [
        group for group in room_collisions.values() if len(group) > 1
    ])
    record("3. Section timetable clashes", [
        group for group in section_collisions.values() if len(group) > 1
    ])

    by_section_subject_day = defaultdict(list)
    by_section_subject = defaultdict(list)
    for row in rows:
        by_section_subject_day[(row["section"], row["subject"], row["day"])].append(row)
        by_section_subject[(row["section"], row["subject"])].append(row)
    course_kind = {name: kind for _, name, _, kind, _, _ in COURSES}
    duplicate_subjects = [
        group for (section_name, subject, _), group in by_section_subject_day.items()
        if course_kind[subject] == "theory" and subject != "Capstone Design Project" and len(group) > 1
    ]
    for course in COURSES:
        _, subject, semester, kind, periods, _ = course
        for section in SECTIONS:
            if section["semester"] != semester:
                continue
            subject_rows = by_section_subject[(section["name"], subject)]
            if kind == "theory" and subject != "Capstone Design Project" and periods == 4:
                days = {row["day"] for row in subject_rows}
                if len(days) != 4:
                    duplicate_subjects.append({
                        "section": section["name"], "subject": subject,
                        "days": sorted(days), "expected_distinct_days": 4,
                    })
            if kind == "lab":
                sessions = defaultdict(list)
                for row in subject_rows:
                    sessions[(row["day"], row["faculty_email"], row["room"])].append(row["period"])
                if len(sessions) != 1 or any(sorted(periods_in_session) != [5, 6, 7]
                                              for periods_in_session in sessions.values()):
                    duplicate_subjects.append({
                        "section": section["name"], "subject": subject,
                        "rows": subject_rows, "expected": "single weekday block at periods 5-7",
                    })
            if subject == "Capstone Design Project":
                periods_by_day = defaultdict(list)
                for row in subject_rows:
                    periods_by_day[row["day"]].append(row["period"])
                if len(periods_by_day) != 1 or any(
                    sorted(values) != [5, 6, 7] for values in periods_by_day.values()
                ):
                    duplicate_subjects.append({
                        "section": section["name"], "subject": subject,
                        "rows": subject_rows, "expected": "single three-period weekday project block",
                    })
    record("4. Subject/day and block rules", duplicate_subjects)

    faculty_daily = defaultdict(set)
    faculty_weekly = Counter()
    for row in rows:
        faculty_daily[(row["faculty_email"], row["day"])].add(row["period"])
        faculty_weekly[row["faculty_email"]] += 1
    daily_load_failures = []
    for (email, day), periods in faculty_daily.items():
        if len(periods) > 5 or longest_run(periods) > 3:
            daily_load_failures.append({
                "faculty_email": email, "day": day, "periods": sorted(periods),
                "daily_count": len(periods), "longest_run": longest_run(periods),
            })
    record("5. Faculty daily load / consecutive periods", daily_load_failures)

    by_section_subject_count = Counter(
        (row["section"], row["subject"]) for row in rows
    )
    period_failures = []
    for section in SECTIONS:
        for _, subject, semester, _, periods, _ in COURSES:
            if section["semester"] == semester:
                actual = by_section_subject_count[(section["name"], subject)]
                if actual != periods:
                    period_failures.append({
                        "section": section["name"], "subject": subject,
                        "expected_periods": periods, "actual_periods": actual,
                    })
    record("6. Weekly subject periods", period_failures)

    weekly_load_failures = []
    for email in TEACHING_EMAILS:
        load = faculty_weekly[email]
        if load > 15 or (load < 6 and email != HOD_EMAIL):
            weekly_load_failures.append({
                "faculty_email": email, "periods": load,
                "minimum": 0 if email == HOD_EMAIL else 6, "maximum": 15,
            })
    record("7. Weekly faculty load", weekly_load_failures)

    absence_failures = []
    timetable_lookup = {
        (row["day"], row["period"], row["section"], row["subject"], row["faculty_email"])
        for row in rows
    }
    absence_by_id = {absence["id"]: absence for absence in data["absences"]}
    substitution_by_id = {sub["absence_id"]: sub for sub in data["substitutions"]}
    if len(data["absences"]) != 20 or len(absence_by_id) != 20:
        absence_failures.append({"expected_unique_absences": 20, "actual": len(absence_by_id)})
    if len(data["substitutions"]) != 20 or set(absence_by_id) != set(substitution_by_id):
        absence_failures.append({"absences": len(absence_by_id), "substitutions": len(substitution_by_id)})
    absent_dates = set()
    for absence in data["absences"]:
        absent_date = date.fromisoformat(absence["date"])
        day = day_name(absent_date)
        absent_dates.add(absence["date"])
        key = (day, absence["period_no"], absence["section"], absence["subject"], absence["faculty_email"])
        if not (ABSENCE_START <= absent_date <= ABSENCE_END) or absent_date.weekday() == 6 or key not in timetable_lookup:
            absence_failures.append({"absence": absence, "issue": "not a valid scheduled absence"})
        sub = substitution_by_id.get(absence["id"])
        if sub is None:
            continue
        sub_email = sub["substitute_email"]
        busy = any(
            row["faculty_email"] == sub_email
            and row["day"] == day
            and row["period"] == absence["period_no"]
            for row in rows
        )
        absent_same_date = any(
            other["faculty_email"] == sub_email and other["date"] == absence["date"]
            for other in data["absences"]
        )
        if busy or absent_same_date or sub_email == absence["faculty_email"]:
            absence_failures.append({
                "absence": absence, "substitution": sub,
                "issue": "substitute is busy, absent, or the absent faculty",
            })
        if sub["status"] != "accepted" or sub["date"] != absence["date"] or sub["period_no"] != absence["period_no"]:
            absence_failures.append({"absence": absence, "substitution": sub, "issue": "invalid accepted substitute"})
    if len(absent_dates) != 20:
        absence_failures.append({"unique_absence_dates": len(absent_dates), "expected": 20})
    record("8. Absence/substitute consistency", absence_failures)

    qualifications_by_email = defaultdict(set)
    for row in data["faculty_subjects"]:
        qualifications_by_email[row["faculty_email"]].add(row["subject"])
    qualification_failures = []
    for email in TEACHING_EMAILS:
        count = len(qualifications_by_email[email])
        if count < 2 or count > 4:
            qualification_failures.append({"faculty_email": email, "subject_count": count})
    if qualifications_by_email[MATH_EMAIL] - {
        "Discrete Mathematics", "Probability and Statistics"
    }:
        qualification_failures.append({
            "faculty_email": MATH_EMAIL,
            "subjects": sorted(qualifications_by_email[MATH_EMAIL]),
            "issue": "Maths faculty must only qualify for Maths subjects",
        })
    record("9. Faculty subject qualifications", qualification_failures)
    return failures


def build_data(seed):
    quals = qualifications()
    rows = make_schedule(seed)
    if rows is None:
        return None
    absences, substitutions = make_absences(rows, quals, seed + 991)
    faculty_subject_rows = [
        {"faculty_email": email, "subject": subject}
        for email, subjects in quals.items()
        for subject in sorted(subjects)
    ]
    allocation_rows = []
    for section in SECTIONS:
        for _, subject, semester, _, _, email in COURSES:
            if section["semester"] == semester:
                allocation_rows.append({
                    "faculty_email": email,
                    "semester": semester,
                    "section": section["name"],
                    "subject": subject,
                })
    return {
        "faculty": FACULTY,
        "rooms": ROOMS,
        "sections": [
            {"name": section["name"], "semester": section["semester"], "strength": section["strength"]}
            for section in SECTIONS
        ],
        "subjects": [
            {"name": name, "department": DEPARTMENT, "kind": kind}
            for _, name, _, kind, _, _ in COURSES
        ],
        "allocations": allocation_rows,
        "faculty_subjects": faculty_subject_rows,
        "timetable": rows,
        "admin_chain": ADMIN_CHAIN,
        "absences": absences,
        "substitutions": substitutions,
    }


HEADERS = {
    "faculty": ["name", "email", "role", "department", "teaches"],
    "rooms": ["name", "type", "capacity"],
    "sections": ["name", "semester", "strength"],
    "subjects": ["name", "department", "kind"],
    "allocations": ["faculty_email", "semester", "section", "subject"],
    "faculty_subjects": ["faculty_email", "subject"],
    "timetable": ["section", "day", "period", "subject", "faculty_email", "room"],
    "admin_chain": ["department", "position", "email"],
    "absences": ["id", "faculty_email", "date", "period_no", "section", "subject", "reason"],
    "substitutions": ["absence_id", "substitute_email", "date", "period_no", "status"],
}


def write_csvs(data):
    for name, headers in HEADERS.items():
        path = OUTPUT_DIR / (name + ".csv")
        with path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data[name])


def print_grid(rows, section_name="3A"):
    print("\nWeekly grid for section %s (breaks after P2 and P4):" % section_name)
    lookup = {(row["day"], row["period"]): row for row in rows if row["section"] == section_name}
    for day in DAYS:
        cells = []
        for period in range(1, DAY_PERIODS[day] + 1):
            row = lookup.get((day, period))
            label = row["subject"] if row else "FREE"
            cells.append("P%d %s" % (period, label))
        print("%s: %s" % (day, " | ".join(cells)))


def print_summary(data, seed, failures):
    print("Seed: %d" % seed)
    print("Row counts:")
    for name in HEADERS:
        print("  %-18s %d" % (name + ".csv", len(data[name])))

    faculty_weekly = Counter(row["faculty_email"] for row in data["timetable"])
    print("\nFaculty weekly teaching load (out of 39 periods):")
    for faculty in FACULTY:
        email = faculty["email"]
        periods = faculty_weekly[email]
        print("  %-34s %2d taught, %2d free" % (faculty["name"], periods, 39 - periods))

    print_grid(data["timetable"])
    print("\nValidation result:")
    if not any(failures.values()):
        print("PASS (all hard constraints and seed-data consistency checks)")
        print("Section timetable gaps (breaks excluded): %d" % schedule_gaps(data["timetable"]))
    else:
        for name, bad_rows in failures.items():
            if bad_rows:
                print("FAIL - %s (%d failing rows)" % (name, len(bad_rows)))
                for row in bad_rows:
                    print("  %r" % (row,))


def main():
    best = None
    best_seed = None
    best_gap_count = None
    for attempt in range(MAX_SCHEDULE_ATTEMPTS):
        seed = BASE_SEED + attempt
        data = build_data(seed)
        if data is None:
            continue
        failures = validation_failures(data)
        if any(failures.values()):
            continue
        gaps = schedule_gaps(data["timetable"])
        if best is None or gaps < best_gap_count:
            best, best_seed, best_gap_count = data, seed, gaps
        # Continue a short reproducible search to retain the lower-gap valid result.
        if best_gap_count == 0:
            break
    if best is None:
        raise SystemExit("Unable to generate a valid timetable after %d seeded attempts." % MAX_SCHEDULE_ATTEMPTS)
    write_csvs(best)
    print_summary(best, best_seed, validation_failures(best))
    print("Assumptions:")
    print("  * Faculty total 12 includes 11 CSD staff (including the HOD) and one Mathematics instructor; Principal is an additional non-teaching user.")
    print("  * 3rd/5th semester sections use six theory subjects (19 periods) and two 3-period labs; 7th semester uses five theory subjects and one 3-period capstone project.")
    print("  * The 4-period daily-run limit treats the scheduled breaks as run boundaries; the project block, like a lab, is placed in weekday periods 5-7.")
    print("  * Each accepted substitution covers one class period; all absences are dated on 20 distinct non-Sunday dates in the requested range.")


if __name__ == "__main__":
    main()
