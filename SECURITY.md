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

## Phase 3: input handling, injection, XSS, and CSRF

**Status: partial.** Jinja templates now use explicit autoescaping. All
state-changing API routes require a double-submit CSRF token and a matching
Origin or Referer; the browser templates send the token for fetch, HTMX, and
form requests. A request-body middleware limits ordinary requests to 1 MiB and
timetable-import requests to 2 MiB plus multipart overhead. Timetable imports
require a `.csv` filename and `text/csv`, UTF-8 input, at most 5,000 rows,
exact approved headers, bounded field lengths, and no control/format
characters; CSV error messages do not echo submitted field contents. The
existing transactional import remains all-or-nothing. Validation errors no
longer include submitted values. CSV exports neutralize formula prefixes,
including whitespace-prefixed formulas, tabs, carriage returns, and newlines.
No `.ics` export or one-click action-link route exists in this checkout.

Behavior changes: browser writes without a valid CSRF token and same-origin
Origin/Referer are rejected; JSON requests over 1 MiB and timetable files over
2 MiB are rejected; CSV imports with non-CSV metadata, over 5,000 rows,
oversized fields, control characters, or non-UTF-8 data are rejected.

Regression evidence: `test_every_unsafe_route_requires_csrf_validation`,
`test_csrf_less_absence_post_is_rejected`,
`test_cross_origin_absence_post_is_rejected`,
`test_oversized_json_request_is_rejected`,
`test_stored_user_content_is_html_escaped`,
`test_import_rejects_oversized_csv_without_importing_rows`,
`test_import_rejects_more_than_5000_rows_without_importing`,
`test_import_requires_csv_filename_and_content_type`,
`test_import_rejects_non_utf8_csv_without_importing_rows`,
`test_csv_formula_prefixes_are_neutralized`, and
`test_application_contains_no_string_built_sql`.

Remaining Phase 3 work: exhaustive length/character validation for every
user-facing string and a PostgreSQL-backed verification of import rollback.
Inline scripts remain and are authorized by the per-response nonce-based
content security policy implemented in Phase 5; browser dependencies use
integrity-pinned CDN assets. These controls are not claimed complete.

## Phase 4: public surface, tokens, and abuse protection

**Status: partial.** Added a per-IP in-memory limiter: global traffic is capped
at 300 requests/minute, public/unauthenticated routes at 120/minute, login at
30/minute, password-reset endpoints at 10 per 15 minutes, and CSV upload at
10/minute. Rejections return 429 with `Retry-After`. Login also retains the
per-account/per-IP progressive lockout from Phase 1. Password-reset tokens
remain 256-bit random values stored as SHA-256 hashes, short-lived, and
single-use.

The current checkout does not implement public `/today`, `/week`, or QR
timetable routes, calendar feeds, Telegram linking, or one-click action links.
Those are not exposed by this application version; the authenticated
`/timetable` page is not a student-public endpoint. Password reset is the only
email token flow present. No Telegram bot or user-controlled server-side URL
fetching exists.

Remaining Phase 4 work: add a public student timetable only if the product
requires it, then apply an explicit section allowlist and PII regression
scans; migrate rate-limit state to Redis or another shared service for
multi-worker deployments; and add notification delivery limits if those
features are introduced. The in-memory limiter is process-local and is not
sufficient as the sole production DDoS control.

## Phase 5: transport, headers, and configuration

**Status: partial.** Responses now receive a nonce-based Content Security
Policy with no `unsafe-inline` or `unsafe-eval`; inline scripts and the shared
stylesheet carry the per-request nonce, and templates contain no inline style
attributes. The two CDN-hosted browser libraries are version-pinned and use
SRI. Other response headers include HSTS in production, `nosniff`,
Referrer-Policy, Permissions-Policy, COOP, and frame restrictions.
Authenticated responses are marked `Cache-Control: no-store`; the Server
header is removed. CORS is deny-by-default with explicit configured origins,
and TrustedHostMiddleware rejects unlisted hosts. Production settings require
HTTPS base URL, a strong non-placeholder JWT secret, secure `__Host-` cookies,
DEBUG off, explicit hosts, PostgreSQL with `sslmode=require`, SMTP, and a valid
TOTP encryption key; API docs are disabled in production. Docker/Uvicorn use a
configurable forwarded-IP trust list and disable the Server header.

