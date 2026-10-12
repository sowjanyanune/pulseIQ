"""Role-and-college-scoped cookie authentication for v3."""
import hashlib, hmac, secrets, uuid
from datetime import timedelta, timezone
from fastapi import HTTPException, Request
from sqlalchemy import select, delete, insert, func
from pwdlib import PasswordHash
from .tenant_db import accounts, colleges, attempts, sessions, now

passwords=PasswordHash.recommended()
DUMMY=passwords.hash('fixed-placeholder-pulseiq')
COOKIE='pulseiq_v3_session'

def digest(raw, secret):
    return hmac.new(secret.encode(),raw.encode(),hashlib.sha256).hexdigest()

def public(row):
    return {k:row[k] for k in ('id','email','full_name','role','college_id','college_name','departments','student_id')}

def login(engine, settings, email, password, ip):
    email=email.strip().lower()
    stamp=now()
    stamp_id=digest(email+'|'+ip,settings.app_secret)
    with engine.begin() as c:
        c.execute(delete(attempts).where(attempts.c.at < stamp-timedelta(minutes=15)))
        failures=c.execute(select(func.count()).where(attempts.c.identity_hash==stamp_id)).scalar_one()
        if failures >= 8: raise HTTPException(429,'Too many attempts; retry after 15 minutes.')
        row=c.execute(select(accounts,colleges.c.name.label('college_name')).join(colleges,accounts.c.college_id==colleges.c.id).where(accounts.c.email==email)).mappings().first()
        ok=passwords.verify(password,row['password_hash'] if row else DUMMY)
        if not row or not row['active'] or not ok:
            c.execute(insert(attempts).values(id=str(uuid.uuid4()),identity_hash=stamp_id,at=stamp))
            failed=True
        else:
            failed=False
            c.execute(delete(attempts).where(attempts.c.identity_hash==stamp_id))
            c.execute(delete(sessions).where(sessions.c.expires_at<stamp))
            token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(24)
            c.execute(insert(sessions).values(token_hash=digest(token,settings.app_secret),user_id=row['id'],csrf_token=csrf,expires_at=stamp+timedelta(hours=8)))
            result={'user':public(row),'csrf_token':csrf}
    if failed: raise HTTPException(401,'Invalid email or password.')
    return token,result

def identity(request:Request):
    token=request.cookies.get(COOKIE,'')
    if not token: raise HTTPException(401,'Sign in to continue.')
    with request.app.state.engine.connect() as c:
        row=c.execute(select(accounts,colleges.c.name.label('college_name'),sessions.c.csrf_token,sessions.c.expires_at).join(sessions,accounts.c.id==sessions.c.user_id).join(colleges,accounts.c.college_id==colleges.c.id).where(sessions.c.token_hash==digest(token,request.app.state.settings.app_secret))).mappings().first()
    if not row or not row['active']:raise HTTPException(401,'Your session has expired.')
    expiry=row['expires_at']
    if expiry.tzinfo is None:expiry=expiry.replace(tzinfo=timezone.utc)
    if expiry<=now():raise HTTPException(401,'Your session has expired.')
    if request.method not in ('GET','HEAD','OPTIONS') and not hmac.compare_digest(request.headers.get('X-CSRF-Token',''),row['csrf_token']):
        raise HTTPException(403,'Invalid CSRF token.')
    return dict(public(row),csrf_token=row['csrf_token'])

def roles(user,*allowed):
    if user['role'] not in allowed:raise HTTPException(403,'This action is not permitted for your role.')
