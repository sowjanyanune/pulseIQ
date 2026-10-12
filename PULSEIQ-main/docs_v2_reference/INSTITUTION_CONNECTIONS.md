# Connect an institute without student data files

An institute can retain its existing ERP, SIS and database. PULSEIQ needs approved read access and a canonical mapping. Support for a database driver does not imply automatic understanding of every vendor's schema.

## Engine choices

| Source | SQLAlchemy/connector choice | Packaged status |
|---|---|---|
| PostgreSQL, Neon, compatible managed PostgreSQL | `postgresql+psycopg://` | Driver included |
| MongoDB / MongoDB Atlas | `mongodb://` or `mongodb+srv://` using PyMongo | Driver included |
| HTTPS ERP/SIS API | Canonical JSON endpoint; optional bearer token | HTTP client included |
| MySQL | `mysql+pymysql://` | Install optional SQL drivers in Docker |
| MariaDB | `mysql+pymysql://` with compatible server | Install optional SQL drivers in Docker |
| Oracle Database | `oracle+oracledb://` (thin mode where supported) | Install optional SQL drivers in Docker; some servers require a client/wallet |
| Microsoft SQL Server | `mssql+pyodbc://` | Optional Python driver **and** compatible system ODBC driver required |
| Campus-only SQLite/Access files | Not a cloud source workflow | Ask IT for a supported database/API connection |

