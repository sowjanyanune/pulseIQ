from datetime import date, datetime
import json, math, uuid
import numpy as np
from sqlalchemy import select, insert, update, delete, func, text
from .db import TABLES, SCHEMAS, students, state, sync_log, now
from .validation import validate_records, joined_records
from .scoring import score_dataset


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def set_state(conn, key, value):
    if conn.execute(select(state.c.key).where(state.c.key == key)).first():
        conn.execute(update(state).where(state.c.key == key).values(value=clean(value)))
    else:
        conn.execute(insert(state).values(key=key, value=clean(value)))


def replace_snapshot(engine, records, source_name, actor="system", demo=False):
    normalized, report = validate_records(records)
    stamp = now()
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(763928451)"))
        # Preserve roster identities referenced by durable intervention history.
        conn.execute(update(students).values(active=False))
        existing = {r[0] for r in conn.execute(select(students.c.student_id))}
        for row in normalized["students"]:
            data = dict(row, active=True)
            if row["student_id"] in existing:
                conn.execute(
                    update(students)
                    .where(students.c.student_id == row["student_id"])
                    .values(**data)
                )
            else:
                conn.execute(insert(students).values(**data))
        for source in list(SCHEMAS)[1:]:
            table = TABLES[source]
            conn.execute(delete(table))
            values = []
            for row in normalized[source]:
                item = dict(row)
                item["period_end"] = date.fromisoformat(item["period_end"])
                item.update(source_name=source_name + " / " + source, imported_at=stamp)
                values.append(item)
            if values:
                conn.execute(insert(table), values)
        summary = {
            "source": source_name,
            "students": len(normalized["students"]),
            "periods": sorted(
                {
                    r["period_end"]
                    for k, v in normalized.items()
                    if k != "students"
                    for r in v
                }
            ),
            "demo": demo,
            "updated_at": stamp,
            "quality_report": report,
            "source_counts": {k: len(v) for k, v in normalized.items()},
        }
        set_state(conn, "dataset", summary)
        conn.execute(
            insert(sync_log).values(
                id=str(uuid.uuid4()),
                at=stamp,
                actor=actor,
                status="Success",
                source=source_name,
                summary=clean(
                    {"students": len(normalized["students"]), "warnings": len(report)}
                ),
            )
        )
    return clean(summary)


def records_from_database(engine):
    with engine.connect() as conn:
        if conn.dialect.name == "postgresql":
            # Keep all entity reads on one snapshot if a refresh commits midway.
            conn.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            )
        elif conn.dialect.name == "sqlite":
            conn.execute(text("BEGIN"))
        roster = [
            dict(r)
            for r in conn.execute(
                select(students).where(students.c.active == True)
            ).mappings()
        ]
        ids = {r["student_id"] for r in roster}
        records = {"students": [{k: r[k] for k in SCHEMAS["students"]} for r in roster]}
        for source in list(SCHEMAS)[1:]:
            records[source] = [
                clean(dict(r))
                for r in conn.execute(select(TABLES[source])).mappings()
                if r["student_id"] in ids
            ]
        result = conn.execute(
            select(state.c.value).where(state.c.key == "dataset")
        ).scalar_one_or_none()
    return records, result or {
        "students": 0,
        "periods": [],
        "source": "No student records yet",
        "demo": False,
        "quality_report": [],
    }


def scored_records(
    engine,
    period,
    analysis_date,
    stale_days,
    user,
    department=None,
    semester=None,
    segment=None,
):
    records, meta = records_from_database(engine)
    if not records["students"]:
        return [], meta
    if meta["periods"]:
        if period is None:
            period = meta["periods"][-1]
        if period not in meta["periods"]:
            raise ValueError("Select an available reporting period.")
    else:
        # A roster-only institute snapshot still has profiles and actions.
        # The reference date creates no observations or fresh source evidence.
        period = analysis_date.isoformat()
    rows = score_dataset(
        joined_records(records, period, analysis_date, stale_days)
    ).to_dict("records")
    scoped = []
    for r in rows:
        if user["role"] != "admin" and r["department"] not in user["departments"]:
            continue
        if department and r["department"] != department:
            continue
        if semester and int(r["semester"]) != semester:
            continue
        if segment == "Support requested" and not r["support_request"]:
            continue
        if (
            segment
            and segment not in ("All", "Support requested")
            and segment not in r["segments"]
        ):
            continue
        scoped.append(clean(r))
    return sorted(scoped, key=lambda r: r["student_id"]), meta
