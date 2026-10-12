from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
import uuid, json, os
from urllib.parse import urlsplit
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, insert, update, delete, func, text
from sqlalchemy.exc import SQLAlchemyError
from .settings import Settings, ROOT
from .db import (
    metadata,
    users,
    sessions,
    students,
    interventions,
    history,
    sync_log,
    state,
    now,
    engine_for,
)
from .auth import (
    identity,
    admin_user,
    can_view,
    login,
    passwords,
    fingerprint,
    COOKIE,
    public_user,
)
from .repository import (
    clean,
    replace_snapshot,
    records_from_database,
    scored_records,
    set_state,
)
from .connectors import source_info, fetch_source, ConnectorError
from .validation import InvalidSnapshot
from .seed import generate
from .scoring import CONFIG, component_breakdown, simulate

STATUSES = ["Planned", "In progress", "Reviewed", "Closed"]


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


class UserInput(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.-]{3,80}$")
    password: str = Field(min_length=6, max_length=200)
    role: str
    departments: list[str] = Field(default_factory=list, max_length=50)


class ActionInput(BaseModel):
    student_id: str = Field(min_length=1, max_length=100)
    owner_alias: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(default="", max_length=3000)
    due_date: date


class ActionRevision(BaseModel):
    owner_alias: str = Field(min_length=1, max_length=80)
    action: str = Field(min_length=1, max_length=2000)
    due_date: date
    status: str
    review_note: str = Field(default="", max_length=2000)
    version: int = Field(ge=1)


class ScenarioInput(BaseModel):
    period: str
    analysis_date: date
    stale_days: int = Field(default=30, ge=0, le=365)
    changes: dict[str, float]


