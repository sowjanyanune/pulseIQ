# Developer commands and extension points

Cloud setup in `START_HERE.md` requires no local runtime. Team changes can be pushed to GitHub and deployed against the existing hosted database. The following commands are optional for developers and automated CI.

## Build and test

Use Python 3.12 and Node 24. From the project root:

```text
python -m venv .venv
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
```

Activate that environment before installing on your platform, or run its Python explicitly. Unit/API tests use an isolated temporary SQLite database when no PostgreSQL test URL is supplied. SQLite is test-only; production settings reject it.

```text
cd frontend
npm ci
npm run build
```

The lockfile pins the tested frontend dependency graph. Docker uses this build and packages the output behind FastAPI. `frontend/dist` is ignored by Git; Render rebuilds it from source.

To run tests against PostgreSQL, set `PULSEIQ_TEST_DATABASE_URL` to an isolated QA database. The fixture creates a unique schema for each test and drops that schema afterward. Never point tests at the institutional application database. The included GitHub Actions workflow supplies its own PostgreSQL service.

For browser integration checks, install Chromium with `python -m playwright install chromium`, build the frontend and run `python scripts/browser_check.py`. It starts a private test server/database and exercises the real UI. Screenshots/logs go to a temporary QA directory unless you supply `--output`. This test does not start or create a hosted account.

## Optional local development with a cloud database

If a developer needs interactive debugging, use an isolated Neon development branch/database and set `DATABASE_URL`, `APP_SECRET` (32+ characters), `BOOTSTRAP_ADMIN_PASSWORD` (12+ characters), `SEED_DEMO=true`. Use `COOKIE_SECURE=false` only for localhost HTTP and keep `.env` untracked. The included server reads process environment variables; `.env.example` is a reference, not an automatic configuration loader.

Build React, then run:

```text
python -m uvicorn backend.main:create_app --factory --host 127.0.0.1 --port 8000
```

For frontend hot reload run `npm run dev` in `frontend`; Vite proxies `/api` to `127.0.0.1:8000`. In production use the Render HTTPS URL with `COOKIE_SECURE=true`.

## Extension points

- Edit `backend/config.json` for reviewed rules/weights/thresholds; update the displayed Method explanation and increment `scoring_version` when rules change.
- Edit `connectors/mapping.json` or add a source-specific adapter to `backend/connectors.py` for institution schemas or paginated/OAuth vendor APIs.
- Add database migrations before changing existing table columns. Current startup creates initial tables only.
- Add a proper staff-account lifecycle/SSO if required by the institute. Initial staff creation is implemented; password recovery and account editing are not.
- Add scheduled synchronization, paginated cohort APIs and batch ingestion if required for a larger deployment. They are not enabled in this initial version.
- Use appropriate Neon backups and an agreed restore test; a GitHub code rollback does not restore application records.

Do not commit `.env`, source credentials, real student records, node_modules, virtual environments or database snapshots. The public repository is for code and fictional demo generation only.
