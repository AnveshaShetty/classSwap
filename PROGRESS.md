# ClassSwap build progress

## Completed

1. **Project and database foundation** — SQLAlchemy models, PostgreSQL Compose service, Alembic initial migration, transactional CSV seeder, and seed count tests. Commit: `6276730`.
2. **Authentication and role guards** — bcrypt password verification, JWT HTTP-only cookie, `GET /me`, and faculty/HOD/super-admin authorization dependency. Focused tests pass.

## Remaining

3. Timetable views and CSV import validation
4. Absence marking and suggestion ranking
5. Substitution request flow and clash handling
6. Acting admin, whole-day leave, and audit log
7. Dashboard, reports, and UI
8. Setup/demo documentation

Docker was unavailable during milestone 1, so PostgreSQL container startup has not yet been verified.
