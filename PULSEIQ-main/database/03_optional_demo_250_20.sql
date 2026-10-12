-- OPTIONAL fictional source/demo data for a brand-new demo setup.
-- Do NOT run if you already have real college tables or are connecting production data.
-- Source email addresses can differ from application domain; source college domain must MATCH.
-- Does not create any login accounts. Admin > Supabase Import creates hashed logins.
BEGIN;
CREATE TABLE IF NOT EXISTS public.colleges (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 college_code VARCHAR(30) UNIQUE NOT NULL,
 college_name VARCHAR(200) NOT NULL,
 email_domain VARCHAR(150) UNIQUE NOT NULL,
 address TEXT,
 created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS public.students (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 college_id BIGINT REFERENCES public.colleges(id) NOT NULL,
 roll_number VARCHAR(50) NOT NULL,
 full_name VARCHAR(150) NOT NULL,
 email VARCHAR(200) NOT NULL UNIQUE,
 department VARCHAR(100),
 academic_year INTEGER,
 semester INTEGER,
 section VARCHAR(20),
 created_at TIMESTAMPTZ DEFAULT now(),
 UNIQUE(college_id,roll_number)
);
CREATE TABLE IF NOT EXISTS public.faculty (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 college_id BIGINT REFERENCES public.colleges(id) NOT NULL,
 employee_id VARCHAR(50) NOT NULL,
 full_name VARCHAR(150) NOT NULL,
 email VARCHAR(200) NOT NULL UNIQUE,
 department VARCHAR(100),
 designation VARCHAR(100),
 subject_code VARCHAR(30),
 subject_name VARCHAR(150),
 assigned_year INTEGER,
 assigned_semester INTEGER,
 assigned_section VARCHAR(10),
 created_at TIMESTAMPTZ DEFAULT now(),
 UNIQUE(college_id,employee_id)
);
ALTER TABLE public.faculty ADD COLUMN IF NOT EXISTS subject_code VARCHAR(30);
ALTER TABLE public.faculty ADD COLUMN IF NOT EXISTS subject_name VARCHAR(150);
ALTER TABLE public.faculty ADD COLUMN IF NOT EXISTS assigned_year INTEGER;
ALTER TABLE public.faculty ADD COLUMN IF NOT EXISTS assigned_semester INTEGER;
ALTER TABLE public.faculty ADD COLUMN IF NOT EXISTS assigned_section VARCHAR(10);
INSERT INTO public.colleges(college_code,college_name,email_domain,address)
VALUES ('DEMO001','Demo Engineering College','democollege.edu.in','Andhra Pradesh, India')
ON CONFLICT (college_code) DO NOTHING;
WITH nums AS (
 SELECT n,(ARRAY['CSE','ECE','EEE','MECH','CIVIL'])[1+((n-1)/50)::int] AS dept,
  (ARRAY['Aarav','Vivaan','Aditya','Arjun','Sai','Rohan','Karthik','Harsha','Pranav','Nikhil','Rahul','Varun','Manoj','Tejas','Charan','Ananya','Diya','Sneha','Priya','Kavya','Meghana','Sravani','Lakshmi','Pooja','Nandini'])[1+((n-1)%25)] AS given_name,
  (ARRAY['Reddy','Sharma','Naidu','Rao','Patel','Kumar','Varma','Chowdary','Iyer','Nair'])[1+(((n-1)/25)%10)::int] AS family_name
 FROM generate_series(1,250) AS n
)
INSERT INTO public.students(college_id,roll_number,full_name,email,department,academic_year,semester,section)
SELECT c.id,'26'||nums.dept||LPAD(nums.n::text,4,'0'),nums.given_name||' '||nums.family_name,
 'student'||LPAD(nums.n::text,3,'0')||'@demo.edu.in',nums.dept,
 1+((nums.n-1)%4),1+2*((nums.n-1)%4),(ARRAY['A','B','C'])[1+((nums.n-1)%3)]
FROM nums JOIN public.colleges c ON c.college_code='DEMO001'
ON CONFLICT (college_id,roll_number) DO NOTHING;
WITH f(n,dept,subcode,subject,sem) AS (
 VALUES(1,'CSE','CSE101','Programming Fundamentals',1),(2,'CSE','CSE301','Data Structures',3),(3,'CSE','CSE501','DBMS',5),(4,'CSE','CSE701','Machine Learning',7),
 (5,'ECE','ECE101','Basic Electronics',1),(6,'ECE','ECE301','Signals and Systems',3),(7,'ECE','ECE501','Digital Communication',5),(8,'ECE','ECE701','Embedded Systems',7),
 (9,'EEE','EEE101','Basic Electrical Engineering',1),(10,'EEE','EEE301','Electrical Machines',3),(11,'EEE','EEE501','Power Systems',5),(12,'EEE','EEE701','Smart Grids',7),
 (13,'MECH','ME101','Engineering Mechanics',1),(14,'MECH','ME301','Thermodynamics',3),(15,'MECH','ME501','Machine Design',5),(16,'MECH','ME701','CAD CAM',7),
 (17,'CIVIL','CE101','Engineering Drawing',1),(18,'CIVIL','CE301','Structural Analysis',3),(19,'CIVIL','CE501','Geotechnical Engineering',5),(20,'CIVIL','CE701','Transportation Engineering',7)
)
INSERT INTO public.faculty(college_id,employee_id,full_name,email,department,designation,subject_code,subject_name,assigned_year,assigned_semester,assigned_section)
SELECT c.id,'FAC'||LPAD(f.n::text,3,'0'),
 'Demo Faculty '||LPAD(f.n::text,3,'0'),'faculty'||LPAD(f.n::text,3,'0')||'@demo.edu.in',
 f.dept,'Assistant Professor',f.subcode,f.subject,(f.sem+1)/2,f.sem,(ARRAY['A','B','C'])[1+((f.n-1)%3)]
FROM f JOIN public.colleges c ON c.college_code='DEMO001'
ON CONFLICT (college_id,employee_id) DO NOTHING;
ALTER TABLE public.colleges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.students ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.faculty ENABLE ROW LEVEL SECURITY;
COMMIT;
SELECT (SELECT COUNT(*) FROM public.students s JOIN public.colleges c ON c.id=s.college_id WHERE c.college_code='DEMO001') AS demo_students,
       (SELECT COUNT(*) FROM public.faculty f JOIN public.colleges c ON c.id=f.college_id WHERE c.college_code='DEMO001') AS demo_faculty;
