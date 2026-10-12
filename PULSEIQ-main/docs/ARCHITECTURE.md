# Architecture v3

```text
College Admin / Faculty / Student (React, one origin)
           |
     HTTPS /api  + CSRF session cookies
           |
        FastAPI v3
           |
   Tenant identity: college_id + role + class assignments
           |
   Neon PostgreSQL (pi3_colleges, pi3_accounts, pi3_roster,
    pi3_assignments, pi3_entries, pi3_observations, pi3_actions,
    pi3_connections, pi3_audit)
           |
       Connector adapters (admin initiated)
        /       |       \
      SQL     MongoDB  HTTPS institutional API
           |
 Canonical validation → only one college's imported records
           |
 Original explainable rules_v1 student scoring engine
```

All tenant-specific API queries verify the signed-in college ID. Faculty roster visibility requires a teaching assignment matching department, semester, and section. Student access requires a linked student ID. Draft academic entries never affect student scores or appear in student detail; published entries aggregate at subject level and override imported academic/attendance values for that student/period, without altering source files.

Note: Multi-college test coverage is present, but defense in depth at the database layer (Postgres row-level policies, external penetration testing, backups, immutable event log) requires extra work for real production use. Old PULSEIQ v2 tables are not used by v3 APIs, except for an explicitly enabled one-time migration.
