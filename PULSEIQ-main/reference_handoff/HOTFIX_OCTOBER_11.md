# PULSEIQ — 11 October 2026 attendance, registration and class analytics hotfix

This package replaces the previous `PULSEIQ_LOGIN_REGISTER_ATTENDANCE_FIXED.zip`.
It **does not** delete or reset Supabase records.

## Diagnoses verified in the previous project

1. **Wrong day:** `backend/campus_pages.py` compared attendance to `date.today()` running on Render's UTC system clock. At approximately 05:20 India time on 11 October, UTC is still 10 October. The valid local date was rejected as future.
2. **Class Analytics crash:** Without attendance, the code accessed an empty `defaultdict` while building `below_attendance`. That inserted zero counters and produced `ZeroDivisionError` when computing the attendance-fall percentage. It affected classes with marks but zero saved attendance.
3. **Registration form:** The College Email Domain field requires **a domain only** (e.g. `pulseiq.edu.in`), not an email address (e.g. `clg@pulseiq.edu.in`). A valid invite code set in Render under `REGISTRATION_INVITE_CODE`, a 12+ character password and a matching administrator email domain are also required. API 422 validation failures formerly appeared as generic "Request failed".
4. **Legacy marks:** Older versions stored published marks in `pi3_entries`, while the newer faculty Marks Entry stores exams in `pi3_exam_results`. Analytics now reads published older records as a **fallback** when there are no current exam-wise marks for that same student/subject. No fake marks are generated and newer records take precedence.

## Files updated

| File | Change |
| --- | --- |
| `backend/campus_pages.py` | College-local date validation, `/api/v4/college-date`, division-by-zero fix, legacy published-marks compatibility and diagnostic counts |
| `backend/college_setup.py` | Default and validated college `timezone` preference |
| `frontend/src/main.tsx` | Clear registration hints, minimum password length, college timezone preferences, clearer Class Analytics marks/empty state |
| `frontend/src/api.ts` | Useful HTTP status and field validation messages for server errors and bad registration data |
| `requirements.txt` | Include Python `tzdata` in Render's slim container |
| `CHECK_MARKS_ATTENDANCE_REGISTRATION.sql` | Read-only checks for saved marks, attendance and college domains |
| `tests/test_oct11_hotfix.py` | Date-boundary, registration and marks-compatibility regression tests |

## Deployment

1. Copy this project's `PULSE` contents into the GitHub repository used by Render.
2. Commit and push. Choose **Manual Deploy → Deploy latest commit** on Render if auto deploy does not begin.
3. Wait until Render reports **Live**. Confirm `/health` responds with JSON, not an HTML error page.
4. Sign in as Faculty. Choose Attendance → assigned subject, date **11 October 2026**, slot and topic → mark present/absent → Save.
5. Open Class Analytics for **the same branch/semester/section/subject**. With recorded marks it should show pass/fail immediately, even if there are no attendance sessions yet; attendance fall should say **No data** until attendance exists.
6. Go to **College Preferences** (Admin) and verify timezone `Asia/Kolkata`, or change to your real institution's IANA timezone.

## Registration example

- College Name: `PulseIQ College`
- College Email Domain: `pulseiq.edu.in` (do **not** enter `clg@pulseiq.edu.in`)
- Administrator Name: your real administrator name
- Administrator Email: `srinu01@pulseiq.edu.in`
- Admin Password: at least 12 characters
- Registration Invite Code: exactly the secret configured in Render → Environment → `REGISTRATION_INVITE_CODE`

**Security note:** Do not send your invite code, password or entire database connection URI in chat. Production self-registration should add verification that the registrant controls the institution's domain.

## If errors continue

Use browser **F12 → Network → Fetch/XHR** and select the failed `/api/v4/class-analytics` or `/api/colleges/register` request. Note its HTTP code and safe error message. In Render, check the request's timestamp in **Logs**; redacted SQLSTATE/errors are logged for database failures. Run `CHECK_MARKS_ATTENDANCE_REGISTRATION.sql` in Supabase SQL Editor to inspect saved record counts. Do not disable RLS to diagnose these issues.

## Verification limitations

Local backend tests pass using a temporary, test-only Argon2 password hash compatibility shim because the development environment lacks the `pwdlib` package. The shim is NOT shipped in this ZIP; Render installs the real dependency from `requirements.txt`. The live Supabase database, Render deployment and full `npm run build` were not verified from this environment.
