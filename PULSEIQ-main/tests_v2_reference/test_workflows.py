from copy import deepcopy
from datetime import date, timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update, func
from backend.db import students, TABLES, users, sessions, interventions, history, now
from backend.repository import records_from_database, replace_snapshot
from backend.seed import generate
from backend.validation import InvalidSnapshot
from conftest import sign_in, PASSWORD


def test_health_and_anonymous_access(client):
    assert client.get("/health").json()["status"] == "ok"
    for path in [
        "/api/meta",
        "/api/cohort",
        "/api/actions",
        "/api/students/DEMO0001",
        "/api/quality",
        "/api/admin/users",
    ]:
        assert client.get(path).status_code == 401


def test_cookie_session_csrf_and_logout(admin, action_body):
    cookie = admin.cookies.get("pulseiq_session")
    assert cookie and admin.get("/api/auth/me").json()["user"]["username"] == "admin"
    good = admin.headers.pop("X-CSRF-Token")
    assert admin.post("/api/actions", json=action_body).status_code == 403
    admin.headers["X-CSRF-Token"] = good
    assert admin.post("/api/actions", json=action_body).status_code == 201
    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/actions").status_code == 401


def test_secure_cookie_and_cross_origin(app_factory):
    with TestClient(
        app_factory(cookie_secure=True), base_url="https://testserver"
    ) as c:
        response = sign_in(c)
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "Secure" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert (
            c.post(
                "/api/auth/logout", headers={"Origin": "https://attacker.example"}
            ).status_code
            == 403
        )
        assert (
            c.post(
                "/api/auth/logout", headers={"Origin": "https://testserver"}
            ).status_code
            == 200
        )


def test_login_failures_are_rate_limited(client):
    for _ in range(8):
        assert (
            client.post(
                "/api/auth/login", json={"username": "admin", "password": "incorrect"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "admin", "password": PASSWORD}
        ).status_code
        == 429
    )


def test_expired_and_deactivated_sessions(admin):
    with admin.app.state.engine.begin() as conn:
        conn.execute(update(sessions).values(expires_at=now() - timedelta(seconds=1)))
    assert admin.get("/api/auth/me").status_code == 401
    sign_in(admin)
    with admin.app.state.engine.begin() as conn:
        conn.execute(update(users).values(active=False))
    assert admin.get("/api/cohort").status_code == 401


def test_database_seed_and_reference_score(admin, period):
    cohort = admin.get("/api/cohort").json()
    assert cohort["total"] == 1000
    assert sum(cohort["status_counts"].values()) == 1000
    assert cohort["status_counts"] == {
        "Complete": 964,
        "Provisional": 35,
        "Insufficient data": 1,
    }
    record = admin.get("/api/students/DEMO0001").json()
    assert record["record"]["overall_score"] == 68.0
    assert record["record"]["A"] == 80 and record["record"]["P"] == 40
    assert "Strong academics with placement gap" in record["record"]["segments"]
    assert sum(c["weighted_points"] for c in record["components"]) == 68.0
    assert all(
        c["source_name"] and c["period_end"] == period for c in record["components"]
    )
    assert admin.get("/api/cohort").headers["cache-control"] == "no-store"


def test_department_semester_and_segment_filters(admin):
    view = admin.get(
        "/api/cohort", params={"department": "Computer Science", "semester": 4}
    ).json()
    assert view["total"] == 250 and all(
        r["department"] == "Computer Science" and r["semester"] == 4
        for r in view["items"]
    )
    gap = admin.get(
        "/api/cohort", params={"segment": "Strong academics with placement gap"}
    ).json()
    assert gap["total"] > 0 and all(
        "Strong academics with placement gap" in r["segments"] for r in gap["items"]
    )
    requested = admin.get("/api/cohort", params={"segment": "Support requested"}).json()
    assert requested["total"] > 0 and all(
        r["support_request"] for r in requested["items"]
    )
    assert admin.get("/api/cohort", params={"period": "1990-01-01"}).status_code == 400
    assert admin.get("/api/cohort", params={"stale_days": -1}).status_code == 422


