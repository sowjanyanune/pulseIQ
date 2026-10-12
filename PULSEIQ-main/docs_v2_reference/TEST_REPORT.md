# Package verification — 10 October 2026

## Results

| Check | Result |
|---|---|
| Python API, rules, source and persistence suite | **41 passed** |
| React TypeScript check and Vite production build | **Passed** |
| Browser integration scenarios | **7 passed**, no uncaught page errors |
| Desktop and mobile board inspection | **Passed**, mobile width 390 px |
| PostgreSQL DDL compilation | **Passed** through SQLAlchemy PostgreSQL dialect |

Environment: Python 3.12.14, Node 24.19.0. Backend/browser checks used isolated temporary SQLite databases with the real FastAPI routes and real React build. Production settings require PostgreSQL; users do not configure a local SQLite database.

## What the automated suite checks

- Login, secure session-cookie settings, CSRF, cross-origin rejection, logout, expired/deactivated sessions and login attempt limits.
- Administrator/faculty/placement account access, department filters and denial of profiles/actions/history outside authorized departments.
- A 1,000-student database seed, idempotent startup and a known complete reference score of 68.0.
- Missing fields, zero denominators, provisional/insufficient coverage, known triggers despite partial evidence, support requests without score penalties, stale and future reporting dates.
- Exact reporting-period joins and configuration/threshold boundaries.
- Invalid source fields/ranges, duplicate keys, unmatched IDs, malformed entity arrays and field mapping.
- Read-only SQL mapping using a separate fixture database, stable string IDs with leading zeroes and bounded canonical API responses/authentication on a mock HTTPS transport.
- Action creation, required review notes, reopening, append-only application revision events and version conflict rejection.
- **Two simultaneous edits:** one succeeds, the other receives 409; only one additional revision is committed.
- Parallel cohort/profile/action requests and persistence across application/engine reconstruction.
- Failed validation preserves the prior snapshot/actions/history; an injected database failure rolls back snapshot replacement.
- Removed students retain existing intervention history; a roster-only source still provides unknown profiles and usable actions.

## Browser scenarios

1. Staff login and 1,000-student overview/charts.
2. Student profile, 68.0 reference score and source provenance.
3. Create an Action Board item and save a Reviewed status/note.
4. Reopen, inspect three revisions, restart the backend and confirm the same action/history/session persists.
5. Calculate a 78.0 scenario from the 68.0 baseline; confirm the baseline stays unchanged and the scenario remains visible.
6. Create a faculty account and confirm 250 authorized Computer Science students, scoped actions and no administrator navigation.
7. Use the Action Board at mobile width without horizontal page overflow.

Screenshots are included under `docs/screenshots/`; their students and account names are fictional test records.

## Demo coverage

The initial database seed contains 1,000 roster records and 2,000 rows in each of the seven reporting sources: **15,000 canonical records total**, across two reporting dates. In the latest fresh period, 964 scores are complete, 35 provisional and 1 insufficient. Fixtures explicitly include an academic gap, placement gap, dual gap, on-track case, missing placement evidence, zero denominator and a student support request.

This validates program behavior, not model prediction accuracy. There is no trained model or claimed real-world accuracy figure.

## Checks that require your accounts or institute access

An actual Neon connection, Render image build/deployment and the institute's real SQL/MongoDB/ERP endpoint have **not** been tested here because their accounts, credentials and approved network access were not provided. Do not interpret driver support or PostgreSQL DDL compilation as a completed live-connection test.

The GitHub Actions workflow is included to run the API suite against its own PostgreSQL 17 service, build React, run browser checks and build the Docker image. That remote workflow has not run until you push this code to GitHub. Follow `START_HERE.md` to deploy and verify your HTTPS service.

MySQL/Oracle/SQL Server require optional drivers and, for SQL Server, a system ODBC driver. MongoDB nested-field handling is checked, but a live MongoDB server is not part of the initial verification.

Nonfatal messages: an upstream test-client deprecation warning and Vite's JavaScript bundle-size advisory. No test failures remain in the verified package.
