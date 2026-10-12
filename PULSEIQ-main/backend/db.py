from datetime import datetime, timezone
from sqlalchemy import (
    MetaData,
    Table,
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Date,
    DateTime,
    JSON,
    ForeignKey,
    create_engine,
    event,
)
from sqlalchemy.pool import StaticPool
from sqlalchemy.engine import make_url
from .settings import normalize_url

metadata = MetaData()
users = Table(
    "pulseiq_users",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("username", String(80), unique=True, nullable=False),
    Column("password_hash", String(300), nullable=False),
    Column("role", String(20), nullable=False),
    Column("departments", JSON, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)
sessions = Table(
    "pulseiq_sessions",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("user_id", ForeignKey("pulseiq_users.id"), nullable=False),
    Column("csrf_token", String(80), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
attempts = Table(
    "pulseiq_login_attempts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("identity_hash", String(64), index=True),
    Column("at", DateTime(timezone=True), nullable=False),
)
students = Table(
    "students",
    metadata,
    Column("student_id", String(100), primary_key=True),
    Column("department", String(100), nullable=False),
    Column("semester", Integer, nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)
SCHEMAS = {
    "students": ["student_id", "department", "semester"],
    "academic": ["student_id", "period_end", "marks_pct", "backlog_count"],
    "attendance": ["student_id", "period_end", "classes_attended", "classes_held"],
    "lms": [
        "student_id",
        "period_end",
        "assignments_completed",
        "assignments_assigned",
    ],
    "placement": [
        "student_id",
        "period_end",
        "aptitude_pct",
        "coding_pct",
        "interview_pct",
    ],
    "skills": ["student_id", "period_end", "technical_pct", "communication_pct"],
    "engagement": [
        "student_id",
        "period_end",
        "activities_completed",
        "activities_available",
    ],
    "feedback": ["student_id", "period_end", "support_requested", "support_category"],
}
TABLES = {"students": students}
for source, fields in list(SCHEMAS.items())[1:]:
    columns = [
        Column("student_id", ForeignKey("students.student_id"), primary_key=True),
        Column("period_end", Date, primary_key=True),
        Column("source_name", String(150), nullable=False),
        Column("imported_at", DateTime(timezone=True), nullable=False),
    ]
    for field in fields[2:]:
        kind = (
            Float
            if field.endswith("_pct")
            else (
                Boolean
                if field == "support_requested"
                else (String(50) if field == "support_category" else Integer)
            )
        )
        columns.append(Column(field, kind, nullable=True))
    TABLES[source] = Table(source, metadata, *columns)
interventions = Table(
    "interventions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("student_id", ForeignKey("students.student_id"), nullable=False),
    Column("owner_alias", String(80), nullable=False),
    Column("action", String(2000), nullable=False),
    Column("rationale", String(3000), nullable=False),
    Column("due_date", Date, nullable=False),
    Column("status", String(30), nullable=False),
    Column("review_note", String(2000), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("version", Integer, nullable=False),
)
history = Table(
    "intervention_history",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("intervention_id", ForeignKey("interventions.id"), nullable=False),
    Column("actor", String(80), nullable=False),
    Column("event", String(30), nullable=False),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("snapshot", JSON, nullable=False),
)
sync_log = Table(
    "sync_log",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("at", DateTime(timezone=True), nullable=False),
    Column("actor", String(80)),
    Column("status", String(20), nullable=False),
    Column("source", String(100), nullable=False),
    Column("summary", JSON, nullable=False),
)
state = Table(
    "pulseiq_state",
    metadata,
    Column("key", String(80), primary_key=True),
    Column("value", JSON, nullable=False),
)


def now():
    return datetime.now(timezone.utc)


def engine_for(url):
    url = normalize_url(url)
    if url.startswith("sqlite"):
        memory = make_url(url).database in (None, "", ":memory:")
        pool = (
            {"poolclass": StaticPool} if memory else {"pool_size": 3, "max_overflow": 2}
        )
        engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 15}, **pool
        )

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
        pool_recycle=300,
        connect_args={"prepare_threshold": None, "connect_timeout": 15},
    )