def test_stale_future_and_insufficient_evidence(admin, period):
    stale = admin.get(
        "/api/cohort",
        params={
            "period": period,
            "analysis_date": (
                date.fromisoformat(period) + timedelta(days=31)
            ).isoformat(),
        },
    ).json()
    assert stale["status_counts"]["Insufficient data"] == 1000
    assert (
        stale["academic_support"]
        == stale["placement_support"]
        == stale["support_requests"]
        == 0
    )
    future = admin.get(
        "/api/students/DEMO0001",
        params={
            "period": period,
            "analysis_date": (
                date.fromisoformat(period) - timedelta(days=1)
            ).isoformat(),
        },
    ).json()["record"]
    assert (
        future["overall_score"] is None
        and future["academic_flag"] == future["placement_flag"] == "Undetermined"
    )
    missing = admin.get("/api/students/DEMO0005").json()["record"]
    assert missing["coverage"] == 0.75 and missing["overall_score"] is None
    zero = admin.get("/api/students/DEMO0006").json()["record"]
    assert zero["E"] is None and zero["score_status"] == "Provisional"
    assert zero["overall_score"] == round(65.5 / 0.95, 2)


def test_support_request_has_no_score_penalty(admin):
    reference = admin.get("/api/students/DEMO0001").json()["record"]
    request = admin.get("/api/students/DEMO0007").json()["record"]
    assert request["overall_score"] == reference["overall_score"] == 68
    assert request["support_request"] and request["support_category"] == "Other"
    assert any(
        "support_requested=true" in r["trigger"] for r in request["recommendations"]
    )


def test_scenario_does_not_mutate_database(admin, period):
    before = admin.get("/api/students/DEMO0001").json()["record"]
    body = dict(
        period=period,
        analysis_date=date.today().isoformat(),
        stale_days=30,
        changes={"coding_pct": 80, "aptitude_pct": 80, "interview_pct": 80},
    )
    result = admin.post("/api/students/DEMO0001/scenario", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["scenario"]["overall_score"] == 78
    assert result.json()["baseline"]["overall_score"] == 68
    after = admin.get("/api/students/DEMO0001").json()["record"]
    assert before == after
    for changes in [
        {"coding_pct": 101},
        {"classes_attended": 41},
        {"classes_attended": 20.5},
        {"semester": 2},
    ]:
        assert (
            admin.post(
                "/api/students/DEMO0001/scenario", json={**body, "changes": changes}
            ).status_code
            == 400
        )
    assert (
        admin.post(
            "/api/students/DEMO0005/scenario",
            json={**body, "changes": {"coding_pct": 80}},
        ).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/students/DEMO0001/scenario",
            json={
                **body,
                "analysis_date": (date.today() + timedelta(days=40)).isoformat(),
            },
        ).status_code
        == 400
    )


def test_action_review_reopen_history_and_edit_conflict(admin, action_body):
    response = admin.post("/api/actions", json=action_body)
    assert response.status_code == 201, response.text
    action = response.json()
    aid = action["id"]
    revision = {
        k: action[k]
        for k in [
            "owner_alias",
            "action",
            "due_date",
            "status",
            "review_note",
            "version",
        ]
    }
    assert (
        admin.patch(
            "/api/actions/" + aid, json={**revision, "status": "Reviewed"}
        ).status_code
        == 400
    )
    reviewed = {
        **revision,
        "status": "Reviewed",
        "review_note": "Student attended the coding workshop; review next assessment.",
    }
    saved = admin.patch("/api/actions/" + aid, json=reviewed)
    assert saved.status_code == 200 and saved.json()["version"] == 2
    assert admin.patch("/api/actions/" + aid, json=reviewed).status_code == 409
    reopened = {
        **reviewed,
        "version": 2,
        "status": "In progress",
        "review_note": "Additional practice agreed during review.",
    }
    assert admin.patch("/api/actions/" + aid, json=reopened).json()["version"] == 3
    events = admin.get("/api/actions/" + aid + "/history").json()["items"]
    assert [r["event"] for r in events] == ["Created", "Updated", "Reopened"]
    assert [r["snapshot"]["version"] for r in events] == [1, 2, 3]
    assert all(r["actor"] == "admin" for r in events)
    assert events[1]["snapshot"]["review_note"] == reviewed["review_note"]
    assert admin.get("/api/actions").json()["items"][0]["status"] == "In progress"
    assert (
        admin.patch(
            "/api/actions/" + aid, json={**reopened, "version": 3, "status": "Unknown"}
        ).status_code
        == 400
    )


