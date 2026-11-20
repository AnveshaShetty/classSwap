# ClassSwap

> **"Smart Substitutions. Zero Idle Hours."**  
> *When a faculty member is absent, ClassSwap finds an available substitute and a suitable free classroom within seconds.*

---

## 1. Project Overview

**ClassSwap** is an intelligent college timetable and faculty substitution management platform designed to eliminate wasted class hours when professors are absent unexpectedly.

### The Problem
In most academic institutions, substitution arrangement is still handled manually through chaotic WhatsApp group calls and phone chains every morning. This results in:
- **30+ minute delays** before a replacement is found.
- **Unfair workload distribution**, where cooperative junior faculty are overburdened while others are never contacted.
- **Timetable clashes & room confusion**, with two sections arriving at the same lecture hall or specialized labs remaining locked.

### The ClassSwap Solution
ClassSwap automates the entire substitution and room-finding pipeline using an **intelligent multi-factor recommendation algorithm** that balances **Subject Expertise (50%)**, **Monthly Fairness (30%)**, and **Departmental Specialization (20%)**, along with real-time **Classroom Availability & Capacity Verification**.

---

## 2. Key Features

- **Role-Based Authentication & Access Control**:
  - **HOD / Admin Portal**: Complete college management dashboard, master timetable management, CSV timetable import & conflict validation, faculty absence handling, recommendation engine review, substitution tracking, classroom availability engine, and audit reports.
  - **Faculty Portal**: Daily & weekly teaching schedule, absence submission with period selection, substitution requests with instant **Accept** & **Decline** actions, and historical workload logs.
- **Intelligent Substitute Recommendation Engine**:
  - Implements the exact multi-factor scoring formula:
    $$\text{Final Score} = (0.5 \times \text{Subject Match}) + (0.3 \times \text{Fairness Score}) + (0.2 \times \text{Department Match})$$
  - Real-time normalization preventing bias and ensuring equitable monthly workload distribution.
- **Classroom Availability Engine (Free Room Finder)**:
  - Scans occupied lecture halls and labs for the chosen date and period.
  - Matches room capacity against section student strength.
  - Distinguishes theory classrooms from laboratories to prevent improper room assignments.
- **Date-Specific Timetable Overrides**:
  - When a substitute accepts a class, temporary date-specific overrides are applied without modifying or corrupting the master weekly timetable.
- **Audit Analytics & Monthly Reports**:
  - Computes verified statistics: absences, substitutions arranged, classes saved, and exact **idle hours recovered** (calculated from period duration).
  - One-click **PDF Report Generation** with college header, executive KPIs, and workload tables using ReportLab.
  - One-click **CSV Report Export** for Excel analytics.
- **Instant Hackathon Demo Persona Switcher**:
  - Switch between Admin (HOD) and various Faculty accounts with 1 click from the navigation bar.

---

## 3. Technology Stack

- **Backend**: Python 3.14 / 3.11+, FastAPI, Uvicorn, SQLAlchemy 2.0, Pydantic V2, JWT Authentication (`PyJWT`), direct `bcrypt` password hashing.
- **Database**: SQLite for local development; fully compatible with PostgreSQL for production deployment.
- **Frontend**: Jinja2 Templates, Tailwind CSS (Modern SaaS theme: Deep Navy `#0f172a`, Royal Blue `#2563eb`, Teal `#0d9488`), Lucide Icons, Chart.js.
- **Document & Data Processing**: ReportLab (vector PDF generation), Pandas (CSV imports, previewing, and validation).
- **Testing**: Pytest automated test suite (16 test cases covering auth, recommendation algorithm, room finder, timetable conflict detection, substitution actions, reports, and full 16-step demonstration workflow).

---

## 4. Project Structure