Default deployment includes PostgreSQL, MongoDB and API dependencies. To enable MySQL or Oracle, change the Docker install line to `pip install --no-cache-dir -r requirements.txt -r requirements-connectors.txt`, then push the change. That file includes `PyMySQL`, `oracledb` and `pyodbc`. For SQL Server, the system Microsoft ODBC driver must also be installed in the Docker image per [Microsoft's Linux driver guide](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server). Installing `pyodbc` alone is insufficient.

Only the SQL mapping on a SQLite test fixture and the canonical API on a mock HTTPS transport were exercised in the initial package verification, unless the test report says otherwise. Connections to your institute's server and other engine-specific TLS/authentication configurations need their actual credentials/network to be verified.

Driver references: [SQLAlchemy dialects](https://docs.sqlalchemy.org/en/20/dialects/index.html), [MySQL/PyMySQL](https://docs.sqlalchemy.org/en/20/dialects/mysql.html), [SQL Server/pyodbc](https://docs.sqlalchemy.org/en/20/dialects/mssql.html), [Oracle/oracledb](https://docs.sqlalchemy.org/en/20/dialects/oracle.html), [PyMongo](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/).

## Canonical entities

| Entity | Fields after mapping |
|---|---|
| students | `student_id`, `department`, `semester` |
| academic | `student_id`, `period_end`, `marks_pct`, `backlog_count` |
| attendance | `student_id`, `period_end`, `classes_attended`, `classes_held` |
| lms | `student_id`, `period_end`, `assignments_completed`, `assignments_assigned` |
| placement | `student_id`, `period_end`, `aptitude_pct`, `coding_pct`, `interview_pct` |
| skills | `student_id`, `period_end`, `technical_pct`, `communication_pct` |
| engagement | `student_id`, `period_end`, `activities_completed`, `activities_available` |
| feedback | `student_id`, `period_end`, `support_requested`, `support_category` |

Use a stable string student ID consistently across sources; leading zeroes are preserved. Reporting dates are `YYYY-MM-DD`. Percentages are 0–100; counts are nonnegative integers; semester is 1–12. Missing observations use null, not zero. Feedback categories are Academic, Placement, Attendance, LMS, Other, None. A true support request needs a category.

The roster is required. Other entities may be absent when the institute has no approved source. A present record must expose its canonical fields, using null for missing observations. Duplicate roster IDs or duplicate `(student_id, period_end)` rows block the refresh. Unmatched IDs are excluded with a warning. A count exceeding its denominator blocks refresh; zero denominators yield missing evidence. Limits apply to each source array: 20,000 rows per refresh.

## SQL settings

In Render Environment:

```text
SOURCE_KIND=sql
SOURCE_NAME=Institute approved views
SOURCE_DATABASE_URL=<private SQLAlchemy connection URL>
SOURCE_MAPPING=connectors/mapping.json
SEED_DEMO=false
```

Examples are placeholders, not working credentials:

```text
postgresql://READONLY:ENCODED_PASSWORD@HOST:5432/DB?sslmode=require
mysql+pymysql://READONLY:ENCODED_PASSWORD@HOST:3306/DB
oracle+oracledb://READONLY:ENCODED_PASSWORD@HOST:1521/?service_name=SERVICE
mssql+pyodbc://READONLY:ENCODED_PASSWORD@HOST:1433/DB?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes
```

Use the provider's required TLS options/certificates. Password characters inside a URL need URL encoding. Use a source database account whose database permissions allow SELECT only on approved views. This connector selects/refects configured tables; it does not create or write source tables. Source SQL strings are not entered in the browser.

Edit the tracked `connectors/mapping.json`. The structure for two entities is:

```json
{
  "students": {
    "table": "pulseiq_student_view",
    "schema": "public",
    "columns": {"student_id": "roll_number", "department": "dept_name", "semester": "current_semester"}
  },
  "academic": {
    "table": "pulseiq_academic_view",
    "schema": "public",
    "columns": {"student_id": "roll_number", "period_end": "report_date", "marks_pct": "marks_percentage", "backlog_count": "arrears"}
  }
}
```

Remove entities the institute does not provide, retaining `students`. Add the available reporting entities using the canonical fields above. Map a field to `null` if that entity is available but that observation is missing. `schema` is optional; use the source engine's supported schema/database convention. The default included file maps all fields to the same names and needs editing for a differently named ERP.

Use normalized views for aggregated results or narrowed historical periods. Do not give a write-capable ERP owner account to PULSEIQ. PULSEIQ's own `DATABASE_URL` is read/write; `SOURCE_DATABASE_URL` is a separate read-only source.

## MongoDB settings

```text
SOURCE_KIND=mongodb
SOURCE_NAME=Institute MongoDB
SOURCE_MONGODB_URI=<private URI for read-only user>
SOURCE_MONGODB_DATABASE=<database name>
SOURCE_MAPPING=connectors/mapping.json
SEED_DEMO=false
```

`table` in the mapping is a collection name. Column mappings can use dotted document paths, such as `student.roll_number` or `assessments.coding_pct`. Each mapped collection still needs one document per student/reporting period. Use an approved materialized collection/view if raw documents contain arrays/events. Configure Atlas/network access to permit only the approved backend connection and use least-privilege credentials.

## HTTPS API settings

```text
SOURCE_KIND=api
SOURCE_NAME=Institute canonical API
SOURCE_API_URL=https://YOUR_APPROVED_HOST/pulseiq/snapshot
SOURCE_API_TOKEN=<token supplied by institute, if required>
SEED_DEMO=false
```

The GET endpoint must return a JSON object containing entity arrays such as:

```json
{
  "students": [{"student_id": "001007", "department": "Computer Science", "semester": 6}],
  "academic": [{"student_id": "001007", "period_end": "2026-10-03", "marks_pct": 81, "backlog_count": 0}]
}
```

Omitted reporting arrays are treated as unavailable evidence. The backend sends `Authorization: Bearer ...` when a token is configured. The endpoint uses HTTPS, does not redirect, and returns one bounded snapshot, up to 10 MiB. Pagination/OAuth renewal/vendor-specific payload normalization must be implemented in an adapter before using a vendor endpoint that does not meet this contract.

## Network access

A database available only inside the institute cannot be reached by entering a private host into a public cloud service. IT must provide an approved network route/gateway, a reachable API or host the Docker backend where it can reach the source. The same application architecture can use institute-controlled hosting and PostgreSQL if their policy requires it; do not expose the ERP publicly just to make a connection.

After deployment with the approved settings, admin selects **Refresh from institution**. If validation fails, the error includes the report and previous records stay available. If fetching/network/authentication fails, verify settings without copying passwords into GitHub issues or public screenshots. Persistent actions/history are separate from source refreshes.
