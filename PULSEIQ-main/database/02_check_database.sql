-- Supabase SQL Editor: check PULSEIQ and the new page-specific tables.
SELECT schemaname,tablename,rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'pi3_%' ORDER BY tablename;
SELECT 'students in application roster' AS item,COUNT(*) AS total FROM public.pi3_roster
UNION ALL SELECT 'student login accounts',COUNT(*) FROM public.pi3_accounts WHERE role='student'
UNION ALL SELECT 'faculty login accounts',COUNT(*) FROM public.pi3_accounts WHERE role='faculty'
UNION ALL SELECT 'teaching assignments',COUNT(*) FROM public.pi3_assignments
UNION ALL SELECT 'timetable slots',COUNT(*) FROM public.pi3_timetable
UNION ALL SELECT 'faculty class sessions',COUNT(*) FROM public.pi3_class_sessions
UNION ALL SELECT 'student attendance marks',COUNT(*) FROM public.pi3_class_attendance
UNION ALL SELECT 'student exam results',COUNT(*) FROM public.pi3_exam_results
UNION ALL SELECT 'student achievements',COUNT(*) FROM public.pi3_student_achievements;
