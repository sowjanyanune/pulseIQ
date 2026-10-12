-- PULSEIQ immediate recovery (source => admin roster).
-- Run in Supabase SQL Editor for the ONE Demo Engineering College only.
-- Review the college names/domains before running on real institutional data.
-- Does NOT create passwords or grant account access; use Admin Import afterwards.
BEGIN;
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM public.pi3_colleges WHERE lower(domain)='democollege.edu.in')
 THEN RAISE EXCEPTION 'Expected PULSEIQ college democollege.edu.in does not exist; inspect SELECT * FROM public.pi3_colleges first'; END IF;
 IF NOT EXISTS (SELECT 1 FROM public.colleges WHERE college_code='DEMO001')
 THEN RAISE EXCEPTION 'Source college DEMO001 missing'; END IF;
END $$;

-- Keep existing admin login and PULSEIQ college; correct source college mapping only.
UPDATE public.colleges
SET email_domain = 'democollege.edu.in'
WHERE college_code='DEMO001' AND lower(email_domain) IN ('demo.edu.in','democollege.edu.in');

-- Student roster uses the original source emails (@demo.edu.in), which is valid.
INSERT INTO public.pi3_roster
  (id,college_id,student_id,full_name,email,department,semester,section,active)
SELECT gen_random_uuid()::text, p.id, s.roll_number, s.full_name,
       lower(s.email), COALESCE(NULLIF(s.department,''),'Unassigned'),
       COALESCE(s.semester,1), COALESCE(NULLIF(s.section,''),'A'), TRUE
FROM public.students s
JOIN public.colleges src ON src.id=s.college_id AND src.college_code='DEMO001'
JOIN public.pi3_colleges p ON lower(p.domain)=lower(src.email_domain)
ON CONFLICT (college_id,student_id) DO UPDATE
SET full_name=EXCLUDED.full_name, email=EXCLUDED.email,
    department=EXCLUDED.department, semester=EXCLUDED.semester,
    section=EXCLUDED.section, active=TRUE;
COMMIT;

SELECT 'Source students' AS item, count(*) FROM public.students s
 JOIN public.colleges c ON c.id=s.college_id WHERE c.college_code='DEMO001'
UNION ALL
SELECT 'Admin roster students', count(*) FROM public.pi3_roster r
 JOIN public.pi3_colleges p ON p.id=r.college_id WHERE lower(p.domain)='democollege.edu.in'
UNION ALL
SELECT 'Student login accounts', count(*) FROM public.pi3_accounts WHERE role='student'
UNION ALL
SELECT 'Faculty login accounts', count(*) FROM public.pi3_accounts WHERE role='faculty'
UNION ALL
SELECT 'Teaching assignments', count(*) FROM public.pi3_assignments;
