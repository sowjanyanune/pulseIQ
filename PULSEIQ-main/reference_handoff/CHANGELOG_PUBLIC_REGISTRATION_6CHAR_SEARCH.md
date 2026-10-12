# PULSEIQ update — public registration, 6-character minimum, student search

## Changes

1. **College registration no longer requires an invite code.** The frontend field and the backend invite-code check have been removed. `GET /api/colleges/registration-status` reports public registration. The `REGISTRATION_INVITE_CODE` Render setting is no longer required or used.
2. **New passwords: minimum 6 characters** (previously 12). Applies to college Admin registration, Admin-created faculty/student accounts, Supabase import temporary passwords, account reset, password change and the optional initial bootstrap account. Existing password hashes and accounts are unchanged.
3. **Faculty > Student Success Insight** gains search for student name or roll number, alongside branch/section filters and a matching-record count. Searches are case-insensitive and operate on the faculty-scoped records returned by the API.
4. **Fresh platform startup:** if none of the `BOOTSTRAP_*` variables are configured, the server can start with zero colleges and the first college can self-register. If you use bootstrap, set the full group of variables. No existing college is deleted or changed.

## Edited files

- `frontend/src/main.tsx`
- `backend/college_setup.py`
- `backend/api_v3.py`
- `backend/campus_pages.py`
- `backend/legacy_main.py`
- `tests/test_oct11_hotfix.py`
- `.env.example`, `render.yaml`, `README.md`

## Deploy to Render

1. Extract and push the `PULSE/` folder contents to the GitHub repository connected to Render.
2. Keep your existing `DATABASE_URL`, `APP_SECRET`, `COOKIE_SECURE` and your existing bootstrap variables if the college already exists.
3. You may remove the old `REGISTRATION_INVITE_CODE` from **Render > Environment**. It is ignored by this release.
4. Redeploy **latest commit**, then hard-refresh the browser (`Ctrl+Shift+R`).
5. At Sign in, click **Register Your College**. Only college name, domain, administrator name/email and a password (>=6 characters) are required. Domain example: `mycollege.edu.in`, not `admin@mycollege.edu.in`.
6. As Faculty, open **Student Success Insight** and search by roll number or name; branch/section filters work at the same time.

## Security and architecture notes

- Six characters is a **minimum**, not a recommended password strength. Use longer, unique passwords, especially for real institutions.
- With no invite code, anyone can attempt to register a college using an unclaimed domain. **This version does not verify ownership of the entered email/domain.** Before onboarding real colleges, add email/domain verification, registration rate limits and institutional approval/abuse controls.
- The app stores college-scoped records in **one shared Supabase PostgreSQL project**. It does not provision a separate physical database per college.
- Existing Supabase data does not need SQL migration for these three changes.

## Verification performed

- 25 Python backend tests passed in local SQLite test runs using a **test-only Argon2 compatibility adapter**, because `pwdlib` was not installed locally. Real deployments use `pwdlib[argon2]` from the supplied requirements.
- Python backend bytecode compilation passed.
- React TSX parsing passed using TypeScript compiler parsing (0 syntax diagnostics).
- **Not verified:** full React/Vite production build, live Render/Supabase integration, and end-to-end browser behavior.
