# Run, connect Supabase, and deploy

## 1. Fastest working demonstration on Windows

Extract this ZIP. Open the PULSEIQ folder. Install Python 3.12 if not installed.
Double-click `start_demo_windows.bat`. The first run downloads dependencies.
Open **http://127.0.0.1:8000**. Sign in:

- Email: `admin@demo.edu.in`
- Password: `DemoCampus2026!`

Open **Success Intelligence**. There are 200 fictional students covering seven
categories and two reporting periods. Select DEMO0001 for strong academics but
weak placement readiness. Train the synthetic demonstration model if needed.
This loopback-only demo stores data in local_demo.sqlite. It is not Supabase and
must not be deployed publicly. It deliberately uses test settings and known credentials.
For a fresh demo, stop the server and rename local_demo.sqlite to a backup filename.

Manual equivalent in PowerShell, from the extracted PULSEIQ folder:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run_demo.py
```

## 2. Connect the real app to Supabase

1. Create a Supabase project. Save its **database password**.
2. Open **Connect → Session pooler** and copy the PostgreSQL URI, normally port
   5432. Use the host displayed for YOUR project. The user is typically
   `postgres.PROJECT_REF`. This is not the Supabase Project URL or anon API key.
3. Replace the password placeholder with your URL-encoded database password.
   Special characters such as @, #, / and : must be percent-encoded. Add
   `?sslmode=require` if there is no query string (or `&sslmode=require` otherwise).
4. In Supabase SQL Editor run `database/01_application_schema.sql` once. It creates
   pi3_* tables and enables RLS; it does not delete data. Startup also creates
   missing tables and protects them against direct anon/authenticated API access.
   The backend uses a database owner connection. Tenant isolation is enforced by
   the backend, not by Supabase Auth JWTs.
5. Copy `.env.example` to `.env`. Fill DATABASE_URL and a random APP_SECRET.
   Generate a secret using `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Keep COOKIE_SECURE=false only for local HTTP. Leave all bootstrap fields blank.
6. Run `start_windows.bat`. Open http://127.0.0.1:8000 and click **Register Your College**.
   Domain example: `qis.edu.in` (no @, no https://). Admin email must match that domain.
7. Sign in. For an empty demo college use Success Intelligence → Load 200 fictional
   students. For real data use the CSV import. Do not mix fictional and real data.

No Supabase project keys or database password belong in frontend code. The browser
only calls FastAPI. Application accounts are stored in pi3_accounts with Argon2 hashes;
Supabase Authentication users are separate and are not used by this application.

## 3. Import data and enable faculty/student workflows

- Use `templates/students.csv` and category templates. Keep headers unchanged.
- `student_id` joins all categories; keep it consistent. Include students.csv with
  every import, containing the students referenced in those category files.
- Include `full_name,email,section` as extra roster columns if available.
- Each category row has `period_end` in YYYY-MM-DD. Use genuine observation dates;
  do not change historic dates merely to make stale data appear fresh.
- Choose all category files together in Success Intelligence. Missing categories
  remain unknown; validation rejects duplicate keys, invalid ranges and unmatched IDs.
- CSV imports create/update the roster and observations, **not login accounts**.
- Add new students with logins through Student Directory. For an existing imported
  roll number, use authenticated `/api/admin/accounts` (role student, student_id,
  matching-domain email, full_name and password); see docs/API.md or ENABLE_API_DOCS=true.
- Faculty & Subjects creates faculty and teaching assignments. Faculty only see
  assigned branch/semester/section students. Admin creates timetable slots.
- Faculty record marks and attendance. Student Performance and Attendance update;
  these operational records also feed the Success Score. Internal failures are
  not automatically labelled official backlogs.
- Existing public.students/public.faculty source tables use the separate Supabase
  Import screen. Their college domain must match; do not run optional source/demo
  SQL on an existing real college unless you intend to add those demo records.

For campus databases on a private LAN, Render cannot reach localhost or private
addresses by magic. Use the CSV flow for the prototype or an institution-managed
outbound integration / secured tunnel. Backend connectors support reachable sources;
automatic private-network agents and dedicated databases per college are not included.

## 4. Deploy on Render (one service for frontend and backend)

1. Create a NEW GitHub repository, upload the CONTENTS of PULSEIQ so Dockerfile,
   render.yaml, backend and frontend are at repository root. Do not upload .env,
   .venv, node_modules or local_demo.sqlite. Prefer a new repository to avoid the
   unrelated-histories problem; do not force-push over an existing project.
2. Render → New → Blueprint → choose the repository. It reads render.yaml.
   Alternatively New → Web Service → Docker; root directory is the folder with
   Dockerfile. Leave Docker command blank so the packaged CMD is used.
3. Set DATABASE_URL to the Supabase Session pooler URI. Blueprint generates APP_SECRET.
   Set COOKIE_SECURE=true and ENVIRONMENT=production. Keep SEED_DEMO=false and
   IMPORT_LEGACY_V2=false. Bootstrap values are not required for web registration.
4. Deploy. Docker rebuilds the React UI and installs Python dependencies. The app
   binds 0.0.0.0 using Render's PORT. Health check: `/health`.
5. Open the HTTPS Render URL, register the college, import data and test all roles.
   If the college already exists in this database, sign in with its existing account.
6. Keep APP_SECRET stable between redeploys; changing it invalidates sessions and
   may make encrypted connector credentials unreadable. Back up Supabase separately.

Typical errors:
- Connection timeout: use session pooler/5432, verify project active and network access.
- Password authentication failed: check database password, encoded URI and project ref.
- 403 CSRF: sign out/in; use same-origin built frontend (or supplied Vite proxy).
- Login succeeds but subsequent request is 401 locally: COOKIE_SECURE must be false.
- No students for faculty: create correct teaching assignment, semester and section.
- No overall score: weighted coverage is below 80%; import more current indicators.
- Blank/old UI: rebuild frontend (`npm ci`, `npm run build` inside frontend) and redeploy.

## 5. Verification and boundaries

See docs/TEST_REPORT_CURRENT.md. Live Supabase/Render cannot be verified without
access to your project. Never describe the supplied synthetic model as validated on
real students. This is a hackathon prototype; institutional production requires
verified onboarding, operational monitoring, backup recovery tests and privacy review.

Official setup references (checked for this release):
https://supabase.com/docs/guides/database/connecting-to-postgres
https://render.com/docs/docker
https://render.com/docs/web-services
