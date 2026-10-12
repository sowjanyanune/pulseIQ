from copy import deepcopy
from datetime import date, timedelta
import json
import pytest, httpx, pandas as pd
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    String,
    Integer,
    Float,
    insert,
    select,
)
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from backend.connectors import fetch_sql, fetch_api, nested, ConnectorError
from backend.validation import validate_records, joined_records, InvalidSnapshot
from backend.seed import generate
from backend.db import metadata, SCHEMAS
from backend.scoring import score_dataset, score_student, validate_config, CONFIG
from backend.settings import Settings, normalize_url


@pytest.fixture
def records():
    return generate(200, reference=date(2026, 10, 10))


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "percentage",
        "negative",
        "fraction",
        "denominator",
        "blank_department",
        "missing_field",
        "invalid_date",
        "request_without_category",
        "semester",
        "oversized_count",
        "non_object",
        "non_array",
    ],
)
def test_invalid_sources_block_entire_snapshot(records, case):
    if case == "duplicate":
        records["academic"].append(deepcopy(records["academic"][0]))
    elif case == "percentage":
        records["academic"][0]["marks_pct"] = 101
    elif case == "negative":
        records["academic"][0]["backlog_count"] = -1
    elif case == "fraction":
        records["academic"][0]["backlog_count"] = 0.5
    elif case == "denominator":
        records["attendance"][0]["classes_attended"] = 100
    elif case == "blank_department":
        records["students"][0]["department"] = "  "
    elif case == "missing_field":
        del records["skills"][0]["technical_pct"]
    elif case == "invalid_date":
        records["academic"][0]["period_end"] = "not-a-date"
    elif case == "request_without_category":
        records["feedback"][0].update(support_requested=True, support_category="None")
    elif case == "semester":
        records["students"][0]["semester"] = 0
    elif case == "oversized_count":
        records["lms"][0]["assignments_completed"] = 10**12
    elif case == "non_object":
        records["students"][0] = "not-an-object"
    elif case == "non_array":
        records["academic"] = {}
    with pytest.raises(InvalidSnapshot) as problem:
        validate_records(records)
    assert any(r["severity"] == "error" for r in problem.value.report)


def test_missing_optional_sources_zero_denominator_and_unmatched_ids(records):
    records["skills"] = []
    records["academic"].append(
        dict(
            student_id="UNKNOWN", period_end="2026-10-03", marks_pct=60, backlog_count=0
        )
    )
    normalized, report = validate_records(records)
    assert normalized["skills"] == []
    assert all(r["student_id"] != "UNKNOWN" for r in normalized["academic"])
    assert any("Unmatched" in r["message"] for r in report)
    assert any("zero" in r["message"] for r in report)
    scores = score_dataset(joined_records(normalized, "2026-10-03", date(2026, 10, 10)))
    assert len(scores) == 200
    assert scores.iloc[0]["score_status"] == "Provisional"
    assert scores.iloc[0]["S"] is None


def test_period_join_does_not_reuse_another_period(records):
    records["placement"] = [
        r for r in records["placement"] if r["period_end"] == "2026-09-03"
    ]
    normalized, _ = validate_records(records)
    row = score_dataset(
        joined_records(normalized, "2026-10-03", date(2026, 10, 10))
    ).iloc[0]
    assert row["P"] is None and row["overall_score"] is None
    assert row["placement_flag"] == "Undetermined"
    assert row["academic_flag"] == "No observed trigger"


def test_known_trigger_survives_missing_flag_evidence(records):
    for row in records["placement"]:
        if row["student_id"] == "DEMO0001":
            row["interview_pct"] = None
    normalized, _ = validate_records(records)
    row = score_dataset(
        joined_records(normalized, "2026-10-03", date(2026, 10, 10))
    ).iloc[0]
    assert pd.isna(row["P"]) and row["placement_flag"] == "Support needed"
    assert row["academic_flag"] == "No observed trigger"
    assert "Currently on track" not in row["segments"]
    assert any("coding_pct" in r for r in row["placement_reasons"])


def test_threshold_boundaries_and_invalid_weight_config(records):
    normalized, _ = validate_records(records)
    row = joined_records(normalized, "2026-10-03", date(2026, 10, 10)).iloc[0].to_dict()
    row.update(
        marks_pct=50,
        classes_attended=30,
        classes_held=40,
        backlog_count=0,
        aptitude_pct=70,
        coding_pct=50,
        interview_pct=60,
    )
    result = score_student(row)
    assert result["P"] == 60
    assert result["academic_flag"] == result["placement_flag"] == "No observed trigger"
    invalid = deepcopy(CONFIG)
    invalid["weights"]["A"] = 0.5
    with pytest.raises(ValueError, match="sum to 1"):
        validate_config(invalid)