def test_concurrent_action_edits_commit_only_one_revision(admin, action_body):
    action = admin.post("/api/actions", json=action_body).json()
    revision = {
        k: action[k]
        for k in [
            "owner_alias",
            "action",
            "due_date",
            "status",
            "review_note",
            "version",
        ]
    }
    revision["status"] = "In progress"

    def edit(_):
        return admin.patch("/api/actions/" + action["id"], json=revision).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, range(2)))
    assert sorted(results) == [200, 409]
    events = admin.get("/api/actions/" + action["id"] + "/history").json()["items"]
    assert len(events) == 2 and events[-1]["snapshot"]["version"] == 2


def test_parallel_dashboard_reads_and_actions_use_independent_connections(
    admin, action_body
):
    aid = admin.post("/api/actions", json=action_body).json()["id"]
    paths = ["/api/cohort", "/api/actions", "/api/students/DEMO0001"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(admin.get, paths))
    assert all(r.status_code == 200 for r in responses)
    assert responses[0].json()["total"] == 1000
    assert responses[1].json()["items"][0]["id"] == aid
    assert responses[2].json()["record"]["overall_score"] == 68


def test_staff_role_and_department_permissions(admin, action_body):
    cse = admin.post("/api/actions", json=action_body).json()["id"]
    other = admin.post(
        "/api/actions", json={**action_body, "student_id": "DEMO0002"}
    ).json()["id"]
    body = dict(
        username="mentor.cs",
        password=PASSWORD,
        role="faculty",
        departments=["Computer Science"],
    )
    assert admin.post("/api/admin/users", json=body).status_code == 201
    assert admin.post("/api/admin/users", json=body).status_code == 409
    assert (
        admin.post(
            "/api/admin/users",
            json={**body, "username": "baddept", "departments": ["Unknown"]},
        ).status_code
        == 400
    )
    assert (
        admin.post(
            "/api/admin/users", json={**body, "username": "nodept", "departments": []}
        ).status_code
        == 400
    )
    sign_in(admin, "mentor.cs")
    assert admin.get("/api/meta").json()["departments"] == ["Computer Science"]
    assert admin.get("/api/cohort").json()["total"] == 250
    assert (
        admin.get("/api/cohort", params={"department": "Electronics"}).json()["total"]
        == 0
    )
    assert admin.get("/api/students/DEMO0001").status_code == 200
    assert admin.get("/api/students/DEMO0002").status_code == 404
    assert [a["id"] for a in admin.get("/api/actions").json()["items"]] == [cse]
    assert admin.get("/api/actions/" + other + "/history").status_code == 404
    assert (
        admin.post(
            "/api/actions", json={**action_body, "student_id": "DEMO0002"}
        ).status_code
        == 404
    )
    for path in ["/api/quality", "/api/admin/users"]:
        assert admin.get(path).status_code == 403
    assert admin.post("/api/admin/users", json=body).status_code == 403
    assert admin.post("/api/admin/sync").status_code == 403


def test_actions_accounts_sessions_survive_backend_restart(app_factory, action_body):
    with TestClient(app_factory()) as first:
        sign_in(first)
        action = first.post("/api/actions", json=action_body).json()
        cookies = dict(first.cookies)
        csrf = first.headers["X-CSRF-Token"]
        assert (
            first.post(
                "/api/admin/users",
                json=dict(
                    username="placement.cs",
                    password=PASSWORD,
                    role="placement",
                    departments=["Computer Science"],
                ),
            ).status_code
            == 201
        )
    # Reconstruct app and engine using the same database, as on a cloud restart.
    with TestClient(
        app_factory(admin_password="different-bootstrap-password")
    ) as second:
        second.cookies.update(cookies)
        second.headers["X-CSRF-Token"] = csrf
        assert second.get("/api/auth/me").status_code == 200
        assert second.get("/api/cohort").json()["total"] == 1000
        assert second.get("/api/actions").json()["items"][0]["id"] == action["id"]
        assert (
            len(second.get("/api/actions/" + action["id"] + "/history").json()["items"])
            == 1
        )
        sign_in(second, "placement.cs")
        assert second.get("/api/cohort").json()["total"] == 250


