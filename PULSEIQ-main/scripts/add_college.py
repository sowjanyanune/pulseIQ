"""Provision additional colleges; run privately from a trusted server terminal.
Example: python -m scripts.add_college --name 'Example Institute' --domain example.edu --admin-email admin@example.edu
Never make this command available as a public unauthenticated HTTP route.
"""
import argparse,getpass,uuid
from sqlalchemy import select,insert
from backend.settings import Settings
from backend.tenant_db import metadata,engine_for,accounts,colleges,now
from backend.tenant_auth import passwords

def main():
    p=argparse.ArgumentParser(description='Provision one additional tenant and its first admin')
    p.add_argument('--name',required=True);p.add_argument('--domain',required=True);p.add_argument('--admin-email',required=True)
    args=p.parse_args();domain=args.domain.strip().lower();email=args.admin_email.strip().lower()
    if '@' not in email or email.partition('@')[2]!=domain:raise SystemExit('Admin email must match the exact college domain.')
    if not domain or '/' in domain:raise SystemExit('Invalid college domain.')
    pw=getpass.getpass('New college admin password (12+ characters): ')
    if len(pw)<12:raise SystemExit('Password too short.')
    settings=Settings.from_env();engine=engine_for(settings.database_url)
    try:
        metadata.create_all(engine)
        with engine.begin() as c:
            if c.execute(select(colleges.c.id).where(colleges.c.domain==domain)).first():raise SystemExit('This college domain is already registered.')
            if c.execute(select(accounts.c.id).where(accounts.c.email==email)).first():raise SystemExit('This email is already registered.')
            college_id=str(uuid.uuid4())
            c.execute(insert(colleges).values(id=college_id,name=args.name.strip(),domain=domain,created_at=now()))
            c.execute(insert(accounts).values(id=str(uuid.uuid4()),college_id=college_id,email=email,full_name='College Administrator',password_hash=passwords.hash(pw),role='admin',departments=[],student_id=None,active=True))
        print(f'Created college {args.name!r} ({domain}). Admin: {email}')
    finally:engine.dispose()

if __name__=='__main__':main()
