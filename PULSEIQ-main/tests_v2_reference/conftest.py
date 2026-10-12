"""Isolated test databases; production settings never default to SQLite."""

import os, uuid
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from backend.settings import Settings
from backend.db import engine_for
from backend.main import create_app

PASSWORD = "test-password-not-for-deployment"
SECRET = "test-secret-only-at-least-thirty-two-characters"


@pytest.fixture
def app_factory(tmp_path):
    url = os.environ.get("PULSEIQ_TEST_DATABASE_URL") or "sqlite:///" + str(
        tmp_path / "app.sqlite"
    )
    schema = None
    if url.startswith(("postgres", "postgresql")):
        schema = "test_" + uuid.uuid4().hex
        base = engine_for(url)
        with base.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA {schema}"))

    def make(**changes):
        options = dict(
            database_url=url,
            app_secret=SECRET,
            admin_password=PASSWORD,
            seed_demo=True,
            demo_students=1000,
            cookie_secure=False,
            environment="test",
        )
        options.update(changes)
        settings = Settings(**options)
        engine = engine_for(url)
        if schema:
            engine = engine.execution_options(schema_translate_map={None: schema})
        return create_app(settings, engine)

    yield make
    if schema:
        with base.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        base.dispose()


@pytest.fixture
def client(app_factory):
    with TestClient(app_factory()) as c:
        yield c


def sign_in(client, username="admin", password=PASSWORD):
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    return response


@pytest.fixture
def admin(client):
    sign_in(client)
    return client


@pytest.fixture
def period(admin):
    return admin.get("/api/meta").json()["periods"][-1]


@pytest.fixture
def action_body():
    return dict(
        student_id="DEMO0001",
        owner_alias="Mentor CS-1",
        action="Agree on coding practice and review progress.",
        rationale="Fresh coding assessment is below the configured threshold.",
        due_date=date.today().isoformat(),
    )
