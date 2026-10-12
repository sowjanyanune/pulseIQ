"""Self-service institution onboarding and per-college preferences.

This product uses one Supabase PostgreSQL deployment with logically isolated,
college-scoped rows. It does NOT claim to provision separate Supabase projects.
"""
import os
import re
import uuid
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, insert, update
from sqlalchemy.exc import IntegrityError
from .tenant_db import colleges, accounts, college_preferences, now
from .tenant_auth import identity, roles, passwords
from .tenant_data import audit

DOMAIN = re.compile(r'^(?=.{3,150}$)[a-z0-9]+(?:[.-][a-z0-9]+)*\.[a-z]{2,}$')

DEFAULTS={
    'academic_year':'2026-2027', 'semester_system':'semester',
    'timezone':'Asia/Kolkata',
    'attendance_threshold':75, 'pass_percentage':40,
    'grading_scheme':'percentage','brand_color':'#4f46e5',
    'theme':'aurora','departments':['CSE','ECE','EEE','MECH','CIVIL'],
    'allow_student_requests':True,'risk_alerts':True,
}

class RegisterCollege(BaseModel):
    name:str=Field(min_length=3,max_length=150)
    domain:str=Field(min_length=3,max_length=150)
    admin_name:str=Field(min_length=2,max_length=150)
    admin_email:str=Field(min_length=5,max_length=250)
    admin_password:str=Field(min_length=6,max_length=200)

class PreferencePatch(BaseModel):
    academic_year:str=Field(default='2026-2027',min_length=4,max_length=25)
    timezone:str=Field(default='Asia/Kolkata',min_length=1,max_length=100)
    semester_system:str=Field(default='semester')
    attendance_threshold:int=Field(default=75,ge=0,le=100)
    pass_percentage:int=Field(default=40,ge=0,le=100)
    grading_scheme:str=Field(default='percentage')
    brand_color:str=Field(default='#4f46e5')
    theme:str=Field(default='aurora')
    departments:list[str]=Field(default_factory=lambda:DEFAULTS['departments'][:],max_length=40)
    allow_student_requests:bool=True
    risk_alerts:bool=True


def install_college_routes(app,engine,settings):
    @app.get('/api/colleges/registration-status')
    def registration_status():
        return {'enabled':True,
                'method':'public_college_registration',
                'data_isolation':'college-scoped shared Supabase PostgreSQL database; not separate physical databases'}

    @app.post('/api/colleges/register',status_code=201)
    def register_college(body:RegisterCollege,request:Request):
        domain=body.domain.strip().lower()
        email=body.admin_email.strip().lower()
        if not DOMAIN.fullmatch(domain) or email.rpartition('@')[2]!=domain:
            raise HTTPException(400,'Enter a valid college domain; administrator email must use that domain.')
        if len(set(d.strip().upper() for d in DEFAULTS['departments']))<1:
            raise HTTPException(400,'Invalid department setup.')
        name=body.name.strip()
        with engine.begin() as c:
            if c.execute(select(colleges.c.id).where(colleges.c.domain==domain)).first():
                raise HTTPException(409,'That college domain is already registered.')
            if c.execute(select(accounts.c.id).where(accounts.c.email==email)).first():
                raise HTTPException(409,'That administrator email is already registered.')
            cid=str(uuid.uuid4());aid=str(uuid.uuid4())
            c.execute(insert(colleges).values(id=cid,name=name,domain=domain,created_at=now()))
            c.execute(insert(accounts).values(id=aid,college_id=cid,email=email,
                full_name=body.admin_name.strip(),password_hash=passwords.hash(body.admin_password),
                role='admin',departments=[],student_id=None,active=True))
            c.execute(insert(college_preferences).values(college_id=cid,
                configuration=DEFAULTS.copy(),updated_at=now()))
            audit(c,{'id':aid,'college_id':cid},'college.registered',{'domain':domain})
        return {'ok':True,'college_name':name,'domain':domain,
                'message':'College registered. Sign in as its administrator to configure departments, upload data and create faculty/student accounts.'}

    @app.get('/api/college/preferences')
    def preferences(user=Depends(identity)):
        with engine.connect() as c:
            row=c.execute(select(college_preferences.c.configuration).where(college_preferences.c.college_id==user['college_id'])).scalar_one_or_none()
        return {'preferences':{**DEFAULTS,**(row or {})},
                'isolation':'All records are scoped to this college ID within one Supabase PostgreSQL database.'}

    @app.put('/api/college/preferences')
    def save_preferences(body:PreferencePatch,user=Depends(identity)):
        roles(user,'admin')
        cfg=body.model_dump()
        try:ZoneInfo(cfg['timezone'])
        except (ZoneInfoNotFoundError,ValueError):raise HTTPException(400,'Select a valid IANA time zone, e.g. Asia/Kolkata.')
        if cfg['semester_system'] not in ('semester','trimester','annual'):
            raise HTTPException(400,'Unknown academic year structure.')
        if cfg['grading_scheme'] not in ('percentage','cgpa','letter'):
            raise HTTPException(400,'Unknown grading scheme.')
        if cfg['theme'] not in ('aurora','light','dark'):
            raise HTTPException(400,'Unknown theme.')
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}',cfg['brand_color']):
            raise HTTPException(400,'Brand color must be a six-character hex value.')
        if not cfg['departments'] or any(not d.strip() or len(d)>30 for d in cfg['departments']):
            raise HTTPException(400,'Provide at least one valid department.')
        cfg['departments']=list(dict.fromkeys(d.strip().upper() for d in cfg['departments']))
        with engine.begin() as c:
            exists=c.execute(select(college_preferences.c.college_id).where(college_preferences.c.college_id==user['college_id'])).first()
            if exists:
                c.execute(update(college_preferences).where(college_preferences.c.college_id==user['college_id']).values(configuration=cfg,updated_at=now()))
            else:
                c.execute(insert(college_preferences).values(college_id=user['college_id'],configuration=cfg,updated_at=now()))
            audit(c,user,'college.preferences.changed',{'keys':list(cfg)})
        return {'ok':True,'preferences':cfg}
