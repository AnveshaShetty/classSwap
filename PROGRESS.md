# ClassSwap build progress

## Completed

1. **Project and database foundation** — SQLAlchemy models, PostgreSQL Compose service, Alembic initial migration, transactional CSV seeder, and seed count tests. Commit: `6276730`.
2. **Authentication and role guards** — bcrypt password verification, JWT HTTP-only cookie, `GET /me`, and faculty/HOD/super-admin authorization dependency. Focused tests pass.
3. **Timetable and CSV import** — authenticated weekly grid with section/faculty filters and accepted-cover badges; HOD/super-admin CSV import validates row numbers and applies valid files transactionally. Focused tests pass.
4. **Absence marking and suggestions** — validates scheduled absences and ranks up to three free, qualified substitutes using configurable scoring and break-aware adjacent load. Unit and integration tests cover eligibility and active substitution exclusions.

## Remaining

5. Substitution request flow and clash handling
6. Acting admin, whole-day leave, and audit log
7. Dashboard, reports, and UI
8. Setup/demo documentation

Docker was unavailable during milestone 1, so PostgreSQL container startup has not yet been verified.
