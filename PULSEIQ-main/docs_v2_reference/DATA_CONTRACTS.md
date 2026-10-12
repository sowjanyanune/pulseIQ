# Data contracts

A college data team supplies the CSV files. No complete education history from Class 12 onward is required. The public demo uses fictional IDs and no names, phone numbers, email addresses or sensitive demographic fields.

| File | Required columns | Interpretation |
| --- | --- | --- |
| students.csv | student_id, department, semester | One unique roster row per student; semester integer 1–12 |
| academic.csv | student_id, period_end, marks_pct, backlog_count | Marks 0–100; nonnegative integral backlogs |
| attendance.csv | student_id, period_end, classes_attended, classes_held | Nonnegative integral counts, attended ≤ held |
| lms.csv | student_id, period_end, assignments_completed, assignments_assigned | Nonnegative integral counts, completed ≤ assigned |
| placement.csv | student_id, period_end, aptitude_pct, coding_pct, interview_pct | All percentages 0–100; all three needed for P |
| skills.csv | student_id, period_end, technical_pct, communication_pct | Both percentages needed for S |
| engagement.csv | student_id, period_end, activities_completed, activities_available | Nonnegative integral counts, completed ≤ available |
| feedback.csv | student_id, period_end, support_requested, support_category | Boolean request and bounded category; no free text |

`students.csv` is mandatory; absent sources remain unknown. Each evidence source is unique on `(student_id, period_end)` and dates use YYYY-MM-DD. IDs are text, including leading zeroes. Measurements can be blank: missing is never filled with zero or cohort averages. A missing semester or department is a blocking roster error.

Feedback booleans accept true/false or 1/0, case-insensitively. Allowed categories: Academic, Placement, Attendance, LMS, Other, None. A true request needs a category other than blank/None. Requests are a separate review queue.

Files are limited to 5 MiB and 1,000 data rows per source. Any invalid row or missing required column blocks activation of the whole batch. The quality report still shows accepted/rejected row counts. Unmatched IDs are reported warnings and excluded; fix the roster or source and reimport. All duplicate-key rows are rejected; there is no arbitrary first/last selection. Extra columns are ignored with a warning.

The selected period is an exact join: if placement has August but not September, September placement is missing. Reporting records with age above the selected freshness window or with future dates are visible but excluded. Missing assessments within a fresh source still reduce component coverage.

## Demo fixture expectations

| ID | Fixture | Expected result for September at 10 October 2026 |
| --- | --- | --- |
| DEMO001 | A80, T90, L70, P40, S60, E50 | Score 68.0; strong academics with placement gap |
| DEMO002 | Low marks, attendance and one backlog; good placement | Academic support |
| DEMO003 | Low marks/attendance and placement gap | Dual support, plus overlapping support segments |
| DEMO004 | Strong marks and placement, no backlog | Currently on track |
| DEMO005 | Missing all placement assessments | Coverage 75%; insufficient score; placement Undetermined |
| DEMO006 | Zero engagement denominator | Coverage 95%; provisional score approximately 68.9474, displayed 68.95 |
| DEMO007 | Explicit Other support request | Request visible; score unchanged by request |

The same deliberate fixture values exist in both periods. Other fictional rows provide variation, including missing skills and zero LMS denominators. They are demonstrations of behavior, not an empirical student population.