```
Class Swap/
├── backend/
│   ├── app/
│   │   ├── config.py                 # Pydantic Settings & environment variables
│   │   ├── database.py               # SQLAlchemy 2.0 Engine & Session factory
│   │   ├── main.py                   # FastAPI Application & router assembly
│   │   ├── models/                   # SQLAlchemy Database Models
│   │   │   ├── user.py               # User & UserRole
│   │   │   ├── academic.py           # Subject, FacultySubject, Room, Section
│   │   │   ├── timetable.py          # Timetable & PeriodConfig
│   │   │   ├── substitution.py       # Absence, Substitution, DateOverride
│   │   │   └── notification.py       # User notifications
│   │   ├── schemas/                  # Pydantic V2 Request & Response schemas
│   │   │   ├── auth.py
│   │   │   ├── academic.py
│   │   │   ├── timetable.py
│   │   │   ├── substitution.py
│   │   │   └── reports.py
│   │   ├── core/
│   │   │   ├── security.py           # Bcrypt password hashing & JWT token cycle
│   │   │   └── dependencies.py       # Role-based dependency injection
│   │   ├── services/                 # Core Business Logic
│   │   │   ├── recommendation_engine.py  # Intelligent substitute ranking engine
│   │   │   ├── room_finder.py            # Free room & lab allocation engine
│   │   │   ├── timetable_service.py      # CSV validation & date-specific merge
│   │   │   ├── report_service.py         # PDF & CSV analytics generation
│   │   │   └── notification_service.py
│   │   ├── routes/                   # API & Page Routes
│   │   │   ├── auth_routes.py
│   │   │   ├── admin_routes.py
│   │   │   ├── faculty_routes.py
│   │   │   ├── timetable_routes.py
│   │   │   ├── absence_routes.py
│   │   │   ├── substitution_routes.py
│   │   │   ├── room_routes.py
│   │   │   └── report_routes.py
│   │   ├── static/                   # CSS, JS, Assets
│   │   └── templates/                # Jinja2 Templates (Tailwind UI)
│   │       ├── base.html             # Base shell, Toast notifications, Demo switcher
│   │       ├── landing.html          # Public marketing & feature landing page
│   │       ├── login.html            # Sign-in page with 1-click persona fills
│   │       ├── admin/                # 11 Admin dashboard views
│   │       └── faculty/              # 4 Faculty dashboard views
│   └── seed.py                       # Database seeder (15 Faculty, 8 Sections, 10 Rooms)
├── data/
│   └── sample_timetable.csv          # Sample CSV for testing timetable import
├── tests/                            # Comprehensive Pytest Suite
│   ├── conftest.py                   # Isolated in-memory database fixture
│   ├── test_auth.py
│   ├── test_recommendation.py
│   ├── test_room_finder.py
│   ├── test_timetable.py
│   ├── test_substitutions.py
│   ├── test_reports.py
│   ├── test_demo_workflow.py         # Full 16-step presentation test
│   └── test_pages.py                 # HTTP 200 verification for all 15 routes
├── run.py                            # Application startup runner
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment template
├── .gitignore
└── README.md                         # Documentation
```

---

## 5. Installation & Setup Instructions

### Prerequisites
- Python 3.10+ (Tested on Python 3.14)
- Pip package manager

### 1. Clone or Navigate to the Workspace Directory
```bash
cd "C:\Users\ASUS\Desktop\My Projects\Class Swap"
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Initialize & Seed Database
Run the seed script to create all tables and populate realistic demo data:
```bash
python backend/seed.py
```

### 4. Start the ClassSwap Server
```bash
python run.py
```
Or with Uvicorn directly:
```bash
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and visit:  
**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 6. Demo Login Credentials

| Role | Name | Email | Password | Persona & Key Notes |
|---|---|---|---|---|
| **HOD / Admin** | Dr. Arvind Swaminathan | `admin@classswap.edu` | `Admin@123` | Complete College Management & Timetable Override |
| **Faculty (CSE)** | Dr. Rajesh Kumar | `rajesh.kumar@classswap.edu` | `Faculty@123` | Absent Faculty (Data Structures, Tuesday P3) |
| **Faculty (CSE)** | Dr. Priya Nair | `priya.nair@classswap.edu` | `Faculty@123` | Top-Ranked Substitute (0 prior subs, Match: 96%) |
| **Faculty (CSE)** | Dr. Anita Sharma | `anita.sharma@classswap.edu` | `Faculty@123` | Qualified Professor (1 sub completed this month) |
| **Faculty (CSE)** | Prof. Vikram Singh | `vikram.singh@classswap.edu` | `Faculty@123` | Qualified Professor (2 subs completed this month) |
| **Faculty (ECE)** | Dr. Arun Patel | `arun.patel@classswap.edu` | `Faculty@123` | ECE Department Coordinator & Lab Head |

> **Pro Tip**: On the `/login` page and in the top navigation bar, use the **1-Click Demo Persona** buttons to sign in without typing passwords.

---

## 7. The 16-Step Hackathon Demonstration Workflow

Follow this complete walkthrough to showcase the core capabilities to hackathon judges:

1. **Login as Admin**:
   - Go to `http://127.0.0.1:8000/login`.
   - Click **"HOD / Admin Persona"** and click **Sign In**.
2. **Open the Timetable**:
   - In the sidebar, click **Timetable Management**.
   - Notice the weekly timetable grid for `CSE-A (3rd Sem)`.
3. **Select a Faculty Member and Mark them Absent**:
   - Click **Absence Management** in the sidebar.
   - Click **"Mark Faculty Absent"**.
   - Select `Dr. Rajesh Kumar`, select today's date, check `Period 3`, and enter reason: *"Attending University Academic Council Meeting"*.
   - Click **Record Absence**.
