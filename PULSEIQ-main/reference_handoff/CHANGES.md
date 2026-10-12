# Changes from supplied PULSEIQ v2 ZIP (v3.0.0)

- One new multi-college FastAPI entry point with additive `pi3_*` PostgreSQL tables.
- First college bootstraps from `BOOTSTRAP_COLLEGE_*` / admin email; subsequent colleges provisioned with private CLI.
- Institutional email resolution and login with **Admin, Faculty, Student** role-scoped sessions.
- College name visible in UI, role redirects to `/college/admin`, `/college/faculty`, `/college/student`.
- Admin roster create/update and bulk JSON import (5,000 rows per request).
- College admin creates/activates/deactivates faculty/student/admin accounts; faculty assignment by department/semester/section/subject.
- Faculty posts attendance and marks drafts or published records; students see only published records. Institution refresh does not erase manual records.
- Student-only profile, marks, attendance, current rules-v1 analytics and mentorship actions.
- Faculty/admin action board with version checks and update audit events.
- Per-college encrypted integration credentials, SQL/MongoDB/HTTPS mapping, inspection, preview, sync and deletion.
- Optional one-time legacy v2 snapshot and action migration when `IMPORT_LEGACY_V2=true`.
- Six v3 backend regression tests, updated cloud manifests, new docs and three-portal React frontend.

## Not implemented automatically

- Verification that a college actually owns a domain (institutional administrator must verify before provisioning).
- OAuth/SSO or password reset by email, recurring scheduler, automatic live writeback to college SIS.
- Arbitrary database integration without a vendor driver, authorized credentials, network permissions and custom schema mapping.
- Complete end-to-end browser smoke test in artifact-building environment; external npm registry unavailable.
- Production-grade tenant RLS, immutable audit log, formal migration framework, independent penetration test, FERPA/DPDP compliance assessment.
