"""Read-only institution connectors configured by server environment and field maps."""

from pathlib import Path
import json, os
from sqlalchemy import create_engine, MetaData, Table, select, literal
from sqlalchemy.engine import make_url
import httpx
from .db import SCHEMAS
from .settings import ROOT, normalize_url


class ConnectorError(ValueError):
    pass


def source_info():
    kind = os.environ.get("SOURCE_KIND", "none").lower()
    return {
        "kind": kind,
        "name": os.environ.get("SOURCE_NAME", "Institution database"),
        "configured": kind in ("sql", "mongodb", "api"),
        "mapping_path": os.environ.get("SOURCE_MAPPING", "connectors/mapping.json"),
    }


def mapping():
    path = ROOT / os.environ.get("SOURCE_MAPPING", "connectors/mapping.json")
    try:
        config = json.loads(path.read_text())
    except (OSError, ValueError):
        raise ConnectorError(
            "Configure connectors/mapping.json with the institution table/field mapping."
        )
    if "students" not in config:
        raise ConnectorError("The source mapping needs a students entity.")
    return config


def fetch_sql(url, config, app_url):
    src = make_url(normalize_url(url))
    dst = make_url(normalize_url(app_url))
    if (src.drivername, src.host, src.port, src.database) == (
        dst.drivername,
        dst.host,
        dst.port,
        dst.database,
    ):
        raise ConnectorError(
            "The institution source database must be separate from the PULSEIQ application database."
        )
    engine = create_engine(src, pool_pre_ping=True)
    output = {}
    try:
        with engine.connect() as conn:
            for source, definition in config.items():
                if source not in SCHEMAS:
                    raise ConnectorError("Unknown entity in the source mapping.")
                table = Table(
                    definition["table"],
                    MetaData(),
                    schema=definition.get("schema"),
                    autoload_with=conn,
                )
                columns = definition.get("columns", {f: f for f in SCHEMAS[source]})
                selected = []
                for field in SCHEMAS[source]:
                    col = columns.get(field)
                    if col is None:
                        selected.append(literal(None).label(field))
                    elif col not in table.c:
                        raise ConnectorError(
                            f"Mapped field missing for {source}.{field}."
                        )
                    else:
                        selected.append(table.c[col].label(field))
                rows = conn.execute(select(*selected).limit(20001)).mappings()
                output[source] = [dict(r) for r in rows]
    finally:
        engine.dispose()
    return output


def nested(record, key):
    if key is None:
        return None
    current = record
    for part in key.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def fetch_mongo(uri, database, config):
    from pymongo import MongoClient

    output = {}
    with MongoClient(
        uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000
    ) as client:
        for source, definition in config.items():
            fields = definition.get("columns", {f: f for f in SCHEMAS[source]})
            docs = (
                client[database][definition["table"]]
                .find({}, projection={"_id": 0})
                .limit(20001)
            )
            output[source] = [
                {f: nested(row, fields.get(f)) for f in SCHEMAS[source]} for row in docs
            ]
    return output


def fetch_api(url, token, transport=None):
    if not url.startswith("https://"):
        raise ConnectorError("The institution API URL must use HTTPS.")
    headers = {"Authorization": "Bearer " + token} if token else {}
    with httpx.Client(
        timeout=30, follow_redirects=False, transport=transport
    ) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        if len(response.content) > 10 * 1024 * 1024:
            raise ConnectorError("Source API response exceeds 10 MiB.")
        body = response.json()
        if not isinstance(body, dict) or "students" not in body:
            raise ConnectorError(
                "API must return canonical entity arrays including students."
            )
        return body


def fetch_source(app_url):
    kind = source_info()["kind"]
    if kind == "sql":
        url = os.environ.get("SOURCE_DATABASE_URL", "")
        if not url:
            raise ConnectorError(
                "Set SOURCE_DATABASE_URL in the backend host settings."
            )
        return fetch_sql(url, mapping(), app_url)
    if kind == "mongodb":
        return fetch_mongo(
            os.environ["SOURCE_MONGODB_URI"],
            os.environ["SOURCE_MONGODB_DATABASE"],
            mapping(),
        )
    if kind == "api":
        return fetch_api(
            os.environ["SOURCE_API_URL"], os.environ.get("SOURCE_API_TOKEN", "")
        )
    raise ConnectorError(
        "Configure SOURCE_KIND=sql, mongodb or api before refreshing from an institution."
    )
