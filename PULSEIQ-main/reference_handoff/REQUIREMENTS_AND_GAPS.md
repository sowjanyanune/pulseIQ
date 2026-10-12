# PULSEIQ — REQUIREMENTS, DECISIONS, AND VERIFICATION GAPS

## 1. Original hackathon problem

KPMG in India / byteXL: **AI-Powered Student Analytics and Success Platform** — Smart Campus Analytics: Predict, Optimize & Improve Student Success. It must integrate seven categories into a unified student view and support proactive decision intelligence (not merely static dashboard):

| Category | Expected data |
|---|---|
| Academic | CGPA, internal/exam marks, backlogs, subject performance |
| Attendance | Overall and subject-wise attendance |
| LMS | Login frequency, assignment completion |
| Engagement | Events, clubs, hackathons, certifications |
| Placement | Aptitude, coding, mock interviews |
| Skills | Technical and soft-skill assessments |
| Feedback | Student satisfaction and faculty feedback |

Expected deliverables: **working dashboard prototype integrated with data**; short explanation of **Student Success Score** (indicators, weights/combination); short demo or slides. Bonus features: **student segmentation** (e.g. academically strong but weak placement readiness) and **explainable score/risk drivers**. The project also discusses traditional ML prediction and actionable interventions.

## 2. Latest user-selected application/architecture

- New Aurora-inspired look: quiet glittering mixed gradients, glass cards, soft backlight hover, slow floating transitions, optional subtle moving light bars. Real React components, not an image background pretending to be UI.
- Frontend: **React + TypeScript + Vite**.
- API: **FastAPI + Python + Uvicorn**.
- Database: **Supabase PostgreSQL** via a private backend `DATABASE_URL`; backend deploy to **Render**.
- College public registration **without an invite code**; administrator password and all new passwords **minimum 6 characters**, as specifically requested.
- Three **separate role logins**: Admin, Faculty and Student; role-scoped data.
- Each college has **its own preferences/workspace**. User originally requested **a separate database for every college**. Current code instead implements **college_id isolation in one shared Supabase database**, which does NOT meet the literal physical-database requirement. Do not misrepresent this.
- Frontend should require sign-in on initial load per later user request (verify current behavior).

## 3. Final detailed page design requirements (latest user instructions)

### ADMIN
- Remove extra grouped nav sections such as “Overview”, etc.
- Rename Command Center to **Dashboard**; dashboard should show **ONLY** graphical/pie charts of **student counts by branch** and **faculty counts by branch**; remove other dashboard content.
- **Student Directory:** branch + section filters, student search, add student **with email and password**, edit/manage as appropriate.
- **Student Analytics:** calculate each student's **success rate from real recorded marks**, show student interests by branch, remove extraneous panels. Respect that no marks = no meaningful marks success score.
- Hide/remove **Machine Learning tab**, **Teaching Assignments tab**, **Assignments and Tests tab**, **Improvement Insights tab**, **Marks and Publishing**, **Interventions**, duplicate “Improve Insights” screens. Note: faculty/class teaching assignments still have to exist as an Admin-controlled capability so permissions and teaching work.
- **Attendance:** record faculty attendance in Admin; student attendance is posted/corrected **only by authorized Faculty**, not by Admin.
- **Timetable:** Admin adds faculty time slots/subject/day; updated timetable appears in the matching Faculty and Student portals. Support different timetable for every day/branch/section.
- Retain necessary announcements/account and institutional settings as applicable.

### FACULTY
- Remove Success/Academic/Support nav group dividers, faculty dashboard, My Classes, Learning Resources, ML Risk Insights, Mentoring/Intervention.
- **My Students:** roll number, name, department/branch, section, email, phone number.
- Rename “Student Focus Areas” to **Student Success Insight**: faculty's students, interests/achievements, performance-based guidance; **search by name or roll number** plus branch and section filters.
- **Attendance:** faculty selects assigned branch+section (+subject), all matching students appear, Present/Absent per student, attendance date, time slot, topic taught; **save and later correct** in Supabase. Do not allow unrelated faculty to change it.
- **Marks Entry:** selects the assigned subject/class and branch/section; enters marks for listed students by exam directly. Save to database; show in student Performance and class analytics.
- **Timetable:** view Admin-assigned timetable; Faculty cannot independently add it.
- **Class Analytics:** pass/fail % for selected branch/section/class using recorded marks; attendance fall % and list of students below college minimum attendance. If attendance is not recorded, show “No data”; never crash or invent attendance.
- Retain announcements and account tools.

### STUDENT
- Remove group nav dividers, student dashboard, Success Insights, ML Risk Insights tab, My Focus Areas, separate Marks & Results, Support Plans.
- **My Profile:** ONLY signed-in student's profile; no student search or department dropdown; show more detail and controlled edits where appropriate.
- **Performance:** marks of ALL recorded exams, **upload achievements and certifications**.
- **Risk Insights:** weak-scoring subjects, official backlogs if present; do not treat every failed internal exam as official backlog.
- **Attendance:** student's aggregate % from Faculty-marked classes with selectable time duration/date range.
- **Timetable:** different subjects/slots by weekday, supplied by Admin.
- **Assignments and Tests:** upcoming work/exams for the student.
- Retain **Announcements** and **My Account**.

