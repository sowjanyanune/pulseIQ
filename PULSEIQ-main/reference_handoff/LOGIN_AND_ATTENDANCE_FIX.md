# PULSEIQ — Sign-in, college registration button, faculty attendance repair

## Exactly which files changed

| File | Change |
|---|---|
| `frontend/src/main.tsx` | In `App`, stop automatically restoring the old 8-hour cookie session. On every fresh page load, read its CSRF token, revoke the old session, and show login. In `Login`, add a prominent **Register Your College** button. In `FacultyAttendance`, show matched class counts, local save errors, existing-session loading/correction, and verify each save from PostgreSQL. |
| `frontend/src/styles.css` | Add prominent purple/blue/teal college-registration CTA and clear attendance status banners; preserve the Aurora UI animations. |
| `backend/api_v3.py` | Log safe database error diagnostics (`endpoint`, SQLSTATE, constraint) on Render. Passwords and connection URLs are never included in the log message. |
| `CHECK_ATTENDANCE_SETUP.sql` | Read-only SQL to diagnose absent faculty logins, missing assignments, class mismatch, missing attendance tables, and successful saved sessions. |

## Why the application opened without a login

The old `App` loaded `GET /api/auth/me` and restored the cookie session automatically. Cookies are valid for up to eight hours. The updated code **logs out an old session at page initialization**, so a newly opened or refreshed page will require sign-in, while navigating around the app after sign-in works normally. If you prefer "remember me" later, change the initial `useEffect` in `frontend/src/main.tsx`.

## Why attendance can appear not to work

Attendance requires ALL of the following:
1. Faculty logged in with a real `pi3_accounts` faculty account.
2. Admin created an exact `pi3_assignments` record assigning that account the relevant **branch + semester + section + subject**.
3. An active matching student roster in `pi3_roster`. The original imported 250 students do not automatically create assignments.
4. Faculty selected a valid date, time slot and topic and marked the class.
5. The Supabase tables `pi3_class_sessions` and `pi3_class_attendance` exist.
6. The database operation succeeds; on a 503, check Render logs for SQLSTATE.

The updated Faculty Attendance screen now displays the number of matching students, shows the API error beside the form, and verifies the save by calling `GET /api/v4/attendance/session` after the `POST /api/v4/attendance/batch` succeeds.

### Supabase checks

Open Supabase → SQL Editor, paste `CHECK_ATTENDANCE_SETUP.sql`, and run each query. If the "teaching assignments" count is zero, sign in as **Admin → Faculty & Subjects → Assign Subject to Faculty**. Use exact branch, semester, section values shown by SQL.

For reference, `public.students` is your *source* table. Faculty attendance operates on `public.pi3_roster` and `public.pi3_assignments`, not directly on `public.students`.

### Deploy (Render + Supabase)

1. Extract the new ZIP, open its `PULSE` folder and replace/push your project source to GitHub. Make sure Render points to the same branch/repository.
2. **Do not put any passwords or the full `DATABASE_URL` into GitHub**. Keep them in Render environment variables.
3. Verify that Render uses the included `Dockerfile` and starts `backend.main:create_app` via Uvicorn. **Do not start the legacy `app.py` or a separate Vite preview instance as the production app**.
4. Render → Manual Deploy → Deploy latest commit; allow it to rebuild the React frontend and restart FastAPI.
5. Open your deployment in a private browser window, verify the login screen appears, and verify the college registration button is highlighted.
6. Use an Admin account to check teaching assignments and current student roster. Then test Faculty Attendance with a single assigned class.
7. Check Student → Attendance and the 5th query in `CHECK_ATTENDANCE_SETUP.sql` to verify the saved session.

## College registration

The public sign-in screen highlights **Register Your College**. The registration API is invite-code protected. In Render, set `REGISTRATION_INVITE_CODE` to a secure private value before attempting registration; it is intentionally *not* a publicly open registration endpoint.

## Verification notes

- Backend tests were run using an **ephemeral test-only Argon2-compatible `pwdlib` shim** because the actual package was not installed in this offline environment. The shim is NOT included in this release and does not replace the real dependency installed by Docker.
- Frontend TSX parsing/transpilation and Python syntax checks passed.
- Full `npm ci` / Vite production build and live Supabase connection could not be verified from this environment. Deploy and inspect any remaining Render errors.
