"""Validate canonical records fetched from databases, without file uploads."""

from datetime import date
import math
import pandas as pd
from .db import SCHEMAS

COUNTS = {
    "semester",
    "backlog_count",
    "classes_attended",
    "classes_held",
    "assignments_completed",
    "assignments_assigned",
    "activities_completed",
    "activities_available",
}
PAIRS = {
    "attendance": ("classes_attended", "classes_held"),
    "lms": ("assignments_completed", "assignments_assigned"),
    "engagement": ("activities_completed", "activities_available"),
}


class InvalidSnapshot(ValueError):
    def __init__(self, report):
        super().__init__("Source validation failed; previous snapshot preserved.")
        self.report = report


def validate_records(records):
    normalized, report = {}, []

    def issue(source, row, severity, message):
        report.append(dict(source=source, row=row, severity=severity, message=message))

    if not isinstance(records, dict):
        raise InvalidSnapshot(
            [
                dict(
                    source="snapshot",
                    row=0,
                    severity="error",
                    message="Snapshot must contain named entity arrays.",
                )
            ]
        )
    for source, fields in SCHEMAS.items():
        incoming = records.get(source, [])
        if not isinstance(incoming, list):
            issue(source, 0, "error", "Entity must be an array of records.")
            incoming = []
        if len(incoming) > 20000:
            issue(
                source,
                0,
                "error",
                "Source exceeds 20,000 rows. Narrow the configured source views.",
            )
            incoming = []
        rows = []
        for i, input_row in enumerate(incoming, 1):
            if not isinstance(input_row, dict):
                issue(source, i, "error", "Each record must be an object.")
                continue
            missing = set(fields) - set(input_row)
            if missing:
                issue(
                    source,
                    i,
                    "error",
                    "Missing canonical fields: " + ", ".join(sorted(missing)),
                )
                continue
            row = {f: input_row[f] for f in fields}
            for f, v in row.items():
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    row[f] = None
            sid = row["student_id"]
            if sid is None or not str(sid).strip():
                issue(source, i, "error", "student_id is required.")
                continue
            row["student_id"] = str(sid).strip()
            if len(row["student_id"]) > 100:
                issue(source, i, "error", "student_id exceeds 100 characters.")
            if source == "students":
                row["department"] = (
                    "" if row["department"] is None else str(row["department"]).strip()
                )
                if not row["department"] or len(row["department"]) > 100:
                    issue(
                        source,
                        i,
                        "error",
                        "Provide a department of up to 100 characters.",
                    )
            else:
                try:
                    row["period_end"] = date.fromisoformat(
                        str(row["period_end"])[:10]
                    ).isoformat()
                except (ValueError, TypeError):
                    issue(source, i, "error", "period_end must be YYYY-MM-DD.")
                    continue
            for field in fields:
                if field not in COUNTS and not field.endswith("_pct"):
                    continue
                value = row[field]
                if value is None or value == "":
                    row[field] = None
                    issue(
                        source,
                        i,
                        "error" if field == "semester" else "warning",
                        field + " is missing.",
                    )
                    continue
                try:
                    number = float(value)
                    if not math.isfinite(number) or number < 0:
                        raise ValueError()
                    if field.endswith("_pct") and number > 100:
                        raise ValueError()
                    if field in COUNTS and (
                        not number.is_integer() or number > 2147483647
                    ):
                        raise ValueError()
                    if field == "semester" and not 1 <= number <= 12:
                        raise ValueError()
                    row[field] = int(number) if field in COUNTS else number
                except (ValueError, TypeError):
                    issue(
                        source, i, "error", field + " has an invalid range or number."
                    )
            if source in PAIRS:
                n, d = PAIRS[source]
                if row[n] is not None and row[d] is not None:
                    try:
                        if row[n] > row[d]:
                            issue(source, i, "error", n + " exceeds " + d + ".")
                        if row[d] == 0:
                            issue(
                                source, i, "warning", d + " is zero: missing evidence."
                            )
                    except TypeError:
                        pass  # numeric error already reported
            if source == "feedback":
                val = row["support_requested"]
                if val is not None:
                    if str(val).lower() not in ("true", "false", "1", "0"):
                        issue(source, i, "error", "Invalid support_requested boolean.")
                    else:
                        row["support_requested"] = str(val).lower() in ("true", "1")
                if row["support_category"] not in (
                    "Academic",
                    "Placement",
                    "Attendance",
                    "LMS",
                    "Other",
                    "None",
                    None,
                    "",
                ):
                    issue(source, i, "error", "Invalid support_category.")
                if row["support_requested"] is True and row["support_category"] in (
                    "None",
                    None,
                    "",
                ):
                    issue(source, i, "error", "A support request needs a category.")
            rows.append(row)
        keys = ["student_id"] if source == "students" else ["student_id", "period_end"]
        seen = set()
        for i, row in enumerate(rows, 1):
            key = tuple(row[k] for k in keys)
            if key in seen:
                issue(
                    source,
                    i,
                    "error",
                    "Duplicate student/reporting-period key; no arbitrary selection.",
                )
            seen.add(key)
        normalized[source] = rows
    if not normalized["students"]:
        issue("students", 0, "error", "A nonempty roster is required.")
    ids = {r["student_id"] for r in normalized["students"]}
    for source in list(SCHEMAS)[1:]:
        matched = []
        for i, row in enumerate(normalized[source], 1):
            if row["student_id"] not in ids:
                issue(source, i, "warning", "Unmatched student_id excluded.")
            else:
                matched.append(row)
        normalized[source] = matched
    if any(r["severity"] == "error" for r in report):
        raise InvalidSnapshot(report)
    return normalized, report


def joined_records(records, period, analysis_date, stale_days=30):
    roster = pd.DataFrame(records["students"], columns=SCHEMAS["students"])
    joined = roster.copy()
    joined["period_end"] = period
    age = (analysis_date - date.fromisoformat(period)).days
    for source, fields in list(SCHEMAS.items())[1:]:
        rows = [
            r for r in records.get(source, []) if str(r["period_end"])[:10] == period
        ]
        table = pd.DataFrame(rows, columns=fields + ["source_name", "imported_at"])
        table = table.rename(
            columns={
                "period_end": source + "__period_end",
                "source_name": source + "__source_name",
                "imported_at": source + "__imported_at",
            }
        )
        table[source + "__present"] = True
        joined = joined.merge(table, on="student_id", how="left", validate="one_to_one")
        joined[source + "__present"] = joined[source + "__present"].eq(True)
        joined[source + "__fresh"] = joined[source + "__present"] & (
            0 <= age <= stale_days
        )
    joined["analysis_date"] = analysis_date.isoformat()
    joined["data_age_days"] = age
    return joined
