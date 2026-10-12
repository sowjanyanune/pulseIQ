# Challenge coverage and gap analysis

| Rubric / requirement | Working implementation | Where to demonstrate |
|---|---|---|
| Integration & analysis (30%) | Seven canonical sources joined by student ID and as-of period; atomic validation, duplicates/range/missing checks, provenance | CSV import, student component table |
| Success score & risk (25%) | Weighted score, missing-evidence policy, separate academic and placement triggers | Success Intelligence |
| Dashboard (25%) | Branch/period/segment/search filters, score table, segmentation bar chart, trend line, evidence drilldown | Success Intelligence; existing role screens |
| Problem understanding (10%) | Faculty-scoped records, human-reviewed actions, feedback without score penalty | Student detail, role portals |
| Demo (10%) | Repeatable 200-student fictional dataset and five-minute script | run_demo.py; DEMO_SCRIPT.md |
| Bonus segmentation | Six meaningful, overlapping groups | Segment filter and chart |
| Bonus explainability | Actual indicator values, weights, contribution, date/source, risk reasons | Student detail |
| AI | Optional Random Forest, held-out metrics, stored model and predictions | AI model evidence panel |

Changes from handoff: visible integrated analytics; operational marks/attendance
bridge; seven-source CSV ingestion; safe empty-college demo loader; trends; support
action UI; optional model controls; robust all-missing ML feature handling; startup
RLS/anon access protection; .env loading; ready-built frontend and clear launch scripts.

Boundaries: shared database with college_id isolation, not one physical database
per college; no automatic LAN database agent; no domain ownership verification;
no proven real-world predictive accuracy; no SMTP password recovery; no automated
intervention impact attribution. CGPA-to-percentage conversion is institution-specific
and must occur before canonical academic import. Current LMS/engagement/feedback
schemas use completion counts and support requests, not every example in the brief.
Supabase/Render instructions are provided but a live account deployment is not performed.

The supplied challenge brief is covered as a prototype. Scores awarded by judges,
byteXL acceptance, and institutional production readiness cannot be guaranteed.