4. **View the Affected Class**:
   - The absence entry appears immediately with status badge `Pending Substitute`.
   - The affected class is identified: `Data Structures & Algorithms (CS301)` in `LH-101` for `CSE-A (3rd Sem)`.
5. **Display Ranked Substitute Recommendations**:
   - Click **"Find Substitutes"** next to the absence.
   - The **Multi-Factor Recommendation Engine** modal opens.
6. **Explain Subject Relevance and Fairness Scores**:
   - Inspect the top 3 candidates:
     - **#1 Dr. Priya Nair** (Score: **0.96 / 1.00**): Qualified in Data Structures, has **0 substitutions** this month (Fairness: **1.00**), Department match: **1.00**.
     - **#2 Dr. Anita Sharma** (Score: **0.85 / 1.00**): Related CS area, **1 substitution** completed (Fairness: **0.85**).
     - **#3 Prof. Vikram Singh** (Score: **0.76 / 1.00**): Related CS area, **2 substitutions** completed (Fairness: **0.70**).
   - Point out how the fairness score prevents overburdening faculty.
7. **Display Free Rooms**:
   - In the same modal, view the ranked classrooms:
     - **LH-202 (65 Seats)**: Marked as **Best Fit** (fits section strength of 60).
     - Classroom vs Laboratory checks are automatically enforced.
8. **Send a Substitution Request**:
   - With Dr. Priya Nair and LH-202 selected, click **"Send Substitution Request"**.
   - Status updates to `Pending Approval`.
9. **Logout and Login as Recommended Faculty**:
   - Click **Switch Demo Account** &rarr; Select **Dr. Priya Nair**.
10. **Accept the Request**:
    - On Dr. Priya Nair's dashboard, notice the golden banner: **"Action Required: Substitution Requests Awaiting Your Response"**.
    - Click **"Accept Class"**.
11. **Login Again as Admin**:
    - Click **Demo Switch** &rarr; Select **HOD Admin**.
12. **Verify Substitution is Confirmed**:
    - Open **Substitution Tracking** in the sidebar.
    - Notice the record status is **Accepted & Confirmed** with substitute Dr. Priya Nair and room LH-202.
13. **Verify Date-Specific Timetable is Updated**:
    - Go to **Dashboard** or **Timetable Management**.
    - The date-specific schedule shows Dr. Priya Nair covering the class, while the permanent master timetable remains untouched!
14. **Inspect Updated Dashboard Statistics**:
    - Notice the **Completed Substitutions** counter increased and **Idle Hours Saved** reflects the recovered 50-minute period.
15. **Download Monthly PDF Report**:
    - Click **PDF Report** or visit **Reports & Analytics**.
    - Click **Download PDF** &rarr; ReportLab generates a clean executive document with KPIs, department recovery rates, and faculty workload audits.
16. **Download Monthly CSV Report**:
    - Click **Download CSV** &rarr; Download the spreadsheet export for Excel.

---

## 8. Running Automated Tests

ClassSwap includes 16 automated tests covering every layer of the system:
```bash
python -m pytest tests/ -v
```

### Test Coverage Highlights:
- `test_auth.py`: Password hashing with bcrypt, JWT generation & verification, role checks.
- `test_recommendation.py`: Availability filtering, 0.5/1.0 subject match scoring, fairness score normalization, candidate ranking.
- `test_room_finder.py`: Occupied room exclusion, capacity vs strength scoring, lab vs classroom type matching.
- `test_timetable.py`: CSV parsing, in-batch conflict prevention, missing entity validation.
- `test_substitutions.py`: Request cycle, acceptance, DateOverride generation, master timetable preservation.
- `test_reports.py`: Idle hours calculation, ReportLab PDF generation, CSV generation.
- `test_demo_workflow.py`: Executes the complete 16-step presentation workflow end-to-end.
- `test_pages.py`: HTTP 200 verification across all 11 admin views and 4 faculty views.

---

## 9. Production Deployment Readiness

ClassSwap is designed for straightforward deployment on platforms like Render or Railway:
1. **Database URL**: Set the `DATABASE_URL` environment variable to a PostgreSQL connection string (e.g. `postgresql://user:password@host:port/dbname`).
2. **Secret Key**: Set `SECRET_KEY` in environment variables.
3. **Start Command**:
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 10000
   ```
4. **Build Command**:
   ```bash
   pip install -r requirements.txt && python backend/seed.py
   ```

---

## 10. Summary

ClassSwap delivers a complete, production-grade academic software solution that solves a real administrative problem with mathematical precision, attractive SaaS design, and zero idle hours for students.
