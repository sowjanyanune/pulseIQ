from dataclasses import dataclass
from pathlib import Path
import os
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Settings:
    database_url: str
    app_secret: str
    admin_password: str = ""
    seed_demo: bool = False
    demo_students: int = 1000
    cookie_secure: bool = True
    environment: str = "production"

    def __post_init__(self):
        self.database_url = normalize_url(self.database_url)
        if len(self.app_secret) < 32:
            raise ValueError(
                "APP_SECRET must have at least 32 characters; use Render generateValue."
            )
        if self.environment != "test" and not self.database_url.startswith(
            "postgresql+psycopg://"
        ):
            raise ValueError(
                "The application database must be hosted PostgreSQL. SQLite is test-only."
            )
        if not 200 <= self.demo_students <= 10000:
            raise ValueError("DEMO_STUDENTS must be between 200 and 10000.")

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
        url = os.environ.get("DATABASE_URL", "")
        if not url:
            raise ValueError(
                "Set DATABASE_URL to the complete Supabase PostgreSQL Session pooler connection URI in Render."
            )
        return cls(
            url,
            os.environ.get("APP_SECRET", ""),
            os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", ""),
            os.environ.get("SEED_DEMO", "false").lower() == "true",
            int(os.environ.get("DEMO_STUDENTS", "1000")),
            os.environ.get("COOKIE_SECURE", "true").lower() == "true",
            os.environ.get("ENVIRONMENT", "production"),
        )


def normalize_url(value):
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://") :]
    if value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    make_url(value)  # validate without connecting or printing credentials
    return value
