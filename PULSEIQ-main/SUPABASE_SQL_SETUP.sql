-- PULSEIQ Role Pages · Supabase PostgreSQL schema

-- Safe to rerun on an existing PULSEIQ Supabase project. No DROP/DELETE.

-- Supabase > SQL Editor > New query > paste this SQL.

-- The FastAPI service also creates missing tables on startup.

-- This script does not create any login passwords; use the Admin interface.



BEGIN;

CREATE TABLE IF NOT EXISTS pi3_attempts (
	id VARCHAR(36) NOT NULL, 
	identity_hash VARCHAR(64), 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_attempts_identity_hash ON pi3_attempts (identity_hash);

CREATE TABLE IF NOT EXISTS pi3_colleges (
	id VARCHAR(36) NOT NULL, 
	name VARCHAR(150) NOT NULL, 
	domain VARCHAR(150) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (domain)
);

CREATE TABLE IF NOT EXISTS pi3_accounts (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	email VARCHAR(250) NOT NULL, 
	full_name VARCHAR(150) NOT NULL, 
	password_hash VARCHAR(300) NOT NULL, 
	role VARCHAR(20) NOT NULL, 
	departments JSON NOT NULL, 
	student_id VARCHAR(100), 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	UNIQUE (email)
);

CREATE INDEX IF NOT EXISTS ix_pi3_accounts_college_id ON pi3_accounts (college_id);

CREATE TABLE IF NOT EXISTS pi3_audit (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	actor_id VARCHAR(36), 
	event VARCHAR(90) NOT NULL, 
	details JSON NOT NULL, 
	at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_audit_college_id ON pi3_audit (college_id);

CREATE TABLE IF NOT EXISTS pi3_college_preferences (
	college_id VARCHAR(36) NOT NULL, 
	configuration JSON NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (college_id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE TABLE IF NOT EXISTS pi3_connections (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	name VARCHAR(150) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	encrypted_dsn VARCHAR(6000) NOT NULL, 
	mapping JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE TABLE IF NOT EXISTS pi3_ml_examples (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	features JSON NOT NULL, 
	outcome INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_ml_examples_college_id ON pi3_ml_examples (college_id);

CREATE TABLE IF NOT EXISTS pi3_ml_models (
	college_id VARCHAR(36) NOT NULL, 
	artifact BYTEA NOT NULL, 
	metadata JSON NOT NULL, 
	trained_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (college_id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE TABLE IF NOT EXISTS pi3_roster (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	student_id VARCHAR(100) NOT NULL, 
	full_name VARCHAR(150) NOT NULL, 
	email VARCHAR(250), 
	department VARCHAR(100) NOT NULL, 
	semester INTEGER NOT NULL, 
	section VARCHAR(50) NOT NULL, 
	active BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_roster_per_college UNIQUE (college_id, student_id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_roster_college_id ON pi3_roster (college_id);

CREATE TABLE IF NOT EXISTS pi3_actions (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	owner VARCHAR(150) NOT NULL, 
	action VARCHAR(2000) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	due_date DATE NOT NULL, 
	note VARCHAR(2000) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_by VARCHAR(36) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id), 
	FOREIGN KEY(updated_by) REFERENCES pi3_accounts (id)
);

CREATE TABLE IF NOT EXISTS pi3_announcements (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	author_id VARCHAR(36) NOT NULL, 
	title VARCHAR(250) NOT NULL, 
	body TEXT NOT NULL, 
	audience VARCHAR(20) NOT NULL, 
	department VARCHAR(100), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(author_id) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_announcements_college_id ON pi3_announcements (college_id);

CREATE TABLE IF NOT EXISTS pi3_assignments (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	faculty_id VARCHAR(36) NOT NULL, 
	department VARCHAR(100) NOT NULL, 
	semester INTEGER NOT NULL, 
	section VARCHAR(50) NOT NULL, 
	subject VARCHAR(150) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_assign_unique UNIQUE (college_id, faculty_id, department, semester, section, subject), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(faculty_id) REFERENCES pi3_accounts (id)
);

CREATE TABLE IF NOT EXISTS pi3_faculty_presence (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	faculty_id VARCHAR(36) NOT NULL, 
	on_date DATE NOT NULL, 
	present BOOLEAN NOT NULL, 
	recorded_by VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_faculty_presence_unique UNIQUE (faculty_id, on_date), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(faculty_id) REFERENCES pi3_accounts (id), 
	FOREIGN KEY(recorded_by) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_faculty_presence_college_id ON pi3_faculty_presence (college_id);

CREATE TABLE IF NOT EXISTS pi3_observations (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(30) NOT NULL, 
	period_end DATE NOT NULL, 
	payload JSON NOT NULL, 
	source_name VARCHAR(150) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_observation_unique UNIQUE (roster_id, kind, period_end), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_observations_college_id ON pi3_observations (college_id);

CREATE TABLE IF NOT EXISTS pi3_requests (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	subject VARCHAR(200) NOT NULL, 
	detail TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	reply TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_requests_college_id ON pi3_requests (college_id);

CREATE TABLE IF NOT EXISTS pi3_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	csrf_token VARCHAR(80) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (token_hash), 
	FOREIGN KEY(user_id) REFERENCES pi3_accounts (id)
);

CREATE TABLE IF NOT EXISTS pi3_student_achievements (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	title VARCHAR(250) NOT NULL, 
	description VARCHAR(1000) NOT NULL, 
	file_name VARCHAR(255), 
	mime_type VARCHAR(80), 
	document BYTEA, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_student_achievements_college_id ON pi3_student_achievements (college_id);

CREATE TABLE IF NOT EXISTS pi3_student_contacts (
	roster_id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	phone VARCHAR(30) NOT NULL, 
	interests JSON NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (roster_id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_student_contacts_college_id ON pi3_student_contacts (college_id);

CREATE TABLE IF NOT EXISTS pi3_class_sessions (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	assignment_id VARCHAR(36) NOT NULL, 
	on_date DATE NOT NULL, 
	time_slot VARCHAR(70) NOT NULL, 
	topic VARCHAR(250) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_class_session_unique UNIQUE (assignment_id, on_date, time_slot), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(assignment_id) REFERENCES pi3_assignments (id), 
	FOREIGN KEY(created_by) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_class_sessions_college_id ON pi3_class_sessions (college_id);

CREATE TABLE IF NOT EXISTS pi3_entries (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	assignment_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	period_end DATE NOT NULL, 
	attended INTEGER, 
	held INTEGER, 
	marks_pct FLOAT, 
	status VARCHAR(20) NOT NULL, 
	updated_by VARCHAR(36) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_entries_unique UNIQUE (roster_id, assignment_id, kind, period_end), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id), 
	FOREIGN KEY(assignment_id) REFERENCES pi3_assignments (id), 
	FOREIGN KEY(updated_by) REFERENCES pi3_accounts (id)
);

CREATE TABLE IF NOT EXISTS pi3_exam_results (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	assignment_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	exam_name VARCHAR(100) NOT NULL, 
	exam_date DATE NOT NULL, 
	marks FLOAT NOT NULL, 
	maximum FLOAT NOT NULL, 
	entered_by VARCHAR(36) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_exam_results_unique UNIQUE (assignment_id, roster_id, exam_name, exam_date), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(assignment_id) REFERENCES pi3_assignments (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id), 
	FOREIGN KEY(entered_by) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_exam_results_college_id ON pi3_exam_results (college_id);

CREATE TABLE IF NOT EXISTS pi3_learning_resources (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	assignment_id VARCHAR(36) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	url VARCHAR(2000) NOT NULL, 
	description TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(assignment_id) REFERENCES pi3_assignments (id), 
	FOREIGN KEY(created_by) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_learning_resources_college_id ON pi3_learning_resources (college_id);

CREATE TABLE IF NOT EXISTS pi3_learning_tasks (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	assignment_id VARCHAR(36) NOT NULL, 
	created_by VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	title VARCHAR(200) NOT NULL, 
	description TEXT NOT NULL, 
	due_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	max_points INTEGER NOT NULL, 
	questions JSON NOT NULL, 
	published BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(assignment_id) REFERENCES pi3_assignments (id), 
	FOREIGN KEY(created_by) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_learning_tasks_college_id ON pi3_learning_tasks (college_id);

CREATE TABLE IF NOT EXISTS pi3_timetable (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	assignment_id VARCHAR(36) NOT NULL, 
	weekday INTEGER NOT NULL, 
	start_time VARCHAR(5) NOT NULL, 
	end_time VARCHAR(5) NOT NULL, 
	room VARCHAR(60) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(assignment_id) REFERENCES pi3_assignments (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_timetable_college_id ON pi3_timetable (college_id);

CREATE TABLE IF NOT EXISTS pi3_class_attendance (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	present BOOLEAN NOT NULL, 
	updated_by VARCHAR(36) NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_class_attendance_unique UNIQUE (session_id, roster_id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(session_id) REFERENCES pi3_class_sessions (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id), 
	FOREIGN KEY(updated_by) REFERENCES pi3_accounts (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_class_attendance_college_id ON pi3_class_attendance (college_id);

CREATE TABLE IF NOT EXISTS pi3_learning_submissions (
	id VARCHAR(36) NOT NULL, 
	college_id VARCHAR(36) NOT NULL, 
	task_id VARCHAR(36) NOT NULL, 
	roster_id VARCHAR(36) NOT NULL, 
	answers JSON NOT NULL, 
	score FLOAT, 
	feedback TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	submitted_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT pi3_task_submission_unique UNIQUE (task_id, roster_id), 
	FOREIGN KEY(college_id) REFERENCES pi3_colleges (id), 
	FOREIGN KEY(task_id) REFERENCES pi3_learning_tasks (id), 
	FOREIGN KEY(roster_id) REFERENCES pi3_roster (id)
);

CREATE INDEX IF NOT EXISTS ix_pi3_learning_submissions_college_id ON pi3_learning_submissions (college_id);

ALTER TABLE public.pi3_attempts ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_colleges ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_accounts ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_audit ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_college_preferences ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_connections ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_ml_examples ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_ml_models ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_roster ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_actions ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_announcements ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_assignments ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_faculty_presence ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_observations ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_requests ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_student_achievements ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_student_contacts ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_class_sessions ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_entries ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_exam_results ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_learning_resources ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_learning_tasks ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_timetable ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_class_attendance ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.pi3_learning_submissions ENABLE ROW LEVEL SECURITY;

COMMIT;

-- Private backend uses the PostgreSQL owner connection; do not put DATABASE_URL in the React client.
