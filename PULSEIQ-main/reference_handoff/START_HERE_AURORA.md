# PULSEIQ · Admin / Faculty / Student Role Pages (October 2026)

This is the **updated deployable React + FastAPI project** that follows the requested page-by-page redesign. It is built on the previous PULSEIQ Aurora architecture and uses **one Supabase PostgreSQL instance with college-scoped data isolation**. A college registering here receives its own institution/workspace and permissions; it **does not receive a separately provisioned physical Supabase database**. Physical per-college databases require a separate provisioning service.

## Quick deployment (Render + Supabase)

1. Create or reuse a Supabase PostgreSQL project. Do **not** delete your current database, imported 250 student roster, or existing administrator account.
2. In Supabase **Connect → Session pooler**, copy the entire PostgreSQL URI. It should look like:

   `postgresql://postgres.PROJECT_REFERENCE:YOUR_DB_PASSWORD@aws-0-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require`

   Verify the hostname and region in your own Supabase dashboard. NEVER commit this URI to GitHub or paste the password into a public chat.
3. Push the **contents of this PULSE folder** to the root of your GitHub repository.
4. On Render, deploy using `render.yaml` (Docker environment) or configure a Docker Web Service with Dockerfile at repository root.
5. In Render > Environment set these private values:

   | Key | Purpose |
   | --- | --- |
   | `DATABASE_URL` | Full Supabase Session pooler URI. |
   | `APP_SECRET` | Random secret at least 32 characters (Render can generate). |
   | `BOOTSTRAP_COLLEGE_NAME` | College name for a **fresh** database. |
   | `BOOTSTRAP_COLLEGE_DOMAIN` | E.g. `democollege.edu.in`. Must match the source college domain for importing. |
   | `BOOTSTRAP_ADMIN_EMAIL` | Same domain as `BOOTSTRAP_COLLEGE_DOMAIN`. |
   | `BOOTSTRAP_ADMIN_PASSWORD` | Minimum 12 characters, for **initial** bootstrap only. |
   | `REGISTRATION_INVITE_CODE` | Private code for controlled registration of additional colleges. |
   | `COOKIE_SECURE` | `true` for HTTPS Render. |
   | `SEED_DEMO` | `false` (avoid overwriting demo setup with unrelated records). |

   **Existing deployments:** Bootstrap environment values do not replace old Admin logins or passwords. Use the previous Admin login after redeployment.
6. Redeploy. Check `/health`; sign in. SQLAlchemy automatically creates missing `pi3_*` tables on backend startup. For SQL management and RLS, run `database/01_application_schema.sql` from Supabase SQL Editor (does not drop tables).
7. In **Admin → Supabase Import**, use your existing `public.students`, `public.faculty` and `public.colleges` data to create missing student/faculty login accounts. The importer requires the source college `email_domain` to match `pi3_colleges.domain`. Your existing roster is retained. Supply temporary student/faculty passwords at least 12 characters, and change them per user before real use.
8. In **Admin → Faculty & Subjects** make sure faculty subjects/sections are assigned. These assignments control permissions, attendance, marks, and timetable access.

### Local development (Windows, macOS, Linux)

Backend (Python 3.12 recommended):

```bash
python -m venv .venv
# Activate it for your shell, then:
pip install -r requirements-connectors.txt
# Set DATABASE_URL and APP_SECRET in your shell / secrets manager
python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000 --reload
```

Frontend (Node 24, or the version compatible with included Vite):

```bash
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173` (Vite proxies `/api` to `http://127.0.0.1:8000`). Production `Dockerfile` builds React and serves it from the same FastAPI origin, preserving secure cookies and CSRF behavior.

## Exact new page design

