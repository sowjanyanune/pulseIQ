# PULSEIQ — KPMG / byteXL challenge prototype

React + FastAPI + Supabase PostgreSQL. Start with **START_HERE.md**.

This release adds a working Success Intelligence screen to the existing college,
faculty and student portals. It integrates seven categories, explains weighted
scores, shows academic and placement flags, segments and trends, supports what-if
analysis and records support actions. Optional Random Forest training is separate
from the rule-based score. Synthetic demo model performance is not real-world accuracy.

- `START_HERE.md`: quickest Windows run, Supabase connection and Render deployment.
- `docs/REQUIREMENTS_MATRIX.md`: challenge coverage and remaining limitations.
- `docs/SUCCESS_SCORE.md`: scoring explanation for judges.
- `docs/DEMO_SCRIPT.md`: five-minute demonstration.
- `docs/ML_DATA.md`: historical model training instructions.
- `docs/TEST_REPORT_CURRENT.md`: actual verification and boundaries.
- `database/01_application_schema.sql`: non-destructive schema setup.
- `templates/`: eight canonical CSV headers (roster plus seven categories).
- `frontend/dist/`: prebuilt frontend; no Node needed for the first local run.

Development: Python 3.12, Node 24. `python -m pip install -r requirements-dev.txt`,
`python -m pytest -q`, then `cd frontend`, `npm ci`, `npm run build`.
FastAPI serves the built UI and API together; no separate frontend hosting needed.

The original handoff files are retained in `reference_handoff/`; previous release
notes are historical and must not override START_HERE.md.
