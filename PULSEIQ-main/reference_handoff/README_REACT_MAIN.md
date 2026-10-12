# PULSEIQ — Main React Interface (KAKI Design)

This is the main PULSEIQ UI requested for the student success hackathon. The React interface retains the uploaded `kaki.html` visual language (ink sidebar, pale canvas, teal accent, typography, cards, status indicators, student 360° and compact tables). Its stylesheet derives from `design/kaki-original.html`, preserved as a design reference.

## Core architecture

- **React 19 + TypeScript + Vite**, Recharts and Lucide icons.
- **FastAPI + Uvicorn** (`backend.main:create_app`), server serves the built React dist on Render.
- **Supabase PostgreSQL**, connected by `DATABASE_URL` (Session pooler URI recommended).
- Password hashing and HttpOnly cookies with CSRF and role-based access; each data operation is college-scoped and faculty/student-scoped.
- **Traditional ML**: scikit-learn RandomForest supervised classifier with train/holdout evaluation, 7 observed features, model saved per college in PostgreSQL (`pi3_ml_models`).
- Separate, explainable **rules-based score** from `backend/scoring.py`, which deliberately shows "insufficient data" if the college has not supplied fresh observations.

## What is implemented

| Area | Backed by server/database | Notes |
|---|---|---|
| College Admin / Faculty / Student login | Yes | Real accounts, server sessions, password change |
| College Admin students | Yes | `pi3_roster`, search/filter/pagination, create/edit, CSV export |
| Faculty student list | Yes | Assigned department/semester/section only |
| Student account | Yes | Links an actual student roll ID; reads only own record |
| Users / faculty accounts | Yes | Add role accounts; disable/enable; admin password reset |
| Supabase demo import | Yes | `public.colleges/students/faculty` -> pi3 tables, optional new role accounts |
| Subject assignments | Yes | Create/remove; no removal if historical entries exist |
| Attendance | Yes | Faculty enters present/absent per date and publishes |
| Marks | Yes | Faculty enters percentage; draft/publish; students see published only |
| College dashboard | Yes | Live department counts, coverage, score indicators, support flags |
| Student details | Yes | Student 360° evidence, published records and recommendations |
| Rule-based analytics | Yes | Academic and placement support, evidence coverage and filters |
| ML risk model | Yes | Supervised academic intervention classifier; real labels required |
| Synthetic-demo ML | Yes | Explicit synthetic label on screen; not real risk validation |
| Interventions | Yes | Create and update with optimistic version check and review notes |
| Student requests | Yes | Student creates; assigned faculty/admin reply and resolve |
| Announcements | Yes | Admin/faculty publish notices; audience checks |
| Timetable | Yes | Assigned classes; conflict check; role-filtered visibility |
| Audit | Yes | Recent database-backed actions |
| What-if scenarios | Yes | Existing server scenario endpoint for observed, fresh fields only |
| External sources | Partially | Existing configured connectors can preview/sync/remove; dedicated UI to create/edit mapping is not yet rebuilt |

**Not yet complete relative to every `kaki.html` mock screen:** dedicated department/course CRUD, all seven canonical data-source entry UIs, comprehensive placement/skill dashboards, assessment approval workflow (current marks can be published directly by authorized faculty), reports/PDF and email notifications, bulk timed schedule editing, automatic retraining pipelines, full mobile/browser E2E verification, and production-scale validation against a live Supabase project. Do not present those as completed features.

## Render environment variables

