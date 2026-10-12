from datetime import timedelta, timezone
import hashlib, hmac, secrets, uuid
from fastapi import HTTPException, Request
from sqlalchemy import select, insert, delete, func
from pwdlib import PasswordHash
from .db import users, sessions, attempts, now

passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash("placeholder-for-constant-work")
COOKIE = "pulseiq_session"


def fingerprint(value, secret):
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def public_user(row):
    return {k: row[k] for k in ["id", "username", "role", "departments"]}


def login(engine, settings, username, password, ip):
    username = username.strip().lower()
    identity = fingerprint(username + "|" + ip, settings.app_secret)
    stamp = now()
    with engine.begin() as conn:
        conn.execute(
            delete(attempts).where(attempts.c.at < stamp - timedelta(minutes=15))
        )
        count = conn.execute(
            select(func.count())
            .select_from(attempts)
            .where(attempts.c.identity_hash == identity)
        ).scalar()
        if count >= 8:
            raise HTTPException(
                429, "Too many login attempts. Try again after 15 minutes."
            )
        row = (
            conn.execute(select(users).where(users.c.username == username))
            .mappings()
            .first()
        )
        valid = passwords.verify(password, row["password_hash"] if row else DUMMY_HASH)
        if not row or not row["active"] or not valid:
            conn.execute(
                insert(attempts).values(
                    id=str(uuid.uuid4()), identity_hash=identity, at=stamp
                )
            )
            # Commit the attempt before raising outside this transaction.
            failure = True
        else:
            failure = False
            conn.execute(delete(attempts).where(attempts.c.identity_hash == identity))
            conn.execute(delete(sessions).where(sessions.c.expires_at < stamp))
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(24)
            conn.execute(
                insert(sessions).values(
                    token_hash=fingerprint(token, settings.app_secret),
                    user_id=row["id"],
                    csrf_token=csrf,
                    expires_at=stamp + timedelta(hours=8),
                )
            )
            result = {"user": public_user(row), "csrf_token": csrf}
    if failure:
        raise HTTPException(401, "Invalid username or password.")
    return token, result


def identity(request: Request):
    app = request.app
    token = request.cookies.get(COOKIE, "")
    if not token:
        raise HTTPException(401, "Sign in to continue.")
    with app.state.engine.connect() as conn:
        row = (
            conn.execute(
                select(sessions.c.csrf_token, sessions.c.expires_at, users)
                .join(users, users.c.id == sessions.c.user_id)
                .where(
                    sessions.c.token_hash
                    == fingerprint(token, app.state.settings.app_secret)
                )
            )
            .mappings()
            .first()
        )
    if not row or not row["active"]:
        raise HTTPException(401, "Session expired. Sign in again.")
    expiry = row["expires_at"]
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry < now():
        raise HTTPException(401, "Session expired. Sign in again.")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not hmac.compare_digest(
            request.headers.get("X-CSRF-Token", ""), row["csrf_token"]
        ):
            raise HTTPException(403, "Invalid CSRF token. Reload and try again.")
    return dict(public_user(row), csrf_token=row["csrf_token"])


def admin_user(user):
    if user["role"] != "admin":
        raise HTTPException(403, "Administrator access required.")


def can_view(user, department):
    return user["role"] == "admin" or department in user["departments"]