Behavior changes: inline style attributes were replaced with stylesheet
classes to enforce the stricter style policy. Dashboard chart bar heights are
rounded to the nearest 5% to avoid dynamic inline styles. Production requests
are redirected to HTTPS and API documentation endpoints are unavailable.

Regression evidence: `test_security_headers_and_csp_nonce_are_present`,
`test_templates_use_nonce_styles_without_inline_style_attributes`,
`test_authenticated_responses_are_not_cached`,
`test_production_responses_include_hsts`,
`test_unknown_cors_origin_is_rejected`,
`test_untrusted_host_is_rejected`,
`test_production_settings_require_hardened_transport_and_database`,
`test_production_disables_api_documentation`, and
`test_production_database_requires_ssl_and_non_local_host`.

Remaining Phase 5 work: validate HTTPS redirect and trusted-proxy behavior
in the production container behind the actual ingress; document and exercise
the deployment-specific allowed-host/CORS configuration; and consider
self-hosting the integrity-pinned frontend assets to remove the CDN dependency.
Do not treat these code-level tests as proof of deployment transport security.

## Phase 6: data protection, database, logging, and audit

**Status: partial.** Audit events are now appended through a single helper,
serialized with a PostgreSQL transaction advisory lock, and chained with
SHA-256 over the previous hash and canonical event fields. The migration
backfills existing entries, adds non-null hash fields, and installs a
PostgreSQL trigger that rejects UPDATE and DELETE. ORM-level mutation is also
blocked, and `python scripts/verify_audit.py` checks the complete chain.
Authentication successes/failures, password changes/resets, logout, force
logout, anonymization, data export, timetable import, admin-chain/leave
changes, and substitution responses are audited or logged. Request IDs are
generated server-side, returned as `X-Request-ID`, and included in structured
JSON logs. The logging filter redacts email addresses and common secret
assignments; authentication logs use hashed account/IP identifiers and never
include passwords.

Users can download their own profile, timetable, absences, substitutions,
leave records, and audit events at `GET /me/export`. A super administrator
with MFA can anonymize another account; account credentials, TOTP secrets,
reset tokens, role membership, and allocation data are cleared or invalidated
while operational references and immutable audit history remain. TOTP secrets
continue to use Fernet encryption from `TOTP_ENCRYPTION_KEY`; backup codes
remain hashed. No Telegram chat identifier exists in this checkout.

Behavior changes: production container startup no longer runs Alembic as the
application database user; development retains automatic migrations. Run
production migrations as a one-shot operation using a separate DDL-capable
`MIGRATION_DATABASE_URL`; keep the app's `DATABASE_URL` on a least-privilege
non-owner role with no schema DDL grants. Audit targets now use user IDs
rather than emails. Historical audit target text is retained to preserve
chain integrity, so legacy entries may still contain personal data;
anonymization does not rewrite the append-only chain.

Regression evidence: `test_audit_entries_form_a_verifiable_hash_chain`,
`test_audit_entries_cannot_be_updated_or_deleted_through_orm`,
`test_anonymizing_user_preserves_audit_chain_and_invalidates_sessions`,
`test_user_data_export_contains_only_safe_account_fields`,
`test_failed_login_logs_never_include_password`,
`test_redaction_filter_removes_email_and_password_values`, and
`test_responses_include_a_server_generated_request_id`.

Operational requirements: take encrypted, access-controlled PostgreSQL
backups with `pg_dump --format=custom --no-owner --file=classswap.dump
"$DATABASE_URL"`; restore into an isolated database with
`pg_restore --clean --if-exists --no-owner --dbname="$DATABASE_URL"
classswap.dump`, then run `python scripts/verify_audit.py` and application
smoke tests before promotion.
Exercise restores regularly and retain backups outside the primary failure
domain. Back up `TOTP_ENCRYPTION_KEY` in a separate secrets vault. Rotation
requires a controlled job that decrypts each stored TOTP secret with the old
key, re-encrypts it with the new key, verifies all records, and only then
replaces the runtime key; retain a protected rollback copy until completion.

