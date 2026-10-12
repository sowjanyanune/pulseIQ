-- PULSEIQ Faculty Attendance: read-only Supabase diagnostics.
-- Run in Supabase > SQL Editor; no data is changed.
-- 1. Verify the tables were created by the current backend/schema.
SELECT to_regclass('public.pi3_roster') AS student_roster,
       to_regclass('public.pi3_accounts') AS login_accounts,
       to_regclass('public.pi3_assignments') AS teaching_assignments,
       to_regclass('public.pi3_timetable') AS timetable,
       to_regclass('public.pi3_class_sessions') AS class_sessions,
       to_regclass('public.pi3_class_attendance') AS class_attendance;

-- 2. Count faculties and assignments for each registered college.
SELECT c.name AS college,
       (SELECT count(*) FROM public.pi3_accounts a
        WHERE a.college_id=c.id AND a.role='faculty' AND a.active) AS faculty_logins,
       (SELECT count(*) FROM public.pi3_assignments a
        WHERE a.college_id=c.id) AS teaching_assignments,
       (SELECT count(*) FROM public.pi3_roster r
        WHERE r.college_id=c.id AND r.active) AS active_students
FROM public.pi3_colleges c ORDER BY c.name;

-- 3. Exactly matched student counts for EACH teaching assignment.
-- If matched_students=0, attendance cannot be recorded for that class.
SELECT c.name AS college,
       f.full_name AS faculty_name,
       f.email AS faculty_email,
       a.id AS assignment_id,
       a.department AS branch,
       a.semester,
       a.section,
       a.subject,
       COUNT(r.id) AS matched_students
FROM public.pi3_assignments a
JOIN public.pi3_colleges c ON c.id=a.college_id
JOIN public.pi3_accounts f ON f.id=a.faculty_id AND f.college_id=a.college_id
LEFT JOIN public.pi3_roster r ON r.college_id=a.college_id
     AND r.department=a.department
     AND r.semester=a.semester
     AND r.section=a.section
     AND r.active=true
GROUP BY c.name,f.full_name,f.email,a.id,a.department,a.semester,a.section,a.subject
ORDER BY c.name,f.full_name,a.department,a.semester,a.section,a.subject;

-- 4. Student counts by actual branch + semester + section.
-- Use these exact values when Admin assigns a teaching subject.
SELECT c.name AS college,r.department AS branch,r.semester,r.section,
       COUNT(*) AS enrolled_students
FROM public.pi3_roster r
JOIN public.pi3_colleges c ON c.id=r.college_id
WHERE r.active=true
GROUP BY c.name,r.department,r.semester,r.section
ORDER BY c.name,r.department,r.semester,r.section;

-- 5. After a successful save, recent sessions appear here.
-- If the first query shows class_sessions is NULL, run the updated schema script first.
SELECT c.name AS college,f.full_name AS faculty_name,
       a.department,a.semester,a.section,a.subject,
       s.on_date,s.time_slot,s.topic,
       COUNT(p.id) AS students_marked,
       COUNT(p.id) FILTER (WHERE p.present=true) AS present,
       COUNT(p.id) FILTER (WHERE p.present=false) AS absent
FROM public.pi3_class_sessions s
JOIN public.pi3_assignments a ON a.id=s.assignment_id
JOIN public.pi3_colleges c ON c.id=s.college_id
JOIN public.pi3_accounts f ON f.id=s.created_by
LEFT JOIN public.pi3_class_attendance p ON p.session_id=s.id AND p.college_id=s.college_id
GROUP BY c.name,f.full_name,a.department,a.semester,a.section,a.subject,s.id,s.on_date,s.time_slot,s.topic
ORDER BY s.on_date DESC,s.time_slot DESC
LIMIT 30;