def test_failed_refresh_preserves_snapshot_actions_and_history(
    admin, action_body, monkeypatch
):
    import backend.main as module

    aid = admin.post("/api/actions", json=action_body).json()["id"]
    before = admin.get("/api/students/DEMO0001").json()
    bad = generate(200)
    bad["academic"].append(deepcopy(bad["academic"][0]))
    monkeypatch.setattr(module, "fetch_source", lambda _: bad)
    blocked = admin.post("/api/admin/sync")
    assert (
        blocked.status_code == 400
        and "preserved" in blocked.json()["detail"]["message"]
    )
    assert admin.get("/api/students/DEMO0001").json() == before
    assert admin.get("/api/cohort").json()["total"] == 1000
    assert admin.get("/api/actions").json()["items"][0]["id"] == aid
    assert len(admin.get("/api/actions/" + aid + "/history").json()["items"]) == 1
    assert admin.get("/api/quality").json()["sync_history"][0]["status"] == "Blocked"


def test_successful_refresh_preserves_actions_when_student_leaves(
    admin, action_body, monkeypatch
):
    import backend.main as module

    aid = admin.post("/api/actions", json=action_body).json()["id"]
    replacement = generate(200)
    for source in replacement:
        replacement[source] = [
            r for r in replacement[source] if r["student_id"] != "DEMO0001"
        ]
    monkeypatch.setattr(module, "fetch_source", lambda _: replacement)
    response = admin.post("/api/admin/sync")
    assert response.status_code == 200, response.text
    assert response.json()["students"] == 199 and not response.json()["demo"]
    assert admin.get("/api/students/DEMO0001").status_code == 404
    assert admin.get("/api/actions").json()["items"][0]["id"] == aid
    assert len(admin.get("/api/actions/" + aid + "/history").json()["items"]) == 1
    assert admin.post("/api/actions", json=action_body).status_code == 400


def test_refresh_transaction_rolls_back_database_failure(admin, monkeypatch):
    import backend.repository as module

    original = module.set_state

    def fail(*args):
        raise RuntimeError("Injected failure after entity replacement")

    monkeypatch.setattr(module, "set_state", fail)
    with pytest.raises(RuntimeError):
        replace_snapshot(admin.app.state.engine, generate(200), "Test source")
    monkeypatch.setattr(module, "set_state", original)
    assert admin.get("/api/cohort").json()["total"] == 1000


def test_bootstrap_requires_password_and_empty_install(app_factory):
    with pytest.raises(RuntimeError, match="BOOTSTRAP_ADMIN_PASSWORD"):
        with TestClient(app_factory(admin_password="short")):
            pass
    with TestClient(app_factory(seed_demo=False)) as c:
        sign_in(c)
        assert c.get("/api/cohort").json()["total"] == 0
        assert c.get("/api/meta").json()["periods"] == []


def test_roster_only_institution_snapshot_has_unknown_profiles_and_actions(admin):
    records = {
        "students": [
            {"student_id": "NEW001", "department": "Computer Science", "semester": 4}
        ]
    }
    replace_snapshot(admin.app.state.engine, records, "Institute roster")
    cohort = admin.get("/api/cohort")
    assert cohort.status_code == 200 and cohort.json()["total"] == 1
    assert cohort.json()["status_counts"]["Insufficient data"] == 1
    profile = admin.get("/api/students/NEW001").json()["record"]
    assert profile["overall_score"] is None and profile["coverage"] == 0
    assert profile["academic_flag"] == profile["placement_flag"] == "Undetermined"
    body = dict(
        student_id="NEW001",
        owner_alias="Mentor",
        action="Discuss support needs.",
        rationale="Roster-only snapshot.",
        due_date=date.today().isoformat(),
    )
    assert admin.post("/api/actions", json=body).status_code == 201