Remaining Phase 6 work: provision and test separate PostgreSQL owner,
migration, and runtime roles with actual grants; validate append-only behavior
and advisory-lock ordering against PostgreSQL; implement a managed key
rotation process; and decide retention/legal-deletion requirements for
personal data retained inside historical audit records. Database encryption
at rest, field-level encryption beyond TOTP, and production backup/restore
testing remain deployment responsibilities.

## Phase 7: supply chain, containers, and CI

**Status: partial.** Added hash-locked runtime, development, and data
requirements compiled from their `.in` sources; `pip-audit` reports no known
Python dependency vulnerabilities in any of the three locks. CI and
pre-commit run pytest, Ruff, mypy, Bandit, pip-audit, Semgrep, Gitleaks, and a
Trivy image scan. Scanner images and GitHub Actions are pinned. Dependabot
covers pip and Docker. The Docker image uses a digest-pinned Python 3.14
Alpine multi-stage build, installs dependencies with hashes, runs as a
non-root user, removes pip from the runtime, and defines a health check.
Production Compose has no host-published web or database ports, uses a
read-only application filesystem, drops capabilities, and requires explicit
production settings. The running image builds successfully.

The requested Semgrep registry preset `p/jinja2` returns HTTP 404. Instead,
CI uses `p/python`, `p/fastapi`, and `p/security-audit` plus the local
`.semgrep/jinja.yml` rules that reject Jinja `safe` filters and Python
`Markup(...)` calls. Bandit reports no High findings; Semgrep reports zero
findings; Gitleaks scanned 37 commits and reported no leaks.

The initial Debian slim base produced 53 High OS findings, so the image was
changed to the digest-pinned Alpine base and all locked runtime packages were
verified to install from hash-pinned musllinux wheels. Trivy 0.76.2 reports
**0 High and 0 Critical** findings in the final Alpine image, including no
vulnerable Python packages. No severity suppressions or ignored findings
were used.

Behavior changes: production Compose overrides development port bindings
using Compose's `!reset` syntax; use a Compose version supporting that tag.
The runtime image no longer contains pip. The Uvicorn `standard` extras were
removed so a single hash lock installs on Windows and Linux; the server uses
the default h11/asyncio implementation instead of optional accelerated
transports. This can reduce throughput but does not change application
protocol behavior.

Regression/verification evidence: full pytest suite (97 passed),
`python -m ruff check app scripts migrations tests data`,
`python -m mypy app scripts`, high-severity Bandit, all three clean
`pip-audit` lock scans, Semgrep (209 rules, zero findings), Gitleaks (37
commits, zero leaks), successful Alpine Docker image build, Trivy (zero High
or Critical findings), runtime import without pip, and Compose checks proving
no production port bindings and a read-only web filesystem.

Repository hygiene: `.env`, local database dumps, and local
`seed_credentials.*` / `seed-credentials.*` files are ignored. No `.env` or
database dump is tracked, and Gitleaks found no leaked secret. The public
development-only demo password `demo123` does exist in historical
`scripts/seed.py` commits; it is not a production credential and production
seeding is refused. Treat it as public, never reuse it, and reset any account
that may have used it outside development. If repository policy requires
purging that historical string, first rotate/revoke any affected credentials
and coordinate a full history rewrite from a fresh clone. For example, with
`git-filter-repo` installed in PowerShell:

```powershell
@'
demo123==>REMOVED-DEMO-CREDENTIAL
'@ | Set-Content -Encoding utf8 replacements.txt
git filter-repo --replace-text replacements.txt
Remove-Item replacements.txt
```

After review, restore the remote and force-push all branches and tags during a
coordinated maintenance window; collaborators must re-clone. Do not run this
history rewrite casually.

Remaining Phase 7 work: resolve the High Debian OS findings and rerun Trivy;
exercise PostgreSQL role grants and production migrations; scan the actual
deployment image and ingress configuration; and validate Dependabot/CI
execution on the remote runner.

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