## 4. Source-code feature locations — to verify, not assume finished

| Area | Code to inspect |
|---|---|
| React routes/menu/screens | `PULSE/frontend/src/main.tsx` |
| Browser API wrapper and error handling | `PULSE/frontend/src/api.ts` |
| Gradients, hover/floating animations | `PULSE/frontend/src/styles.css` |
| Auth / roles / sessions / import / assignments / timetable | `PULSE/backend/api_v3.py`, `tenant_auth.py`, `tenant_data.py` |
| College registration + preferences | `PULSE/backend/college_setup.py` |
| Directory, attendance, marks, success, class analytics, student performance/certificates | `PULSE/backend/campus_pages.py` |
| Assignments, tests, resources, student focus recommendations | `PULSE/backend/learning.py` |
| Scoring/ML | `PULSE/backend/scoring.py`, `traditional_ml.py` |
| Database models | `PULSE/backend/tenant_db.py` |
| Render Docker deployment | `PULSE/Dockerfile`, `render.yaml`, `requirements.txt` |
| Supabase setup & checks | `PULSE/SUPABASE_SQL_SETUP.sql`, `database/` |

## 5. User-observed problems (historical, must verify after latest deployment)

- Supabase source had **250 students and 20 faculty**. At one stage `pi3_roster` was 0; after repair roster became **250**, but `pi3_accounts` student logins and faculty logins and `pi3_assignments` were **0**. These were historic screenshots; do not assume current counts without running queries.
- Source college `demo.edu.in` vs app `democollege.edu.in` caused import mismatch. Source-college mapping was subsequently changed; check real DB rather than assuming.
- Faculty Attendance screen matched **5 CSE semester 1 section A** students but initially showed “Cannot take future attendance” for Oct 11, 2026 (India UTC date edge). Newer source attempts a timezone-aware fix; recheck live.
- College registration screenshot initially used an **email in the domain field**, which is invalid. Newest release removes the invite-code field and lowers password minimum, but live registration was not revalidated here.
- Faculty Class Analytics screenshot displayed **server starting/unavailable**; newer source includes a fix for calculating class analytics when marks exist but attendance sessions are zero, plus legacy marks fallback. Need inspect live API/status and query data.
- Marks were submitted but previously did not appear in class analytics; check `pi3_exam_results` and any `pi3_entries` historical published scores and re-run relevant API.

## 6. Known gaps / tensions vs original challenge

1. **Seven data categories vs marks-only visible Success Rate.** Latest UI request intentionally narrowed “Student Analytics” to marks and interests. However, original evaluation expects all seven categories integrated into an actionable, explainable multi-factor Success Score and risk assessment. Need reconcile without cluttering UI; perhaps keep marks-based academic success separate and show a concise institution-approved multi-factor score elsewhere.
2. **Physical per-college database vs shared tenant DB.** Current code supports shared Supabase project and college-scoped records, NOT automatic dedicated databases. If literal separate databases are mandatory, design secure provisioning and migration. Never claim this is already built.
3. **Actions and interventions:** Original challenge rewards actionable support but newest UI explicitly removed interventions/mentoring. Consider recommendations and traceable support workflows that respect requested streamlined screens.
4. **Traditional ML:** Backend has ML endpoints, but latest UI hides Machine Learning tab. Verify if model is legitimately trained with historical labeled outcomes and evaluate on held-out data; don't claim synthetic data achieves real-world performance.
5. **Permissions/security:** Public college registration without domain verification can allow domain squatting/impersonation. 6-character minimum accepted for demo but weaker security. Need rate limiting, email verification, tenant isolation tests, backups, logging and security review before real institutions.
6. **Data flow:** Verify source `students`/`faculty` → `pi3_roster` + `pi3_accounts` + `pi3_assignments` → class students → attendance/marks → student portals/analytics. Merely connecting `DATABASE_URL` is insufficient.
7. **Tests/deployment:** Full Vite/React production build, real Render, live Supabase, browser-based workflow and accessibility tests are NOT independently verified in this handoff.
8. **Documentation:** Some older README and start files conflict with current release; see `READ_ME_FIRST.md`.
9. **Certificate storage and time tables:** Review access control, file size/type/security, timetable collision detection, editing/deletion, and day-wise per-section visibility.
10. **Evaluation deliverables:** Create a one-page Success Score methodology and demo/slides based on what is actually working, not illustrated sample numbers.

## 7. Recommended review order for the next chat

A. Build frontend/backend in clean environment and run complete automated tests. B. Verify live database and role authentication. C. Run 250/20 importer or account/assignment provisioning. D. Test attendance and marks end-to-end; confirm Class Analytics and Student Performance updates. E. Check every requested screen/feature and original challenge rubric, prioritize missing features. F. Harden multi-college isolation + registration. G. Produce tested revised ZIP with deployment instructions and honest feature matrix.
