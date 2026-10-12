# PULSEIQ role-page update — October 2026

This release implements the requested Admin, Faculty and Student page changes while keeping the existing Supabase student roster and backend architecture.

## Important existing-data migration behavior

- Existing `pi3_roster` students (including your 250 imported students) remain. No destructive SQL is included.
- `pi3_accounts` entries remain. If student/faculty login counts are zero, use **Admin → Supabase Import** and supply temporary passwords (12+ characters); merely importing roster rows does not create logins.
- Existing faculty `pi3_assignments` link teaching subjects to a semester, department and section. Faculty & Subjects has a form to create them.
- **New** individual attendance sessions are stored in `pi3_class_sessions` and `pi3_class_attendance`. Old aggregated `pi3_entries` attendance is retained but not silently converted into per-class sessions because it lacks topic/time-slot data.
- **New** individual exam marks are stored in `pi3_exam_results`. Old overall published `pi3_entries` marks remain but are not silently converted to named exams (the old records contain no exam name).
- Student phone/interests now live in `pi3_student_contacts`; existing source student data might not include phone numbers. Blank information is displayed as `—` rather than invented.
- Official backlog records may come from non-synthetic academic observation imports; an exam score below passing does not equal a confirmed academic backlog.

## New endpoints

`/api/v4/dashboard`, `/api/v4/directory`, `/api/v4/students`, `/api/v4/student/me`, `/api/v4/student/interests`, `/api/v4/faculty`, `/api/v4/faculty/attendance`, `/api/v4/class/{assignment_id}/students`, `/api/v4/attendance/batch`, `/api/v4/attendance/session`, `/api/v4/attendance/report`, `/api/v4/marks/batch`, `/api/v4/marks/exam`, `/api/v4/performance`, `/api/v4/success`, `/api/v4/class-analytics`, `/api/v4/achievements`, `/api/v4/achievements/{id}/file`; `DELETE /api/timetable/{id}`.

The existing authentication, import, notifications, college registration, preferences and assignment/test endpoints are reused. API documentation is available at `/api/docs` if `ENABLE_API_DOCS=true` (avoid enabling publicly unless necessary).

## Database and deployments

1. Render redeploys this project and creates missing tables on startup.
2. If you need to create or inspect SQL manually, run `SUPABASE_SQL_SETUP.sql` (safe, no DROP) and `database/02_check_database.sql` in Supabase SQL Editor.
3. Verify the Admin/Faculty/Student logins; test attendance, marks and class timetable with one assigned subject.
4. Only then enter college records at scale. Store Render secrets privately.

**Tenant model:** separate college workspaces scoped by college ID in a **shared Supabase PostgreSQL database**. Dedicated physical Supabase databases are not created automatically.

**Validation:** 18 backend tests passed locally using SQLite test fixtures; TypeScript TSX parsing and `tsc` completed; full Vite production build and live Render/Supabase end-to-end checks are outstanding due to offline npm in this environment.
