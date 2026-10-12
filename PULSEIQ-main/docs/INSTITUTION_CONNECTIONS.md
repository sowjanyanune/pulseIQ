# Field mapping for existing college databases

## 1. SQL example (any supported SQL dialect)

College source data may have tables like `student_master`, `marks_table`, and `attendance_details` with institution-specific columns. The admin maps them using JSON:

```json
{
  "students": {
    "table": "student_master",
    "columns": {
      "student_id": "register_number",
      "department": "department_name",
      "semester": "current_semester"
    }
  },
  "academic": {
    "table": "marks_table",
    "columns": {
      "student_id": "register_number",
      "period_end": "result_date",
      "marks_pct": "aggregate_percentage",
      "backlog_count": "backlogs"
    }
  },
  "attendance": {
    "table": "attendance_details",
    "columns": {
      "student_id": "register_number",
      "period_end": "attendance_date",
      "classes_attended": "attended",
      "classes_held": "held"
    }
  }
}
```

Optional canonical entities are `lms`, `placement`, `skills`, `engagement`, and `feedback`. Their required canonical fields are defined by `backend/db.py` (`SCHEMAS`) and may be mapped to the columns in your existing source.

**Important:** The `students` source is required and must yield a nonempty roster. If the college's attendance or marks database stores **multiple rows for one student in one reporting period** (e.g. one row per subject), ask the college IT team for a normalized **read-only view** that aggregates those rows by `(student_id, period_end)` before mapping. PULSEIQ rejects duplicate keys, so it never arbitrarily picks one.

## 2. Student names, section and email

For a student roster imported through **canonical API** or JSON bulk, `full_name`, `email`, `section` are accepted. For generic SQL and MongoDB mapping, the original v2 mapper fetches the canonical three roster fields (student ID, department, semester); unmapped `full_name`, `email`, `section` will default to student ID / no email / section A. Update these manually afterward or build an institution-specific normalized canonical HTTPS endpoint. Admin-created student accounts require **exact registered student IDs**.

## 3. Safer integration workflow

- Institute approves a **read-only** database service account or scoped HTTPS token.
- Admin configures URI/credentials using the browser over HTTPS. They are encrypted server-side and not readable through GET endpoints.
- Click **Inspect tables** to see available names/columns, without exposing passwords.
- Map the college's original columns to canonical fields; click **Preview mapped data**.
- Resolve validation errors. Click **Sync data** when the preview is correct.
- Each sync is isolated to `college_id`. Published marks/attendance recorded by faculty remain in separate tables.
- Faculty updates do **not** write back to the institute's original database automatically.

## 4. Drivers and network limits

- PostgreSQL (`psycopg`), MySQL/MariaDB (`PyMySQL`) and MongoDB (`pymongo`) are installed.
- Optional Oracle (`oracledb`) and SQL Server (`pymssql`) installed from `requirements-connectors.txt` in the Docker build; availability depends on compatible source schemas and network settings. For Windows-integrated/ODBC SQL Server, custom drivers are required.
- Generic HTTPS API payload must be canonical object-of-arrays, use public HTTPS, and may require a bearer token.
- Source scans are capped by legacy validators at 20,000 rows per entity; bigger colleges must expose scoped source views or implement a pagination/ETL extension.
- PULSEIQ does not automatically discover credentials or connect unapproved on-premises college networks.
