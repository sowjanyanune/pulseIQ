# API

Base URL is your Render app address, followed by `/api`. The React client uses relative URLs. Production interactive API documentation is disabled by default; an administrator can set `ENABLE_API_DOCS=true` if needed. Protected endpoints still require staff authentication.

## Authentication

POST `/auth/login` accepts `{"username":"...","password":"..."}` and sets the HttpOnly session cookie. Its JSON response contains the user and CSRF token. GET `/auth/me` restores the user/token for an existing session. Every subsequent POST/PATCH, including logout, needs the cookie and `X-CSRF-Token`. Browser same-origin checks also apply.

This is session authentication, not a public API key. External scripts would need to log in, preserve cookies, handle expiry and send the CSRF token. There is no external API-key issuance feature in this release.

## Routes

| Method/path | Access and behavior |
|---|---|
| GET `/health` (outside `/api`) | Public database health check; no student records |
| POST `/api/auth/login` | Login and issue session |
| GET `/api/auth/me` | Session user/CSRF token |
| POST `/api/auth/logout` | Revoke current session |
| GET `/api/meta` | Available dates, authorized departments, semesters, dataset metadata, scoring config |
| GET `/api/cohort` | Authorized scored student summary and support counts |
| GET `/api/students/{student_id}` | Authorized evidence profile/component breakdown |
| POST `/api/students/{student_id}/scenario` | Read-only what-if computation on fresh observed fields |
| GET `/api/actions` | Authorized saved actions |
| POST `/api/actions` | Create intervention/history event |
| PATCH `/api/actions/{id}` | Version-checked update/history event |
| GET `/api/actions/{id}/history` | Authorized revision history |
| GET `/api/quality` | Admin-only snapshot validation and recent refresh logs |
| POST `/api/admin/sync` | Admin-only fetch/validate/replace source snapshot |
| GET `/api/admin/users` | Admin-only staff list; never password hashes |
| POST `/api/admin/users` | Admin-only create staff account |

Cohort filters: `period`, `analysis_date`, `stale_days` (0–365), `department`, `semester`, `segment`. Profiles take the date/freshness filters. Actions take department/semester filters; reporting-period selection does not delete or rewrite saved actions.

Create action fields: `student_id`, `owner_alias`, `action`, `rationale`, `due_date`. Created status is Planned, version 1. Patch fields: `owner_alias`, `action`, `due_date`, `status`, `review_note`, `version`. Status is Planned, In progress, Reviewed or Closed. Reviewed/Closed need a nonblank review note. Student association cannot be patched.

Create staff fields: `username` (3–80 allowed characters), `password` (12–200 characters), `role` (admin/faculty/placement), `departments` (required for restricted roles). Admin users have institution-wide access.

Scenario fields: `period`, `analysis_date`, `stale_days`, `changes` object. Allowed changes are marks, classes attended, assignments completed, aptitude, coding and interview. Missing/stale fields cannot be invented. Percentages/counts remain within validated ranges. The response contains baseline and scenario; neither result is saved to the student tables.

## Errors

| Status | Meaning |
|---|---|
| 400 | Invalid requested action/period/source snapshot |
| 401 | No valid staff session |
| 403 | Missing permission, invalid CSRF or cross-origin mutation |
| 404 | Unknown resource or outside authorized departments |
| 409 | Action version conflict or duplicate username |
| 422 | Request type/length/range validation error |
| 429 | Login attempt limit |
| 502 | Source fetch/network/driver failure |
| 503 | Application database operation unavailable |

Failed source validation returns `detail.message` and `detail.report`. Database/source failures do not return credential strings. Do not include raw environment settings in an API response when extending the backend.
