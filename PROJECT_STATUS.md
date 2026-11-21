# ClassSwap project status

Updated: 21 November 2026

## What the application does

ClassSwap is a department timetable and substitute-coordination application. Faculty can record an absence for a scheduled class, review ranked eligible substitutes, request cover, and respond to substitution requests. Administrators can manage the acting-admin chain, record whole-day leave, import timetables, and review operational reports.

The UI reads application records from the database. Dashboard counts, tables, and charts are computed from stored absences, timetable entries, faculty, and substitution statuses; no decorative sample metrics or stock images are used.

## Delivery status

| Milestone | Scope | Status |
| --- | --- | --- |
| 1 | Models, PostgreSQL Compose setup, migration, and CSV seeding | Complete · `6276730` |
| 2 | Password authentication, HTTP-only JWT cookie, and role guards | Complete · `75dff0c` |
| 3 | Timetable view, filters, and transactional CSV import | Complete · `26520b1` |
| 4 | Absence recording and ranked substitute suggestions | Complete · `97c3aeb` |
| 5 | Request, inbox, accept/decline, next-candidate offers, and room lookup | Complete · `a0a74dc` |
| 6 | Acting admin, whole-day leave, admin chain, and audit records | Complete · `f117db8` |
| 7 | Dashboard, monthly reporting, and responsive application UI | Complete · current full-suite verification pending |
| 8 | Final setup/demo README and screenshot checklist | Still to be completed |

## Implemented screens

- `/login` — sign-in with the existing JSON authentication endpoint and HTTP-only cookie.
- `/dashboard` — selected-date absences and coverage, pending requests, monthly accepted substitutions, recent accepted-cover trend, substitution distribution, and acting-admin banner.
- `/timetable` — weekly timetable with section/faculty/date filters and an acting-admin-aware timetable import control.
- `/absence/new` — mark scheduled periods absent and continue to suggestions.
- `/absences/{id}/suggestions/view` — ranked eligible faculty, plain-language ranking reasons, and a request action.
- `/requests` — pending inbox with HTMX accept/decline actions and no full-page reload.
- `/reports` — monthly coverage ledger, summary metrics, and CSV download.

The shared layout is responsive and uses a restrained campus-operations visual system: deep teal navigation, light neutral canvas, clear typographic hierarchy, compact status badges, accessible labels, and data-derived CSS bars. It contains no image assets. Tailwind and HTMX are loaded using the project's requested CDN setup; the visual styling itself is maintained in the shared template.
Reports are restricted to the acting admin, HOD, super admin, or an authorized stand-in. A non-admin faculty member can still use their personal dashboard and request inbox.

## API additions

- `GET /stats/dashboard?date=YYYY-MM-DD` — dashboard aggregates from stored records.
- `GET /reports/monthly?month=YYYY-MM` — downloadable monthly CSV.
- `GET /dashboard`, `GET /reports` — authenticated HTML views.
- `GET /login`, `GET /absence/new`, `GET /requests`, and the suggestions view route — authenticated application pages, except sign-in.
- `POST /requests/{substitution_id}/respond` — HTMX form endpoint; the existing JSON `PATCH /substitutions/{id}` remains available.
- Existing absence, suggestion, substitution, inbox, room lookup, acting-admin, chain, leave, and timetable-import APIs remain available.

The monthly CSV contains one row per absence and reports its current coverage state. CSV values beginning with spreadsheet formula characters are escaped.

## Metric definitions

- **Covered:** the absence has an accepted substitution.
- **Pending:** an active substitute request is awaiting a response.
- **Uncovered:** there is neither an accepted nor pending request.
- **Classes recovered:** the count of accepted substitute assignments in the selected month. A timetable period's duration is not defined in the data model, so the app does not label these counts as hours.
- **Substitution distribution:** accepted assignments per substitute, calculated for the selected reporting scope and month.

Seed CSV rows are fictional demo records. They are loaded into the database by the seed script; the UI does not fabricate additional activity when records are absent.

## Run locally

1. Copy `.env.example` to `.env` and set a private `JWT_SECRET_KEY`.
2. Install Python dependencies: `python -m pip install -r requirements.txt`.
3. Start the database and app: `docker compose up --build -d`.
4. Load the demo data from the repository root: `python scripts/seed.py`.
5. Open `http://localhost:8000`.

Demo accounts use password `demo123`:

- HOD: `meera.shenoy@demo.edu`
- Faculty: `ravi.kulal@demo.edu`

The compose service applies Alembic migrations during web startup. Seeding refuses to run when users already exist, to avoid duplicate demo records.

## Validation and known limitations

- Run the automated suite with `python -m pytest -q`.
- Python syntax check: `python -m compileall -q app tests`.
- The current automated integration suite uses SQLite. PostgreSQL/Docker startup has not been verified in this environment.
- Tailwind's CDN build emits a development-use warning in the browser. A production deployment should compile Tailwind locally and serve the generated assets.
- Request expiry and next-candidate handling are available in the service layer; an expiry scheduler/worker is not configured.
- The final standalone README/demo script and screenshot checklist remain for milestone 8.
