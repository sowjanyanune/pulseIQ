Run from project root in an environment with requirements installed:
  python tests_aurora/smoke_end_to_end.py

This test uses SQLite in-memory only (Settings.environment=test) and fictional credentials.
It exercises invite-only college registration, login, preferences, role accounts,
roster, faculty class assignment, MCQ quiz creation/completion/autograding,
resource sharing, student focus guidance, CSRF and cross-college isolation.
No Supabase credentials or external network are required.
