# PULSEIQ source college import fix

## Root cause confirmed by user's SQL screenshots
- `public.students` = 250; `public.faculty` = 20.
- Application `pi3_roster` = 0; `pi3_accounts` = 1 admin; `pi3_assignments` = 0.
- Source college domain `demo.edu.in` did not match application college domain `democollege.edu.in`.
- Even after updating `public.colleges.email_domain`, the original backend rejected demo students and faculty with emails ending `@demo.edu.in` because it required `@democollege.edu.in`, so login accounts would not be created.

## Corrections included
- The admin import still REQUIRES an exact domain match between `public.colleges.email_domain` and the authenticated user's `pi3_colleges.domain` (college tenancy boundary).
- When importing records from that matched source college, validates their email syntax rather than requiring email to use the college's login domain. Existing passwords are preserved.
- Protects globally unique account emails already belonging to another college.
- Import is idempotent for roster, accounts and teaching assignments.
- Added `GET /api/admin/import-supabase/status` for tenant-scoped source/import counts, and Admin Supabase Import UI counts.
- Source data stays in `public.students` and `public.faculty` and is not deleted or overwritten.

## Deploy
1. In Supabase run `SQL_IMPORT_ROSTER_FIRST.sql`, which matches the source college by updating the source college domain and imports the 250 students into `pi3_roster` without adding login accounts.
2. Deploy this project on Render using the existing `DATABASE_URL`, `APP_SECRET`, and bootstrap variables. Do not reset or delete the database.
3. Sign in as the existing administrator; go to **Supabase Import**. Check that **Domain matches** is MATCH.
4. Fill both temporary passwords (12+ characters). Press **Import students and faculty**.
5. Verify `source_students=250`, `roster_students=250`, `student_accounts=250`, `faculty_accounts=20`; assignments typically up to 20, dependent on source assignment values.
6. Sign in as `student001@demo.edu.in` and `faculty001@demo.edu.in` with the passwords you supplied. The old demo emails need not match `democollege.edu.in` for login to succeed.
7. Review the faculty assignments; faculty see only their assigned semester, section and department.

## What is NOT claimed
- No live Supabase connection or Render deployment was run in this sandbox.
- Backend integration tests are blocked locally by a missing `pwdlib` dependency (network installs unavailable); Python compilation succeeded.
- This fix addresses the **import/login/roster** path, not proof that every UI feature or trained ML model is correct.
- ML requires historical labeled outcomes for validation; synthetic demo data alone cannot establish model performance.
