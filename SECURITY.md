# ClassSwap Security

## Phase 0: threat model and baseline audit

This is an initial repository review, not a penetration test or a certification
of OWASP ASVS compliance. Findings are based on the code and checks listed
below, as of 2026-11-24. Do not use real faculty or student data until the
high-risk findings and the residual risks have been addressed and independently
validated.

### Assets

- Faculty, HOD, acting-admin, and super-admin accounts and credentials
- JWT signing keys and browser session cookies
- Timetable integrity, absence records, leave data, and substitution decisions
- Admin-chain membership and acting-admin decisions
- Audit history and operational database contents
- Public timetable availability and the confidentiality of non-public faculty data
- Uploaded CSV data and exported CSV/calendar content

### Actors

- Anonymous visitor or student using public timetable pages
- Authenticated faculty member
- Stand-in acting administrator, HOD, or super administrator
- Malicious or compromised insider
- Automated bot or network attacker
- Compromised dependency publisher, CDN, or deployment host

### Trust boundaries

- Untrusted browser and network traffic ↔ FastAPI routes and authentication
- Route handlers and application services ↔ PostgreSQL or test SQLite database
- Faculty/admin authorization ↔ records selected by client-supplied identifiers
- Uploaded CSV ↔ import parser and persistent timetable data
- Public timetable and export responses ↔ external clients and spreadsheets
- Browser ↔ third-party JavaScript, CSS, and font providers
- Source dependencies and container build ↔ deployed runtime

### Abuse cases

1. A faculty member guesses another faculty member's absence ID and reads
   suggestions or available rooms, or creates/responds to a request for it.
2. A substitution candidate accepts a request addressed to another person.
3. A stand-in or ordinary faculty account invokes a timetable import or changes
   the admin chain through a direct route rather than the UI.
4. A caller supplies another department to retrieve its acting administrator.
5. An attacker uses a known/default signing key to forge a JWT for an admin.
6. A network attacker intercepts a cookie where the app is served over HTTP or
   where the cookie is not marked Secure.
7. An attacker replays an emailed or Telegram action link, scrapes public
   schedules for personal data, or uses a poisoned CSV to alter scheduling data.
8. A compromised CDN script executes in an authenticated browser session.
9. A malicious insider alters audit records or exports formula-active CSV data.

### Phase 0 findings

| # | Severity | File | Lines | Vulnerability | Confidence |
|---|----------|------|-------|---------------|------------|
| 1 | HIGH | `app/config.py`, `docker-compose.yml` | 8; 22 | A known fallback JWT signing key can allow token forgery when deployed without an explicit secret. | 10/10 |
| 2 | MEDIUM | `app/config.py`, `app/routes/auth.py` | 12; 33 | The cookie security setting defaults to false and the default deployment uses HTTP. | 9/10 |
| 3 | MEDIUM | `app/routes/absence.py`, `app/routes/substitution.py`, `app/routes/pages.py`, `app/services/absence.py`, `app/services/suggestion.py` | 46–54; 82–90; 137–145; 102–103; 160–161 | Authenticated routes load absence-related data by ID without consistently checking its owner/department, enabling IDOR/BOLA. | 10/10 |
| 4 | MEDIUM | `app/routes/admin.py` | 31–45 | An authenticated caller can select another department when retrieving its acting administrator. | 9/10 |
| 5 | MEDIUM | `app/templates/base.html` | 13–14 | External JavaScript assets are loaded without Subresource Integrity. | 8/10 |

Planned fixes: fail closed on missing/placeholder signing secrets; enforce
production cookie and transport settings; centralize and enforce object-level
authorization; scope acting-admin lookups; and self-host or integrity-pin
third-party scripts.

## Phase 1: authentication and sessions

**Status: partial.** Implemented production secret validation, a pinned HS256
algorithm, Secure `__Host-` cookies, Argon2id password hashing with bcrypt
rehashing on successful login, generic login errors with a dummy hash check,
database-backed per-account/per-IP lockout, password policy validation and
change, 30-minute sliding sessions with an eight-hour absolute lifetime, and
server-side logout/password-change invalidation via `token_version`. The seed
command is disabled in production; development seed accounts are marked
`must_change_password`. Password-reset tokens are 256-bit random values stored
only as SHA-256 hashes, expire after 15 minutes, are single-use, invalidate
sessions, and are delivered through a fixed-From SMTP message. Production
startup requires SMTP and an HTTPS reset-link origin. HOD and super-admin
accounts must enroll TOTP before using admin features; TOTP secrets are Fernet
encrypted and ten hashed, single-use backup codes are issued at enrollment.
Super admins can force-revoke another account's sessions.

Regression evidence: `test_production_settings_reject_unsafe_jwt_secret`,
`test_login_cookie_is_secure_when_configured`,
`test_unknown_and_known_login_failures_have_same_response`,
`test_login_is_locked_after_five_failures`,
`test_legacy_bcrypt_hash_is_upgraded_after_successful_login`,
`test_logout_invalidates_previously_issued_token`,
`test_password_change_invalidates_old_token`,
`test_reset_token_is_hashed_single_use_and_expires`,
`test_password_reset_request_does_not_disclose_email_existence`,
`test_admin_actions_require_totp_or_a_single_use_backup_code`,
`test_super_admin_can_force_logout_user_with_totp`,
`test_tokens_reject_none_and_non_hs256_algorithms`,
`test_seed_refuses_production_mode`, and
`test_seed_loads_all_csvs_in_dependency_order`. Full suite: 58 passed.

