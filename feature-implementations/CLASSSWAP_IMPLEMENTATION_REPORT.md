# ClassSwap implementation report

Updated: 24 November 2026

## What ClassSwap does

ClassSwap helps a college coordinate teaching coverage when a faculty member is absent. It connects the department timetable to eligible substitute suggestions, requests, leave records, administrator coverage, and reports.

The application has a FastAPI backend, SQLAlchemy 2 models, PostgreSQL for the Docker setup, Alembic migrations, and server-rendered Jinja templates. Authentication uses a JWT stored in an HTTP-only cookie. The interface uses HTMX for in-place request responses and responsive CSS for its layout.

Dashboard and report metrics come from saved database records. The seed CSVs contain fictional demo data; the UI does not invent activity to fill empty states.

## Features implemented

### Accounts and authorization

- Sign in with email and password; passwords are stored as bcrypt hashes.
- Successful sign-in sets the `classswap_access` HTTP-only cookie.
- Roles are `faculty`, `hod`, and `super_admin`.
- Department admin duties follow the ordered admin chain and whole-day leave status.
- A stand-in admin can view reports and manage substitution coverage; timetable imports and admin-chain changes require HOD/super-admin permissions.

### Timetable and absences

- View the timetable by day and period, with section, faculty, and coverage-date filters.
- Import a CSV timetable after validating its header, references, qualifications, capacities, and scheduling clashes. Any invalid row prevents the import.
- A faculty member can record an absence only for a class scheduled on that weekday and period.
- HOD absences automatically request the highest-ranked eligible substitute.
- Suggestion ranking considers subject qualification, adjacent load, accepted-substitution fairness, semester, and department.

### Substitution requests and rooms

- Request a substitute from the ranked suggestions.
- Candidates see pending requests in their inbox and can accept or decline.
- Declining offers the next eligible candidate where one is available.
- The service checks schedule/absence conflicts and the database enforces a partial unique constraint for active candidate-slot requests.
- The substitute uses the class's original room by default. A free-room endpoint lists suitable, unoccupied rooms.

### Leave, administration, and auditing

- Record whole-day leave; the application records absences for scheduled classes on that date.
- Resolve the acting admin as the first available person in the department chain, falling back to a super admin if the chain is on leave.
- Read and update the department admin chain with permission checks.
- Timetable imports, admin-chain edits, leave changes, and HOD auto-requests create audit entries.

### Screens and reports

- `/login` — sign in.
- `/dashboard` — selected-date absences, coverage status, pending requests, accepted monthly cover, recent coverage trend, substitution distribution, and acting-admin status.
- `/timetable` — weekly timetable and authorized CSV import.
- `/absence/new` — mark scheduled absences.
- `/absences/{id}/suggestions/view` — compare ranked eligible substitutes and request one.
- `/requests` — accept or decline assignments inline with HTMX.
- `/reports` — monthly absence/coverage ledger, summary, substitute distribution, and CSV export.
- Shared responsive navigation, empty states, loading treatment, custom 404/500 pages, Lucide icons, and an SVG favicon.