def test_sql_connector_maps_names_preserves_ids_and_leaves_source_unchanged(tmp_path):
    url = "sqlite:///" + str(tmp_path / "institution.sqlite")
    engine = create_engine(url)
    meta = MetaData()
    roster = Table(
        "ERP student roster",
        meta,
        Column("roll", String, primary_key=True),
        Column("dept", String),
        Column("term", Integer),
    )
    marks = Table(
        "ERP marks",
        meta,
        Column("roll", String),
        Column("report_date", String),
        Column("grade", Float),
        Column("arrears", Integer),
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(roster), [dict(roll="001007", dept="Computer Science", term=6)]
        )
        conn.execute(
            insert(marks),
            [dict(roll="001007", report_date="2026-10-03", grade=91, arrears=0)],
        )
    mapping = {
        "students": {
            "table": roster.name,
            "columns": {"student_id": "roll", "department": "dept", "semester": "term"},
        },
        "academic": {
            "table": marks.name,
            "columns": {
                "student_id": "roll",
                "period_end": "report_date",
                "marks_pct": "grade",
                "backlog_count": "arrears",
            },
        },
    }
    fetched = fetch_sql(
        url, mapping, "postgresql://example:unused@invalid.example/pulseiq"
    )
    normalized, _ = validate_records(fetched)
    assert normalized["students"][0]["student_id"] == "001007"
    assert normalized["academic"][0]["marks_pct"] == 91
    with engine.connect() as conn:
        assert conn.execute(select(marks.c.grade)).scalar_one() == 91
    mapping["academic"]["columns"]["backlog_count"] = None
    assert (
        fetch_sql(url, mapping, "postgresql://example:unused@invalid.example/pulseiq")[
            "academic"
        ][0]["backlog_count"]
        is None
    )
    mapping["academic"]["columns"]["marks_pct"] = "missing_column"
    with pytest.raises(ConnectorError):
        fetch_sql(url, mapping, "postgresql://example:unused@invalid.example/pulseiq")
    with pytest.raises(ConnectorError, match="separate"):
        fetch_sql(url, {}, url)
    engine.dispose()


def test_api_connector_https_auth_and_contract(records):
    observed = {}

    def handler(request):
        observed["url"] = str(request.url)
        observed["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=records)

    fetched = fetch_api(
        "https://institution.example/pulseiq-snapshot",
        "test-only-token",
        httpx.MockTransport(handler),
    )
    assert len(validate_records(fetched)[0]["students"]) == 200
    assert observed["auth"] == "Bearer test-only-token"
    with pytest.raises(ConnectorError, match="HTTPS"):
        fetch_api("http://institution.example", "")
    with pytest.raises(ConnectorError, match="entity arrays"):
        fetch_api(
            "https://institution.example",
            "",
            httpx.MockTransport(lambda _: httpx.Response(200, json=[])),
        )
    with pytest.raises(httpx.HTTPStatusError):
        fetch_api(
            "https://institution.example",
            "",
            httpx.MockTransport(lambda _: httpx.Response(401)),
        )


def test_mongodb_nested_fields_and_mapping_contract():
    record = {
        "student": {"id": "00091", "department": "Business"},
        "scores": {"academic": 83},
    }
    assert nested(record, "student.id") == "00091"
    assert nested(record, "scores.academic") == 83
    assert nested(record, "scores.coding") is None
    config = json.loads(open("connectors/mapping.json").read())
    assert set(config) == set(SCHEMAS)
    assert all(
        set(config[s]["columns"]) == set(fields) for s, fields in SCHEMAS.items()
    )


def test_postgresql_schema_compiles_and_settings_fail_closed():
    ddl = "\n".join(
        str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for table in metadata.sorted_tables
    )
    assert "FOREIGN KEY" in ddl and "TIMESTAMP WITH TIME ZONE" in ddl
    assert normalize_url(
        "postgresql://user:placeholder@host/db?sslmode=require"
    ).startswith("postgresql+psycopg://")
    with pytest.raises(ValueError, match="hosted PostgreSQL"):
        Settings("sqlite://", "x" * 32)
    with pytest.raises(ValueError, match="32 characters"):
        Settings("postgresql://host/db", "short")