| Admin | Faculty | Student |
| --- | --- | --- |
| Dashboard — ONLY branch-wise student and faculty pie charts | My Students — roll, name, department, section, email, phone | My Profile — own record, contact and interests |
| Student Directory — branch/section/search, add student + email/password | Student Success Insight — own students' mark rate, subjects, interests, achievements | Performance — every recorded exam; upload certificates/achievements (PDF/image <=2MB) |
| Student Analytics — exam-mark success rate, recorded interests and achievements | Attendance — select branch/section/subject, Present/Absent radios, date, slot, topic; corrections | Risk Insights — low subjects and recorded academic backlogs (no invented predictions) |
| Faculty & Subjects — accounts and teaching assignments | Marks Entry — direct exam marks by branch/section and assigned subject | Attendance — cumulative or date-range presence/total percentage |
| Attendance — record faculty presence and read student attendance | Timetable — admin-published view only | Timetable — Monday through Sunday, each day configurable |
| Timetable — add/remove faculty/subject slots; overlap prevention | Class Analytics — pass %, fail %, attendance fall %, below-threshold students | Assignments & Tests — upcoming published tasks and submissions |
| Announcements, Supabase Import, College Preferences, My Account | Assignments & Tests, Announcements, My Account | Announcements, My Account |

Removed from role navigation: Admin Machine Learning, Teaching Assignments as a separate tab, Admin Marks & Publishing, Improvement Insights, Interventions; Faculty Dashboard, My Classes, Learning Resources, ML Risk Insights, Mentoring; Student Dashboard, old Success Insights, ML Risk Insights, Focus Areas, separate Marks/Results, Support Plans. Existing backend tables are retained **without deleting data**.

### Business rules and data truth

- **Student attendance** is stored in `pi3_class_sessions` and `pi3_class_attendance`, uniquely keyed to the faculty's teaching assignment, date and time slot. Corrections are limited to the original faculty who entered that session. The Admin attendance page is read-only for students.
- **Exam marks** are stored in `pi3_exam_results` for a specific subject, exam name, exam date, and maximum marks. Marks cannot exceed the maximum.
- **Student Success Rate** is the arithmetic mean of the percentages of all recorded faculty-entered exam marks. When no marks exist, the UI shows **No data**, not 0%. Interests and uploaded achievements are displayed to aid guidance; they do not silently influence the marks score.
- **Student Risk Insights** highlights low exam scores and displays the official `backlog_count` only if it exists in a non-synthetic academic observation. A low midterm grade does not automatically mean a backlog.
- **Class pass percentage** is calculated over students with recorded exam marks for the selected subject, using the college's pass threshold from College Preferences. Students with no exam records are excluded, not counted as failures.
- **Attendance below minimum** uses actual recorded class presence and the college's attendance threshold.
- **Faculty attendance** is recorded by Admin for each faculty member and calendar date.
- **Credentials** are server-side hashed using `pwdlib[argon2]`. Student creation is atomic: roster + contact + login together. Email must be globally unique.
- **Files** are optional PDFs, PNGs, JPEGs, or WebP, up to 2MB. The binary data is saved in the college-scoped PostgreSQL record and served as a private attachment only to permitted users.

### Current project architecture

- React / TypeScript, Vite, Lucide icons and Recharts.
- FastAPI, SQLAlchemy, PostgreSQL on Supabase; secure HttpOnly session cookies and CSRF tokens.
- Multi-college logical tenant isolation using `college_id` and subject/roster authorization.
- Historical traditional-ML engine preserved on the backend for future supervised learning data. **No unsupported ML risk claims appear in the simplified screens.** The new risk/interest reports are directly based on recorded marks and evidence, not unvalidated model predictions.
- Visual system: pastel glitter gradients; glass cards; gentle glowing hover backlights, slow lift and moving accent bars; responsive and reduced-motion aware.

## Testing and validation

Backend:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q tests/test_tenants.py tests/test_extensions.py tests/test_page_changes.py
```

Frontend:

```bash
cd frontend
npm ci
npm run build
```

In this sandbox, Python syntax passed, TSX was parsed, TypeScript `tsc` returned success, and **18 local backend tests passed** using SQLite. Full `npm ci` / Vite production build and a live Supabase/Render deployment could not be performed here because npm network access is unavailable. These remain **deployment verification tasks**, not completed tests.

After deployment, run `database/02_check_database.sql`, then test Admin → Faculty → Student with an actual assigned class. **Do not deploy with shared demo passwords or academic synthetic scores for real student decision-making.**
