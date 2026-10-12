# Tests run for v3

`python -m compileall -q backend`: **passed**.

`pytest -q tests/test_tenants.py`: **6 passed** in the artifact creation environment (the installed runtime did not contain `pwdlib`, so an external temporary Argon2-compatible local test shim was used; this shim is **not shipped** in the artifact). The Docker production image installs the specified `pwdlib` dependency.

Covered: admin login and domain resolution, student privacy, faculty assigned classes and draft/published marks/attendance, CSRF enforcement, institutional email domain constraints, atomic bulk roster import, cross-college isolation with duplicate student IDs, action version conflicts. The initial endpoints were also exercised using FastAPI TestClient.

`frontend/src/main.tsx` was parsed/transpiled with TypeScript, **0 parse diagnostics**. **Full `npm ci` / Vite typecheck not run** because package registry network access was unavailable in this environment. Docker/Render runs the actual build and should be checked in the deployment logs.

Additional required before handling actual student data: test against real Neon/PostgreSQL, database-driver and college schema integration tests, end-to-end browser flows, security audit, backup restore, and accessibility checks.