## HTTP API

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/auth/login` | Authenticate and set the session cookie |
| `GET` | `/me` | Return the signed-in user |
| `POST` | `/absences` | Record one or more scheduled absences |
| `GET` | `/absences/{absence_id}/suggestions` | Return up to three eligible substitutes |
| `POST` | `/substitutions` | Create a pending substitute request |
| `PATCH` | `/substitutions/{substitution_id}` | Accept or decline a request |
| `GET` | `/substitutions/inbox` | List the signed-in user's pending requests |
| `GET` | `/rooms/free?absence_id=…` | Look up suitable free rooms |
| `POST` | `/leaves` | Record whole-day leave and scheduled absences |
| `DELETE` | `/leaves/{YYYY-MM-DD}` | Cancel whole-day leave |
| `POST` | `/timetable/import` | Validate and import a timetable CSV |
| `GET` | `/admin/acting` | Resolve acting admin |
| `GET` | `/admin/chain` | Read the authorized department admin chain |
| `PUT` | `/admin/chain` | Replace the authorized department admin chain |
| `GET` | `/stats/dashboard` | Return dashboard aggregates as JSON |
| `GET` | `/reports/monthly?month=YYYY-MM` | Download the monthly CSV report |
| `GET` | `/health` | Check application health |

HTML routes are listed in the Screens section. The HTMX form route is `POST /requests/{substitution_id}/respond`.

## API keys and configuration

**No third-party API key is required to run the application.** Authentication is self-hosted with JWT; PostgreSQL is the application's database.

Runtime configuration is in `.env`, based on `.env.example`:

| Variable | Purpose | Local setup |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy database connection | Compose sets this for the web container |
| `JWT_SECRET_KEY` | Signs login tokens | Replace the example with a private, long random value |
| `JWT_ALGORITHM` | JWT signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Login session lifetime | `480` |
| `AUTH_COOKIE_NAME` | Session cookie name | `classswap_access` |
| `COOKIE_SECURE` | Require HTTPS for cookie transmission | `false` for local HTTP; set `true` behind HTTPS |
| `MAX_PERIOD` | Maximum period count | `7` |
| `BREAK_AFTER` | Breaks used in adjacency ranking | `2,4` |
| `SUBJECT_MATCH_WEIGHT` | Suggestion scoring weight | `0.35` |
| `ADJACENT_FREE_WEIGHT` | Suggestion scoring weight | `0.25` |
| `FAIRNESS_WEIGHT` | Suggestion scoring weight | `0.20` |
| `SAME_SEMESTER_WEIGHT` | Suggestion scoring weight | `0.12` |
| `SAME_DEPARTMENT_WEIGHT` | Suggestion scoring weight | `0.08` |
| `POSTGRES_USER` | Local PostgreSQL role | `classswap` |
| `POSTGRES_PASSWORD` | Local PostgreSQL password | `classswap` for local development only |
| `POSTGRES_DB` | Local PostgreSQL database name | `classswap` |

The UI loads Manrope, Lucide icons, and HTMX from public CDNs; these do not require API keys. Faculty portrait URLs are fixed Unsplash image URLs, not an image API integration. The app needs internet access to load these remote assets. For offline/production deployments, serve approved font, icon, and portrait assets locally.

Do not commit a real `.env`, database password, or production JWT secret.

## Database name, schema, and migration files

- **PostgreSQL database name:** `classswap` by default (`POSTGRES_DB`).
- **PostgreSQL schema:** `public`, PostgreSQL's default; the app does not set a custom schema.
- **SQLAlchemy models:** `app/models/entities.py`.
- **Alembic config:** `alembic.ini`.
- **Migration environment and template:** `migrations/env.py` and `migrations/script.py.mako`.
- **Initial migration:** `migrations/versions/7eb7b019f570_initial_schema.py`.
- **Migration version table:** Alembic's `alembic_version`.

Tables created by the model/migration are:

| Table | Contents |
| --- | --- |
| `users` | Faculty and administrator accounts |
| `subjects` | Department subjects and kinds |
| `faculty_subjects` | Subjects faculty are qualified to teach |
| `sections` | Section name, semester, and strength |
| `faculty_allocations` | Current faculty/subject/section assignments |
| `rooms` | Classroom and lab types and capacities |
| `timetable` | Section, subject, faculty, room, weekday, and period slots |
| `absences` | Absent faculty, date, period, class, and reason |
| `substitutions` | Candidate, room, date, period, and request status |
| `leaves` | Whole-day faculty leave keyed by user and date |
| `admin_chain` | Ordered department administrators |
| `audit_log` | Administrative and automated write history |

Use the existing migration for schema changes. Create the next revision from the repository root with:

```powershell
alembic revision --autogenerate -m "describe the schema change"
```

Review the generated migration, then apply with `alembic upgrade head`. Do not manually create a database schema SQL file unless a separate deployment process explicitly requires one.

Seed CSV headers and files are under `seed/`. `scripts/seed.py` loads them in dependency order in one transaction and uses the demo password `demo123`. It refuses to reseed a database that already contains users.

## Run locally

From the project directory (the directory containing `docker-compose.yml`):

```powershell
Copy-Item .env.example .env
# Edit .env and replace JWT_SECRET_KEY with a private random secret.
docker compose up --build -d
python scripts/seed.py
```

Then open `http://localhost:8000`. Demo logins:

- HOD: `meera.shenoy@demo.edu`
- Faculty: `ravi.kulal@demo.edu`
- Password for both: `demo123`

Useful checks:

```powershell
docker compose ps
docker compose logs -f web
python -m pytest -q
```

The web container applies migrations at startup. Docker/PostgreSQL startup has not been verified in the development environment; the automated tests use SQLite.

## Current validation and follow-up

- At the last full milestone-7 run, `python -m pytest -q` passed **39 tests**.
- `python -m compileall -q app tests` passed.
- Docker/PostgreSQL has not been verified here.
- An automatic worker to expire timed-out requests is not configured.
- The product does not yet include every originally scoped admin user-management screen.
- Final dedicated README/demo walkthrough and screenshot checklist remain follow-up documentation.