1. Go to **Supabase Dashboard → Project → Connect → Session pooler → URI**.
2. Copy the **whole PostgreSQL URI**, including username `postgres.<project-ref>`, password and host. Percent-encode special characters in the password. Append `?sslmode=require` if absent.
3. Render service → Environment: set `DATABASE_URL`, `APP_SECRET` (32+ chars), `BOOTSTRAP_COLLEGE_NAME`, `BOOTSTRAP_COLLEGE_DOMAIN`, `BOOTSTRAP_ADMIN_EMAIL`, `BOOTSTRAP_ADMIN_PASSWORD` (12+ chars). `COOKIE_SECURE=true`, `SEED_DEMO=false`, `IMPORT_LEGACY_V2=false`.
4. Push this project to GitHub and deploy Render with the root **Dockerfile**. Render builds React and runs Uvicorn. Check `/health`.
5. Log in with the configured administrator email and password.
6. Admin → **Supabase Import**. Optionally enter temporary 12+ character passwords to create 20 faculty and 250 student accounts. Existing accounts and their passwords are not overwritten.
7. Admin → **Teaching Assignments**. Verify every faculty member is assigned a class that actually exists in the students list (same `department`, `semester`, `section`).
8. Test: Admin sees 250 students → faculty sees students in their assigned classes → faculty publishes marks/attendance → student sees their own results → analytics updates from observed records.

**One Supabase project** is sufficient. The preexisting public `colleges`, `students`, and `faculty` demo tables are separate from the application's own `pi3_*` tables **inside the same database**.

## Run locally on Windows

Install Python 3.12, Node.js and PostgreSQL/Supabase credentials. In PowerShell inside the `PULSE` directory:

```powershell
$env:DATABASE_URL = 'postgresql://postgres.PROJECT_REF:ENCODED_PASSWORD@YOUR_POOLER_HOST:5432/postgres?sslmode=require'
$env:APP_SECRET = 'replace-with-a-long-private-random-key-32-or-more-characters'
$env:BOOTSTRAP_COLLEGE_NAME = 'Demo Engineering College'
$env:BOOTSTRAP_COLLEGE_DOMAIN = 'demo.edu.in'
$env:BOOTSTRAP_ADMIN_EMAIL = 'admin@demo.edu.in'
$env:BOOTSTRAP_ADMIN_PASSWORD = 'replace-with-a-private-12-plus-character-password'
$env:COOKIE_SECURE = 'false'
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-connectors.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

In another PowerShell window in `PULSE/frontend`:

```powershell
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. The dev server proxies `/api` to local FastAPI. `start_windows.bat` is a convenience launcher for CMD sessions where the environment variables are already set.

## Traditional ML and responsible demo labeling

The trained model predicts an **academic support outcome**, not a certified dropout outcome. The seven features are marks %, attendance %, LMS %, placement %, skills %, engagement %, backlog count. With **no later-outcome labels**, the app truthfully says `Not trained`. Admins can manually add at least **40 historical examples** with **8 positive and 8 negative** outcomes and train the model. Historic snapshots must predate the later outcome; don't use a present-day risk label as the target if it was generated from the same features. Training uses stratified 75/25 train/test split, RandomForest and holdout accuracy, precision, recall, AUC and feature importance.

For a hackathon walkthrough, **Train synthetic demo model** works without private labels but displays a persistent demo banner and must not be described as validated on real college students. `pi3_ml_models` saves the trained artifact in PostgreSQL to survive Render restarts. Predictions are only returned for students with at least two observed features.

## Tests and verification

- `python -m compileall -q backend` — passed in the creation environment.
- `pytest -q tests/test_tenants.py tests/test_extensions.py` — **12 passed** in the creation environment using SQLite and a temporary *test-only* stand-in for the missing `pwdlib` dependency. Production always installs `pwdlib[argon2]` from requirements, not the temporary stand-in.
- ML training and prediction — exercised locally with scikit-learn and confirmed synthetic model train/predict and no-label rejection.
- React/TypeScript JSX parsing — passed TypeScript transpilation syntax checks.
- **Not verified:** `npm ci && npm run build` in the creation environment (npm registry unreachable), an actual live Render/Supabase database, real account sign-ins, and end-to-end UI browser tests. Run a production frontend build in Render or locally before treating the app as release-ready.

## Credentials/security

Never put the PostgreSQL URI, Supabase service role key, student passwords or APP_SECRET in React files or GitHub. The browser only calls FastAPI via same-origin `/api`. Avoid importing real identifiable student records into public demos without explicit authorization.
