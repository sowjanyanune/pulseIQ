# Verification for this release — 11 October 2026

- `npm ci`: passed with the supplied lockfile.
- `npm run build`: passed; bundled React production assets included. Vite reports
  a non-blocking large-bundle warning. Existing main.tsx uses @ts-nocheck, so this
  build must not be represented as complete static type coverage.
- `python -m pytest -q`: **28 passed**. One dependency deprecation warning.
- Tests cover role/college isolation, CSRF, registration, attendance edits and
  dates, marks/student performance, timetable, uploads, action optimistic locking,
  CSV validation rollback, seven-source score explanation, feedback, trends,
  operational marks/attendance integration, demo guard, model train/predict.
- Tests use SQLite via the app's explicit test configuration, not live Supabase.
- Browser workflow exercised through Chromium: admin sign-in, analytics filter,
  student drilldown, action creation/review, what-if, synthetic training/prediction.

Not verified: a live Supabase project, hosted Render deployment, Docker image build,
external database connector credentials, production load, domain ownership or
external predictive validity. A working local prototype is not a promise of
production readiness or a guaranteed challenge score.

Chromium desktop workflow completed with zero JavaScript page errors. A 390px
mobile check still reports horizontal overflow in the long analytics view; desktop
is the recommended judging/demo layout. Mobile layout is not fully verified.