Behavior changes: `/logout` is no longer a state-changing GET; use the POST
`/auth/logout` form. Production now fails closed for missing/placeholder
secrets or insecure cookie configuration. The local `__Host-` cookie is marked
Secure, which requires HTTPS (localhost is typically treated as a secure
context by browsers). Successful password changes revoke existing sessions.
Five failed attempts trigger a 15-minute lockout with exponential backoff.
Admin-only actions require an `X-TOTP-Code` header after enrollment; backup
codes can be used once. Production now also requires SMTP, HTTPS
`APP_BASE_URL`, and a valid `TOTP_ENCRYPTION_KEY`.

Still open in this phase: no implementation items remain. MFA recovery/key
rotation and operational delivery limits remain deployment concerns.

## Phase 2: authorization and object access

**Status: partial.** Added pure policies in `app/core/authorization.py` for
absence ownership, department scope, candidate response ownership, acting
administrator permissions, timetable import, and admin-chain changes.
Absence suggestions, free-room lookup, and the suggestions page now return
not-found responses for records outside the caller's scope. Substitution
responses are restricted to the addressed candidate. Acting-admin permission
checks use an allowlist; stand-ins cannot import timetables or edit the admin
chain. The route-policy regression test requires every API route to either
include the authenticated-user dependency or an explicit public marker.
Input models touched in this phase reject unknown fields and substitution
identifiers must be positive strict integers. Repeated accept/decline and leave
cancellation requests no longer repeat state changes.

Behavior changes: timetable imports and admin-chain edits are now limited to
super administrators (HODs and acting stand-ins receive 403); repeating an
already completed substitution response with the same status returns the
existing result; repeating a leave cancellation returns 204 without changing
data. Non-super-admin users can no longer backdate absences or whole-day leave,
and candidates with five pending substitution requests are excluded from
additional assignments.

Regression evidence: `test_every_route_declares_authentication_or_public_policy`,
`test_acting_admin_permissions_are_allowlisted`,
`test_absence_ids_are_hidden_from_another_faculty_member`,
`test_substitution_response_is_hidden_from_non_candidate`,
`test_absence_create_rejects_mass_assignment`,
`test_faculty_cannot_mark_past_absence`,
`test_candidate_pending_request_limit_is_enforced`,
`test_stand_in_admin_cannot_import_timetable`,
`test_acting_hod_cannot_edit_admin_chain`,
`test_substitution_request_can_be_accepted`, and
`test_cancelling_whole_day_leave_removes_its_absences`.

Remaining Phase 2 work: complete the role/endpoint/object authorization
matrix; verify transactional behavior for concurrent requests against
PostgreSQL; add an authoritative holiday calendar; and validate race behavior
under database-level concurrency. Absences are naturally bounded to the seven
periods in a day, incoming pending substitutions are capped at five per
candidate, and faculty cannot submit past absences or leave. These remaining
items are not claimed as complete.

### OWASP Top 10 (2021) initial mapping

| Category | Phase 0 status | Evidence / next step |
|---|---|---|
| A01 Broken Access Control | Partial | Phase 2 policies and ownership tests; complete the route/object matrix and race/abuse limits. |
| A02 Cryptographic Failures | Finding | Finding 1; remove signing-key fallback and validate production configuration. |
| A03 Injection | Not assessed exhaustively | Run targeted query review and add input/injection regression tests. |
| A04 Insecure Design | Partial | Abuse cases above; review action-link, state-transition, and concurrency design. |
| A05 Security Misconfiguration | Finding | Findings 1–2; secure deployment defaults, headers, host, CORS, and docs configuration. |
| A06 Vulnerable and Outdated Components | Finding | pip-audit reported a pytest advisory; confirm/fix while preserving supported constraints. |
| A07 Identification and Authentication Failures | Findings | Findings 1–2; test authentication, lockout, session invalidation, reset, and MFA behavior. |
| A08 Software and Data Integrity Failures | Finding | Finding 5; pin or self-host browser dependencies and review CI/build integrity. |
| A09 Security Logging and Monitoring Failures | Not assessed exhaustively | Review audit immutability, security-event coverage, and secret redaction. |
| A10 Server-Side Request Forgery | Not assessed exhaustively | Search for server-side requests and validate any user-controlled destinations. |

### Scanner and test baseline

- Bandit: `python -m bandit -q -r app scripts migrations data` scanned 3,573
  lines and reported two Low `B311` pseudo-random-generator findings in
  `data/gen_data.py` (lines 192 and 391); no Medium or High findings. Exit 1.
- pip-audit: `python -m pip_audit -r requirements.txt` reported pytest 8.4.2
  (`PYSEC-2026-1845`), with pytest 9.0.3 reported as the fixed version. Exit 1.
- Semgrep: `p/python`, `p/fastapi`, and `p/jinja2` were not run because no
  usable Semgrep CLI was available in the environment.
- Baseline pytest: 38 passed and one failed. The failure is a stale hard-coded
  cookie-name expectation in `tests/test_auth.py`; the configured app issues
  `__Host-classswap_session`.

### Scope and residual risk

This phase is a code/configuration snapshot only. It does not prove that every
route, workflow, deployment setting, or dependency is secure. No production
penetration test, ZAP scan, Semgrep scan, container scan, or independent review
has been completed. Phase status and further evidence must be updated as fixes
and tests are implemented.
