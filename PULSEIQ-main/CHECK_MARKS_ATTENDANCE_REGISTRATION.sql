-- PULSEIQ OCTOBER 2026: READ-ONLY DIAGNOSTICS (SUPABASE SQL EDITOR)
-- Does not create or change records, passwords or security policies.

-- 1. Check college names, registered domains and optional timezone settings.
SELECT c.name AS college_name, c.domain AS login_domain,
       COALESCE(p.configuration->>'timezone', 'Asia/Kolkata') AS college_timezone
FROM public.pi3_colleges c
LEFT JOIN public.pi3_college_preferences p ON p.college_id=c.id
ORDER BY c.name;

-- 2. Count modern exam marks, older published marks, attendance sessions and saved marks.
SELECT 'Exam marks (new Marks Entry)' AS item, COUNT(*) AS total
FROM public.pi3_exam_results
UNION ALL
SELECT 'Previously published marks', COUNT(*)
FROM public.pi3_entries WHERE kind='marks' AND status='published' AND marks_pct IS NOT NULL
UNION ALL
SELECT 'Old marks still in draft', COUNT(*)
FROM public.pi3_entries WHERE kind='marks' AND status='draft'
UNION ALL
SELECT 'Attendance class sessions', COUNT(*)
FROM public.pi3_class_sessions
UNION ALL
SELECT 'Individual attendance marks', COUNT(*)
FROM public.pi3_class_attendance;

-- 3. Inspect recent marks actually saved by faculty (new Marks Entry screen).
SELECT c.name AS college, a.department AS branch, a.semester, a.section,
       a.subject, r.student_id AS roll_number, r.full_name,
       m.exam_name, m.exam_date, m.marks, m.maximum, m.updated_at
FROM public.pi3_exam_results m
JOIN public.pi3_assignments a ON a.id=m.assignment_id
JOIN public.pi3_roster r ON r.id=m.roster_id
JOIN public.pi3_colleges c ON c.id=m.college_id
ORDER BY m.updated_at DESC LIMIT 40;

-- 4. Check whether any older marks exist in legacy table.
SELECT a.subject, a.department, a.semester, a.section,
       r.student_id AS roll_number, e.period_end, e.marks_pct, e.status
FROM public.pi3_entries e
JOIN public.pi3_assignments a ON a.id=e.assignment_id
JOIN public.pi3_roster r ON r.id=e.roster_id
WHERE e.kind='marks'
ORDER BY e.updated_at DESC LIMIT 40;

-- 5. Check current attendance, if any.
SELECT c.name AS college, a.subject, a.department, a.semester, a.section,
       s.on_date, s.time_slot, s.topic,
       COUNT(*) AS students_marked,
       COUNT(*) FILTER (WHERE x.present) AS present,
       COUNT(*) FILTER (WHERE NOT x.present) AS absent
FROM public.pi3_class_sessions s
JOIN public.pi3_assignments a ON a.id=s.assignment_id
JOIN public.pi3_colleges c ON c.id=s.college_id
LEFT JOIN public.pi3_class_attendance x ON x.session_id=s.id
GROUP BY c.name, a.subject, a.department, a.semester, a.section, s.on_date, s.time_slot, s.topic
ORDER BY s.on_date DESC LIMIT 40;

-- IMPORTANT:
-- A populated pi3_exam_results table is required for NEW exam-wise marks.
-- Published older pi3_entries marks are included as compatibility fallback.
-- A registration invite code is stored in Render, NOT in Supabase tables.