def create_app(settings=None, engine=None):
    settings = settings or Settings.from_env()
    engine = engine or engine_for(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        metadata.create_all(engine)
        with engine.begin() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_xact_lock(763928451)"))
            existing = conn.execute(select(users.c.id).limit(1)).first()
            if not existing:
                if len(settings.admin_password) < 6:
                    raise RuntimeError(
                        "Set BOOTSTRAP_ADMIN_PASSWORD to at least 6 characters before first deployment."
                    )
                conn.execute(
                    insert(users).values(
                        id=str(uuid.uuid4()),
                        username="admin",
                        password_hash=passwords.hash(settings.admin_password),
                        role="admin",
                        departments=[],
                        active=True,
                    )
                )
            version = conn.execute(
                select(state.c.value).where(state.c.key == "schema_version")
            ).scalar_one_or_none()
            if version not in (None, 1):
                raise RuntimeError("Unsupported database schema version.")
            set_state(conn, "schema_version", 1)
            count = conn.execute(
                select(func.count()).select_from(students)
            ).scalar_one()
        if settings.seed_demo and count == 0:
            replace_snapshot(
                engine,
                generate(settings.demo_students),
                "Fictional college demo",
                "system",
                True,
            )
        yield
        engine.dispose()

    app = FastAPI(
        title="PULSEIQ",
        version="2.0.0",
        lifespan=lifespan,
        docs_url=(
            "/api/docs"
            if settings.environment == "test"
            or os.environ.get("ENABLE_API_DOCS") == "true"
            else None
        ),
        redoc_url=None,
        openapi_url=(
            "/api/openapi.json"
            if settings.environment == "test"
            or os.environ.get("ENABLE_API_DOCS") == "true"
            else None
        ),
    )
    app.state.settings = settings
    app.state.engine = engine

    @app.middleware("http")
    async def security_headers(request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(
            "origin"
        ):
            origin = urlsplit(request.headers["origin"]).netloc
            if origin != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "Cross-origin changes are not allowed."}, status_code=403
                )
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def db_failure(request, exc):
        return JSONResponse(
            {
                "detail": "Database operation failed. Check backend connection settings or retry."
            },
            status_code=503,
        )

    @app.get("/health")
    def health():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "version": "2.0.0"}

    @app.post("/api/auth/login")
    def sign_in(body: LoginInput, request: Request, response: Response):
        token, result = login(
            engine,
            settings,
            body.username,
            body.password,
            request.client.host if request.client else "unknown",
        )
        response.set_cookie(
            COOKIE,
            token,
            max_age=28800,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="strict",
            path="/",
        )
        return result

    @app.get("/api/auth/me")
    def me(user=Depends(identity)):
        return {
            "user": {k: v for k, v in user.items() if k != "csrf_token"},
            "csrf_token": user["csrf_token"],
        }

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, user=Depends(identity)):
        with engine.begin() as conn:
            conn.execute(
                delete(sessions).where(
                    sessions.c.token_hash
                    == fingerprint(request.cookies.get(COOKIE, ""), settings.app_secret)
                )
            )
        response.delete_cookie(
            COOKIE, path="/", secure=settings.cookie_secure, samesite="strict"
        )
        return {"ok": True}

    @app.get("/api/meta")
    def meta(user=Depends(identity)):
        records, data = records_from_database(engine)
        roster = [r for r in records["students"] if can_view(user, r["department"])]
        return {
            "periods": data.get("periods", []),
            "departments": sorted({r["department"] for r in roster}),
            "semesters": sorted({r["semester"] for r in roster}),
            "dataset": {k: v for k, v in data.items() if k != "quality_report"},
            "today": date.today().isoformat(),
            "scoring": CONFIG,
            "source": source_info() if user["role"] == "admin" else {"kind": "managed"},
        }

    def cohort_data(
        user,
        period,
        analysis_date,
        stale_days,
        department=None,
        semester=None,
        segment=None,
    ):
        try:
            return scored_records(
                engine,
                period,
                analysis_date or date.today(),
                stale_days,
                user,
                department,
                semester,
                segment,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/cohort")
    def cohort(
        period: str | None = None,
        analysis_date: date | None = None,
        stale_days: int = Query(30, ge=0, le=365),
        department: str | None = None,
        semester: int | None = None,
        segment: str | None = None,
        user=Depends(identity),
    ):
        rows, data = cohort_data(
            user, period, analysis_date, stale_days, department, semester, segment
        )
        segment_counts = {}
        for row in rows:
            for label in row["segments"]:
                segment_counts[label] = segment_counts.get(label, 0) + 1
        fields = [
            "student_id",
            "department",
            "semester",
            "overall_score",
            "score_status",
            "coverage",
            "academic_flag",
            "placement_flag",
            "support_request",
            "segments",
            "A",
            "T",
            "L",
            "P",
            "S",
            "E",
        ]
        counts = {
            label: sum(r["score_status"] == label for r in rows)
            for label in ["Complete", "Provisional", "Insufficient data"]
        }
        return {
            "items": [{k: r[k] for k in fields} for r in rows],
            "total": len(rows),
            "status_counts": counts,
            "segments": segment_counts,
            "academic_support": sum(
                r["academic_flag"] == "Support needed" for r in rows
            ),
            "placement_support": sum(
                r["placement_flag"] == "Support needed" for r in rows
            ),
            "support_requests": sum(r["support_request"] for r in rows),
            "period": period or (data["periods"][-1] if data["periods"] else None),
        }

    @app.get("/api/students/{student_id}")
    def student(
        student_id: str,
        period: str | None = None,
        analysis_date: date | None = None,
        stale_days: int = Query(30, ge=0, le=365),
        user=Depends(identity),
    ):
        rows, _ = cohort_data(user, period, analysis_date, stale_days)
        record = next((r for r in rows if r["student_id"] == student_id), None)
        if not record:
            raise HTTPException(
                404, "Student not found in your authorized departments."
            )
        return {
            "record": record,
            "components": clean(component_breakdown(record).to_dict("records")),
        }

    @app.post("/api/students/{student_id}/scenario")
    def scenario(student_id: str, body: ScenarioInput, user=Depends(identity)):
        rows, _ = cohort_data(user, body.period, body.analysis_date, body.stale_days)
        record = next((r for r in rows if r["student_id"] == student_id), None)
        if not record:
            raise HTTPException(404, "Student not found.")
        # Scenarios cannot invent unobserved, missing or stale source fields.
        source_for = {
            "marks_pct": "academic",
            "classes_attended": "attendance",
            "assignments_completed": "lms",
            "aptitude_pct": "placement",
            "coding_pct": "placement",
            "interview_pct": "placement",
        }
        for field in body.changes:
            if (
                field not in source_for
                or record.get(field) is None
                or not record[source_for[field] + "__fresh"]
            ):
                raise HTTPException(
                    400, "Only fresh observed scenario fields can be adjusted."
                )
        try:
            result = simulate(record, body.changes)
        except (ValueError, TypeError) as exc:
            raise HTTPException(400, str(exc))
        return {
            "baseline": record,
            "scenario": clean(result),
            "notice": "Illustrative score change, not a prediction of improvement.",
        }

    @app.get("/api/actions")
    def actions(
        department: str | None = None,
        semester: int | None = None,
        user=Depends(identity),
    ):
        with engine.connect() as conn:
            query = select(
                interventions, students.c.department, students.c.semester
            ).join(students, students.c.student_id == interventions.c.student_id)
            if user["role"] != "admin":
                query = query.where(students.c.department.in_(user["departments"]))
            if department:
                query = query.where(students.c.department == department)
            if semester:
                query = query.where(students.c.semester == semester)
            rows = [
                dict(r)
                for r in conn.execute(
                    query.order_by(interventions.c.due_date)
                ).mappings()
            ]
        return {"items": clean(rows)}

    def visible_student(conn, sid, user):
        row = (
            conn.execute(select(students).where(students.c.student_id == sid))
            .mappings()
            .first()
        )
        if not row or not can_view(user, row["department"]):
            raise HTTPException(
                404, "Student not found in your authorized departments."
            )
        return row

    def event(conn, record, user, event):
        conn.execute(
            insert(history).values(
                id=str(uuid.uuid4()),
                intervention_id=record["id"],
                actor=user["username"],
                event=event,
                at=now(),
                snapshot=clean(record),
            )
        )

    @app.post("/api/actions", status_code=201)
    def add_action(body: ActionInput, user=Depends(identity)):
        if not body.owner_alias.strip() or not body.action.strip():
            raise HTTPException(400, "Owner and action cannot be blank.")
        stamp = now()
        record = body.model_dump()
        record.update(
            id=str(uuid.uuid4()),
            status="Planned",
            review_note="",
            created_at=stamp,
            updated_at=stamp,
            version=1,
        )
        record["owner_alias"] = record["owner_alias"].strip()
        record["action"] = record["action"].strip()
        with engine.begin() as conn:
            roster = visible_student(conn, body.student_id, user)
            if not roster["active"]:
                raise HTTPException(400, "Student is outside the current snapshot.")
            conn.execute(insert(interventions).values(**record))
            event(conn, record, user, "Created")
        return clean(record)

    @app.patch("/api/actions/{action_id}")
    def revise(action_id: str, body: ActionRevision, user=Depends(identity)):
        if body.status not in STATUSES:
            raise HTTPException(400, "Invalid review status.")
        if body.status in ("Reviewed", "Closed") and not body.review_note.strip():
            raise HTTPException(
                400, "Reviewed and Closed actions require a review note."
            )
        if not body.owner_alias.strip() or not body.action.strip():
            raise HTTPException(400, "Owner and action cannot be blank.")
        with engine.begin() as conn:
            old = (
                conn.execute(
                    select(interventions).where(interventions.c.id == action_id)
                )
                .mappings()
                .first()
            )
            if not old:
                raise HTTPException(404, "Action not found.")
            visible_student(conn, old["student_id"], user)
            if old["version"] != body.version:
                raise HTTPException(
                    409,
                    "Another staff member updated this action. Refresh before editing.",
                )
            change = body.model_dump(exclude={"version"})
            change.update(updated_at=now(), version=old["version"] + 1)
            outcome = conn.execute(
                update(interventions)
                .where(
                    interventions.c.id == action_id,
                    interventions.c.version == body.version,
                )
                .values(**change)
            )
            if outcome.rowcount != 1:
                raise HTTPException(
                    409, "Action changed concurrently. Refresh and retry."
                )
            record = {**dict(old), **change}
            reopened = old["status"] in ("Reviewed", "Closed") and body.status in (
                "Planned",
                "In progress",
            )
            event(conn, record, user, "Reopened" if reopened else "Updated")
        return clean(record)

    @app.get("/api/actions/{action_id}/history")
    def revisions(action_id: str, user=Depends(identity)):
        with engine.connect() as conn:
            row = (
                conn.execute(
                    select(interventions).where(interventions.c.id == action_id)
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(404, "Action not found.")
            visible_student(conn, row["student_id"], user)
            events = [
                dict(r)
                for r in conn.execute(
                    select(history)
                    .where(history.c.intervention_id == action_id)
                    .order_by(history.c.at)
                ).mappings()
            ]
        return {"items": clean(events)}

    @app.get("/api/quality")
    def quality(user=Depends(identity)):
        # This operational report includes all institution records; restricted to admin.
        admin_user(user)
        records, data = records_from_database(engine)
        with engine.connect() as conn:
            logs = [
                dict(r)
                for r in conn.execute(
                    select(sync_log).order_by(sync_log.c.at.desc()).limit(10)
                ).mappings()
            ]
        return {
            "dataset": data,
            "sync_history": clean(logs),
            "connector": source_info(),
        }

    @app.post("/api/admin/sync")
    def synchronize(user=Depends(identity)):
        admin_user(user)
        label = source_info()["name"]
        try:
            return replace_snapshot(
                engine, fetch_source(settings.database_url), label, user["username"]
            )
        except InvalidSnapshot as exc:
            with engine.begin() as conn:
                conn.execute(
                    insert(sync_log).values(
                        id=str(uuid.uuid4()),
                        at=now(),
                        actor=user["username"],
                        status="Blocked",
                        source=label,
                        summary={"report": exc.report},
                    )
                )
            raise HTTPException(
                400,
                {
                    "message": "Source validation failed; previous snapshot preserved.",
                    "report": exc.report,
                },
            )
        except ConnectorError as exc:
            raise HTTPException(400, str(exc))
        except Exception:
            raise HTTPException(
                502,
                "Institution connection failed. Check source settings, mapping, driver and network access in Render.",
            )

    @app.get("/api/admin/users")
    def user_list(user=Depends(identity)):
        admin_user(user)
        with engine.connect() as conn:
            return {
                "items": [
                    public_user(r) for r in conn.execute(select(users)).mappings()
                ]
            }

    @app.post("/api/admin/users", status_code=201)
    def user_add(body: UserInput, user=Depends(identity)):
        admin_user(user)
        if body.role not in ("admin", "faculty", "placement"):
            raise HTTPException(400, "Role must be admin, faculty or placement.")
        if body.role != "admin" and not body.departments:
            raise HTTPException(400, "Assign at least one department to this user.")
        with engine.begin() as conn:
            username = body.username.lower()
            if conn.execute(
                select(users.c.id).where(users.c.username == username)
            ).first():
                raise HTTPException(409, "Username already exists.")
            records, _ = records_from_database(engine)
            allowed = {r["department"] for r in records["students"]}
            if set(body.departments) - allowed:
                raise HTTPException(400, "Select departments from the active roster.")
            record = dict(
                id=str(uuid.uuid4()),
                username=username,
                password_hash=passwords.hash(body.password),
                role=body.role,
                departments=body.departments,
                active=True,
            )
            conn.execute(insert(users).values(**record))
        return public_user(record)

    dist = ROOT / "frontend" / "dist"
    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith(("api/", "assets/")):
            raise HTTPException(404, "Not found.")
        if not (dist / "index.html").exists():
            return JSONResponse(
                {
                    "detail": "Frontend build missing. Deploy using the included Dockerfile."
                },
                status_code=503,
            )
        return FileResponse(dist / "index.html")

    return app
