"""Multi-college API. Every protected database read/write is tenant scoped."""
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit
import os, re, uuid, logging
from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, insert, update, delete, func, text
from sqlalchemy.exc import SQLAlchemyError,IntegrityError
from .settings import Settings,ROOT
from .tenant_db import (metadata,colleges,accounts,sessions,roster,subjects,entries,observations,
                        actions,connections,logs,now,engine_for)
from .tenant_auth import identity,login,passwords,public,digest,roles,COOKIE
from .tenant_data import visible_ids,authorized_student,list_roster,academic,sync_records,audit
from .tenant_connectors import validate_config,discover,fetch,encrypt,decrypt,ConnectorError
from .repository import clean
from .scoring import simulate,component_breakdown,CONFIG
from .validation import InvalidSnapshot

logger=logging.getLogger('pulseiq.database')

EMAIL_RE=re.compile(r'^[^\s@]+@([a-z0-9.-]+)$',re.I)
STATUS=('Planned','In progress','Reviewed','Closed')

def uid():return str(uuid.uuid4())
def email_domain(email):
    m=EMAIL_RE.fullmatch(email.strip().lower());return m.group(1) if m else ''
def permitted_domain(email,domain):return email_domain(email)==domain

class LoginData(BaseModel):
    email:str=Field(min_length=3,max_length=250)
    password:str=Field(min_length=1,max_length=200)
class AccountData(BaseModel):
    email:str=Field(min_length=3,max_length=250)
    full_name:str=Field(min_length=1,max_length=150)
    password:str=Field(min_length=6,max_length=200)
    role:str
    departments:list[str]=Field(default_factory=list)
    student_id:str|None=None
class SupabaseImportData(BaseModel):
    faculty_password: str | None = Field(default=None, min_length=6, max_length=200)
    student_password: str | None = Field(default=None, min_length=6, max_length=200)

class StudentData(BaseModel):
    student_id:str=Field(min_length=1,max_length=100)
    full_name:str=Field(min_length=1,max_length=150)
    email:str|None=None
    department:str=Field(min_length=1,max_length=100)
    semester:int=Field(ge=1,le=12)
    section:str=Field(default='A',min_length=1,max_length=50)
class AssignmentData(BaseModel):
    faculty_id:str
    department:str=Field(min_length=1,max_length=100)
    semester:int=Field(ge=1,le=12)
    section:str=Field(min_length=1,max_length=50)
    subject:str=Field(min_length=1,max_length=150)
class EntryData(BaseModel):
    student_id:str
    assignment_id:str
    kind:str
    period_end:date
    attended:int|None=None
    held:int|None=None
    marks_pct:float|None=None
    status:str='draft'
class ActionData(BaseModel):
    student_id:str
    owner:str=Field(min_length=1,max_length=150)
    action:str=Field(min_length=1,max_length=2000)
    due_date:date
    note:str=Field(default='',max_length=2000)
class ActionUpdate(BaseModel):
    owner:str=Field(min_length=1,max_length=150)
    action:str=Field(min_length=1,max_length=2000)
    due_date:date
    status:str
    note:str=Field(default='',max_length=2000)
    version:int=Field(ge=1)
class SourceData(BaseModel):
    name:str=Field(min_length=1,max_length=150)
    kind:str
    details:dict
    mapping:dict
class MappingData(BaseModel):
    mapping:dict
class Scenario(BaseModel):
    changes:dict[str,float]

def create_app(settings=None,engine=None):
    settings=settings or Settings.from_env()
    engine=engine or engine_for(settings.database_url)

    @asynccontextmanager
    async def lifecycle(app):
        metadata.create_all(engine)
        # Browser-facing Supabase API roles must never read private campus tables.
        with engine.begin() as c:
            if c.dialect.name=='postgresql':
                for table in metadata.sorted_tables:
                    c.execute(text(f'ALTER TABLE public."{table.name}" ENABLE ROW LEVEL SECURITY'))
                    for role in ('anon','authenticated'):
                        if c.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'),{'role':role}).first():
                            c.execute(text(f'REVOKE ALL ON public."{table.name}" FROM {role}'))
        with engine.begin() as c:
            if c.dialect.name=='postgresql':c.execute(text('SELECT pg_advisory_xact_lock(763928452)'))
            college_name=os.environ.get('BOOTSTRAP_COLLEGE_NAME','Demo College' if settings.environment=='test' and settings.admin_password else '').strip()
            admin_email=os.environ.get('BOOTSTRAP_ADMIN_EMAIL','admin@demo.edu' if settings.environment=='test' and settings.admin_password else '').strip().lower()
            domain=os.environ.get('BOOTSTRAP_COLLEGE_DOMAIN',email_domain(admin_email)).strip().lower()
            if c.execute(select(func.count()).select_from(colleges)).scalar_one()==0:
                if not college_name and not admin_email and not os.environ.get('BOOTSTRAP_COLLEGE_DOMAIN','').strip() and not settings.admin_password:
                    pass  # Allow initial onboarding through public college registration.
                else:
                    if not college_name or not admin_email or not domain or not permitted_domain(admin_email,domain) or len(settings.admin_password)<6:
                        raise RuntimeError('Set BOOTSTRAP_COLLEGE_NAME, BOOTSTRAP_COLLEGE_DOMAIN, BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD (6+ characters), or leave all bootstrap values unset for self-service registration.')
                    cid=uid();c.execute(insert(colleges).values(id=cid,name=college_name,domain=domain,created_at=now()))
                    c.execute(insert(accounts).values(id=uid(),college_id=cid,email=admin_email,full_name='College Administrator',password_hash=passwords.hash(settings.admin_password),role='admin',departments=[],student_id=None,active=True))
        if os.environ.get('IMPORT_LEGACY_V2','false').lower()=='true':
            from sqlalchemy import inspect
            if inspect(engine).has_table('students'):
                from .repository import records_from_database
                from .tenant_data import sync_records
                with engine.connect() as c:
                    first=c.execute(select(colleges.c.id).order_by(colleges.c.created_at).limit(1)).scalar_one()
                    total=c.execute(select(func.count()).select_from(roster).where(roster.c.college_id==first)).scalar_one()
                if total==0:
                    old_records,_=records_from_database(engine)
                    if old_records['students']:
                        sync_records(engine,{'id':None,'college_id':first},old_records,'legacy PULSEIQ v2 snapshot')
                        # Preserve v2 interventions for roster identities that were copied.
                        from .db import interventions as old_actions
                        with engine.begin() as c:
                            admin_id=c.execute(select(accounts.c.id).where(accounts.c.college_id==first,accounts.c.role=='admin').limit(1)).scalar_one()
                            ids={r['student_id']:r['id'] for r in c.execute(select(roster.c.student_id,roster.c.id).where(roster.c.college_id==first)).mappings()}
                            for a in c.execute(select(old_actions)).mappings():
                                if a['student_id'] in ids:
                                    c.execute(insert(actions).values(id=uid(),college_id=first,roster_id=ids[a['student_id']],owner=a['owner_alias'],action=a['action'],status=a['status'],due_date=a['due_date'],note=a['review_note'],version=a['version'],updated_by=admin_id,updated_at=a['updated_at']))
        if settings.seed_demo:
            from .seed import generate
            from .tenant_data import sync_records
            with engine.connect() as c:
                college=c.execute(select(colleges.c.id).order_by(colleges.c.created_at).limit(1)).scalar_one()
                total=c.execute(select(func.count()).select_from(roster).where(roster.c.college_id==college)).scalar_one()
            if total==0:
                demo=generate(settings.demo_students)
                for s in demo['students']:
                    s['full_name']='Demo Student '+s['student_id'][-4:]
                    s['section']='A' if int(s['student_id'][-4:])%2 else 'B'
                sync_records(engine,{'id':None,'college_id':college},demo,'fictional demo (not real student data)')
        yield
        engine.dispose()

    app=FastAPI(title='PULSEIQ Campus Platform',version='3.0.0',lifespan=lifecycle,
        docs_url='/api/docs' if settings.environment=='test' or os.environ.get('ENABLE_API_DOCS')=='true' else None,
        openapi_url='/api/openapi.json' if settings.environment=='test' or os.environ.get('ENABLE_API_DOCS')=='true' else None,
        redoc_url=None)
    app.state.engine=engine;app.state.settings=settings
    from .college_setup import install_college_routes
    from .learning import install_learning_routes
    install_college_routes(app,engine,settings)
    install_learning_routes(app,engine)
    from .campus_pages import routes as install_revised_pages
    install_revised_pages(app,engine)

    from .challenge import install as install_challenge
    install_challenge(app,engine)

    @app.middleware('http')
    async def security(request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin'):
            if urlsplit(request.headers['origin']).netloc!=request.headers.get('host'):
                return JSONResponse({'detail':'Cross-origin changes are not allowed.'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response

    @app.exception_handler(SQLAlchemyError)
    async def db_fail(request,exc):
        # Render logs need an actionable SQLSTATE/constraint without exposing student
        # records, connection strings, or SQL parameter values in public API errors.
        original=getattr(exc,'orig',None)
        diag=getattr(original,'diag',None)
        logger.error('Database request failed: endpoint=%s exception=%s sqlstate=%s constraint=%s',
                     request.url.path,type(exc).__name__,
                     getattr(original,'sqlstate',None),
                     getattr(diag,'constraint_name',None))
        return JSONResponse({'detail':'Database operation failed. Check Render logs for SQLSTATE and verify Supabase tables and constraints.'},status_code=503)

    @app.get('/health')
    def health():
        with engine.connect() as c:c.execute(text('SELECT 1'))
        return {'status':'ok','version':'3.0.0'}

    @app.get('/api/colleges/resolve')
    def resolve(email:str=Query(min_length=3,max_length=250)):
        domain=email_domain(email)
        with engine.connect() as c:
            name=c.execute(select(colleges.c.name).where(colleges.c.domain==domain)).scalar_one_or_none()
        return {'recognized':bool(name),'college_name':name}

    @app.post('/api/auth/login')
    def sign_in(body:LoginData,request:Request,response:Response):
        token,result=login(engine,settings,body.email,body.password,request.client.host if request.client else 'unknown')
        response.set_cookie(COOKIE,token,max_age=28800,httponly=True,secure=settings.cookie_secure,samesite='strict',path='/')
        return result

    @app.get('/api/auth/me')
    def me(user=Depends(identity)):
        return {'user':{k:v for k,v in user.items() if k!='csrf_token'},'csrf_token':user['csrf_token']}

    @app.post('/api/auth/logout')
    def sign_out(request:Request,response:Response,user=Depends(identity)):
        with engine.begin() as c:c.execute(delete(sessions).where(sessions.c.token_hash==digest(request.cookies.get(COOKIE,''),settings.app_secret)))
        response.delete_cookie(COOKIE,path='/',secure=settings.cookie_secure,samesite='strict')
        return {'ok':True}

    @app.get('/api/college')
    def college(user=Depends(identity)):
        with engine.connect() as c:
            c_row=c.execute(select(colleges).where(colleges.c.id==user['college_id'])).mappings().first()
        return {'name':c_row['name'],'domain':c_row['domain'],'user':user}

    @app.get('/api/students')
    def get_students(user=Depends(identity)):
        return {'items':list_roster(engine,user)}

    @app.get('/api/analytics')
    def analytics(period:str|None=None,department:str|None=None,semester:int|None=None,stale_days:int=Query(365,ge=0,le=3650),user=Depends(identity)):
        rows,periods,selected=academic(engine,user,period,stale_days)
        if department:rows=[r for r in rows if r['department']==department]
        if semester:rows=[r for r in rows if r['semester']==semester]
        return {'items':[{'student_id':r['student_id'],'full_name':r['full_name'],'department':r['department'],'semester':r['semester'],'section':r['section'],'overall_score':r['overall_score'],'score_status':r['score_status'],'academic_flag':r['academic_flag'],'placement_flag':r['placement_flag'],'coverage':r['coverage'],'segments':r['segments'],'attendance_pct':round(100*r['classes_attended']/r['classes_held'],1) if r.get('classes_held') else None,'marks_pct':r.get('marks_pct')} for r in rows],
                'periods':periods,'period':selected,'total':len(rows),'support_needed':sum(r['academic_flag']=='Support needed' or r['placement_flag']=='Support needed' for r in rows),'scoring':CONFIG}

    @app.get('/api/students/{student_id}')
    def student_profile(student_id:str,period:str|None=None,user=Depends(identity)):
        with engine.connect() as c:authorized_student(c,user,student_id)
        rows,periods,selected=academic(engine,user,period)
        match=next((r for r in rows if r['student_id']==student_id),None)
        if not match:raise HTTPException(404,'Student not found.')
        try:components=clean(component_breakdown(match).to_dict('records'))
        except Exception:components=[]
        with engine.connect() as c:
            item=authorized_student(c,user,student_id)
            visible_actions=c.execute(select(actions).where(actions.c.college_id==user['college_id'],actions.c.roster_id==item['id']).order_by(actions.c.due_date)).mappings().all()
            visible_entries=c.execute(select(entries,subjects.c.subject).join(subjects,entries.c.assignment_id==subjects.c.id).where(entries.c.college_id==user['college_id'],entries.c.roster_id==item['id'],entries.c.status=='published')).mappings().all()
        return {'record':match,'components':components,'periods':periods,'period':selected,'actions':clean([dict(r) for r in visible_actions]),'faculty_records':clean([dict(r) for r in visible_entries])}

    @app.post('/api/students/{student_id}/scenario')
    def scenario(student_id:str,body:Scenario,user=Depends(identity)):
        with engine.connect() as c:authorized_student(c,user,student_id)
        rows,_,_=academic(engine,user)
        record=next((r for r in rows if r['student_id']==student_id),None)
        if record is None:raise HTTPException(404,'Student not found.')
        allowed={'marks_pct':'academic','classes_attended':'attendance','assignments_completed':'lms','coding_pct':'placement','aptitude_pct':'placement','interview_pct':'placement'}
        if any(k not in allowed or record.get(k) is None or not record.get(allowed[k]+'__fresh') for k in body.changes):
            raise HTTPException(400,'Only observed, fresh fields may be simulated.')
        try:result=simulate(record,body.changes)
        except (ValueError,TypeError) as exc:raise HTTPException(400,str(exc))
        return {'scenario':clean(result),'notice':'What-if only; student records were not changed.'}

    @app.get('/api/admin/accounts')
    def list_accounts(user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:
            r=c.execute(select(accounts).where(accounts.c.college_id==user['college_id']).order_by(accounts.c.role,accounts.c.email)).mappings().all()
        return {'items':[{k:x[k] for k in ('id','email','full_name','role','departments','student_id','active')} for x in r]}

    @app.post('/api/admin/accounts',status_code=201)
    def add_account(body:AccountData,user=Depends(identity)):
        roles(user,'admin')
        if body.role not in ('admin','faculty','student'):raise HTTPException(400,'Role must be admin, faculty or student.')
        email=body.email.strip().lower()
        with engine.begin() as c:
            domain=c.execute(select(colleges.c.domain).where(colleges.c.id==user['college_id'])).scalar_one()
            if not permitted_domain(email,domain):raise HTTPException(400,f'Account email must use @{domain}.')
            if body.role=='student':
                if not body.student_id:raise HTTPException(400,'Student account requires a student ID.')
                match=c.execute(select(roster).where(roster.c.college_id==user['college_id'],roster.c.student_id==body.student_id,roster.c.active==True)).mappings().first()
                if not match:raise HTTPException(400,'Add this student to the college roster first.')
                if c.execute(select(accounts.c.id).where(accounts.c.college_id==user['college_id'],accounts.c.student_id==body.student_id,accounts.c.role=='student')).first():raise HTTPException(409,'Student already has an account.')
            elif body.student_id:raise HTTPException(400,'Only students may have a linked student ID.')
            if c.execute(select(accounts.c.id).where(accounts.c.email==email)).first():raise HTTPException(409,'Email already registered.')
            record=dict(id=uid(),college_id=user['college_id'],email=email,full_name=body.full_name.strip(),password_hash=passwords.hash(body.password),role=body.role,departments=body.departments if body.role=='faculty' else [],student_id=body.student_id if body.role=='student' else None,active=True)
            c.execute(insert(accounts).values(**record));audit(c,user,'account.created',{'role':body.role,'email':email})
        return {k:record[k] for k in ('id','email','full_name','role','student_id')}

    @app.patch('/api/admin/accounts/{account_id}/toggle')
    def toggle_account(account_id:str,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            target=c.execute(select(accounts).where(accounts.c.id==account_id,accounts.c.college_id==user['college_id'])).mappings().first()
            if not target:raise HTTPException(404,'User not found.')
            if target['id']==user['id']:raise HTTPException(400,'Cannot disable your own account.')
            c.execute(update(accounts).where(accounts.c.id==account_id,accounts.c.college_id==user['college_id']).values(active=not target['active']))
            if target['active']:c.execute(delete(sessions).where(sessions.c.user_id==account_id))
            audit(c,user,'account.toggled',{'account_id':account_id,'active':not target['active']})
        return {'active':not target['active']}

    def _supabase_source(c, college):
        """Find the authorized source college by its configured domain; never guess a tenant."""
        from sqlalchemy import inspect
        if not {'students', 'faculty', 'colleges'}.issubset(
            set(inspect(c).get_table_names(schema='public'))
        ):
            raise HTTPException(400, 'Source tables public.colleges, public.students and public.faculty are missing.')
        rows=c.execute(text("""
            SELECT id, college_code, college_name, email_domain
            FROM public.colleges
            WHERE lower(trim(email_domain)) = :domain
        """), {'domain':college['domain'].strip().lower()}).mappings().all()
        if len(rows)!=1:
            raise HTTPException(400,
                'College domain mismatch: PULSEIQ uses '+college['domain']+
                '. Update public.colleges.email_domain to this value before importing.')
        return rows[0]

    @app.get('/api/admin/import-supabase/status')
    def import_supabase_status(user=Depends(identity)):
        """Read-only diagnostics for admin; no passwords or arbitrary college records."""
        roles(user,'admin')
        from sqlalchemy import inspect
        with engine.connect() as c:
            college=c.execute(select(colleges).where(colleges.c.id==user['college_id'])).mappings().one()
            tables=set(inspect(c).get_table_names(schema='public'))
            result={'application_domain':college['domain'],
                    'tables_present':all(x in tables for x in ('colleges','students','faculty')),
                    'matching_source':False,
                    'source_students':0,'source_faculty':0,
                    'roster_students':c.execute(select(func.count()).select_from(roster).where(roster.c.college_id==user['college_id'])).scalar_one(),
                    'student_accounts':c.execute(select(func.count()).select_from(accounts).where(accounts.c.college_id==user['college_id'],accounts.c.role=='student')).scalar_one(),
                    'faculty_accounts':c.execute(select(func.count()).select_from(accounts).where(accounts.c.college_id==user['college_id'],accounts.c.role=='faculty')).scalar_one(),
                    'faculty_assignments':c.execute(select(func.count()).select_from(subjects).where(subjects.c.college_id==user['college_id'])).scalar_one()}
            if result['tables_present']:
                matched=c.execute(text("""SELECT id FROM public.colleges WHERE lower(trim(email_domain))=:domain"""),
                    {'domain':college['domain'].lower().strip()}).scalars().all()
                if len(matched)==1:
                    result['matching_source']=True
                    result['source_students']=c.execute(text('SELECT count(*) FROM public.students WHERE college_id=:id'),{'id':matched[0]}).scalar_one()
                    result['source_faculty']=c.execute(text('SELECT count(*) FROM public.faculty WHERE college_id=:id'),{'id':matched[0]}).scalar_one()
        return result

    @app.post('/api/admin/import-supabase')
    def import_supabase(body:SupabaseImportData,user=Depends(identity)):
        """Idempotent import of a source college into tenant-scoped roster and accounts.

        A student/faculty email need not use the institute domain: demo data may
        have an older mail domain. The SOURCE college must match, and accounts
        never cross tenant boundaries or overwrite existing passwords.
        """
        roles(user,'admin')
        stats={'students_created':0,'students_updated':0,'faculty_accounts_created':0,
               'student_accounts_created':0,'assignments_created':0,'skipped_faculty':0,
               'skipped_student_accounts':0}
        with engine.begin() as c:
            college=c.execute(select(colleges).where(colleges.c.id==user['college_id'])).mappings().one()
            source=_supabase_source(c,college)
            students=c.execute(text('SELECT roll_number, full_name, email, department, semester, section FROM public.students WHERE college_id=:cid ORDER BY roll_number'),{'cid':source['id']}).mappings().all()
            faculty=c.execute(text('SELECT * FROM public.faculty WHERE college_id=:cid ORDER BY employee_id'),{'cid':source['id']}).mappings().all()
            known={r['student_id']:r['id'] for r in c.execute(select(roster.c.student_id,roster.c.id).where(roster.c.college_id==college['id'])).mappings()}
            # Globally unique email constraint: never insert an address owned by another campus.
            all_accounts={r['email'].lower():dict(r) for r in c.execute(select(accounts)).mappings()}
            linked={r['student_id'] for r in all_accounts.values() if r['college_id']==college['id'] and r['role']=='student' and r['student_id']}
            fp_hash=passwords.hash(body.faculty_password) if body.faculty_password else None
            sp_hash=passwords.hash(body.student_password) if body.student_password else None
            for item in students:
                sid=str(item['roll_number']).strip()
                if not sid:raise HTTPException(400,'A source student has a blank roll_number.')
                values=dict(full_name=str(item['full_name'])[:150],email=str(item['email']).strip().lower() if item['email'] else None,
                    department=str(item['department'] or 'Unassigned')[:100],semester=int(item['semester'] or 1),section=str(item['section'] or 'A')[:50],active=True)
                if sid in known:
                    c.execute(update(roster).where(roster.c.id==known[sid],roster.c.college_id==college['id']).values(**values));stats['students_updated']+=1
                else:
                    rid=uid();c.execute(insert(roster).values(id=rid,college_id=college['id'],student_id=sid,**values));known[sid]=rid;stats['students_created']+=1
                email=values['email']
                # Valid source-row membership is the authorization, not email suffix.
                if sp_hash and email and EMAIL_RE.fullmatch(email) and email not in all_accounts and sid not in linked:
                    record=dict(id=uid(),college_id=college['id'],email=email,full_name=values['full_name'],password_hash=sp_hash,role='student',departments=[],student_id=sid,active=True)
                    c.execute(insert(accounts).values(**record));all_accounts[email]=record;linked.add(sid);stats['student_accounts_created']+=1
                elif sp_hash and sid not in linked:stats['skipped_student_accounts']+=1
            for item in faculty:
                email=str(item['email'] or '').strip().lower()
                if not email or not EMAIL_RE.fullmatch(email):
                    stats['skipped_faculty']+=1;continue
                department=str(item['department'] or 'Unassigned')[:100]
                existing=all_accounts.get(email)
                if existing and (existing['college_id']!=college['id'] or existing['role']!='faculty'):
                    stats['skipped_faculty']+=1;continue
                if not existing and fp_hash:
                    record=dict(id=uid(),college_id=college['id'],email=email,full_name=str(item['full_name'])[:150],password_hash=fp_hash,role='faculty',departments=[department],student_id=None,active=True)
                    c.execute(insert(accounts).values(**record));all_accounts[email]=record;existing=record;stats['faculty_accounts_created']+=1
                if not existing:stats['skipped_faculty']+=1;continue
                subject=str(item.get('subject_name') or item.get('subject_code') or '').strip()
                semester=item.get('assigned_semester');section=item.get('assigned_section')
                if not subject or not semester or not section:continue
                values=dict(college_id=college['id'],faculty_id=existing['id'],department=department,semester=int(semester),section=str(section),subject=subject[:150])
                conditions=[subjects.c[k]==v for k,v in values.items()]
                if not c.execute(select(subjects.c.id).where(*conditions)).first():
                    c.execute(insert(subjects).values(id=uid(),**values));stats['assignments_created']+=1
            audit(c,user,'supabase.demo.import',stats)
        return stats

    @app.post('/api/admin/students')
    def upsert_student(body:StudentData,user=Depends(identity)):
        roles(user,'admin')
        if body.email and not EMAIL_RE.fullmatch(body.email):raise HTTPException(400,'Provide a valid email.')
        with engine.begin() as c:
            old=c.execute(select(roster.c.id).where(roster.c.college_id==user['college_id'],roster.c.student_id==body.student_id)).scalar_one_or_none()
            data=body.model_dump();data.update(email=body.email.strip().lower() if body.email else None,active=True)
            if old:c.execute(update(roster).where(roster.c.id==old).values(**data))
            else:c.execute(insert(roster).values(id=uid(),college_id=user['college_id'],**data))
            audit(c,user,'roster.saved',{'student_id':body.student_id})
        return {'ok':True,'student_id':body.student_id}

    @app.post('/api/admin/students/bulk')
    def bulk_students(items:list[StudentData],user=Depends(identity)):
        """Bulk add/upsert JSON roster. Entire batch is atomic and tenant scoped."""
        roles(user,'admin')
        if not items or len(items)>5000:raise HTTPException(400,'Provide between 1 and 5,000 student records.')
        identifiers=[x.student_id for x in items]
        if len(set(identifiers))!=len(identifiers):raise HTTPException(400,'Duplicate student IDs in the import.')
        if any(x.email and not EMAIL_RE.fullmatch(x.email) for x in items):raise HTTPException(400,'Invalid email in imported roster.')
        with engine.begin() as c:
            existing={r['student_id']:r['id'] for r in c.execute(select(roster.c.id,roster.c.student_id).where(roster.c.college_id==user['college_id'])).mappings()}
            for student in items:
                data=student.model_dump();data.update(email=student.email.strip().lower() if student.email else None,active=True)
                if student.student_id in existing:
                    c.execute(update(roster).where(roster.c.id==existing[student.student_id],roster.c.college_id==user['college_id']).values(**data))
                else:c.execute(insert(roster).values(id=uid(),college_id=user['college_id'],**data))
            audit(c,user,'roster.bulk',{'count':len(items)})
        return {'ok':True,'count':len(items)}

    @app.get('/api/assignments')
    def list_assignments(user=Depends(identity)):
        roles(user,'admin','faculty')
        with engine.connect() as c:
            q=select(subjects,accounts.c.full_name.label('faculty_name'),accounts.c.email.label('faculty_email')).join(accounts,accounts.c.id==subjects.c.faculty_id).where(subjects.c.college_id==user['college_id'])
            if user['role']=='faculty':q=q.where(subjects.c.faculty_id==user['id'])
            result=[dict(r) for r in c.execute(q.order_by(subjects.c.department,subjects.c.subject)).mappings()]
        return {'items':clean(result)}

    @app.post('/api/admin/assignments',status_code=201)
    def add_assignment(body:AssignmentData,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            target=c.execute(select(accounts).where(accounts.c.id==body.faculty_id,accounts.c.college_id==user['college_id'],accounts.c.role=='faculty',accounts.c.active==True)).mappings().first()
            if not target:raise HTTPException(400,'Choose a faculty member from your own college.')
            row=dict(id=uid(),college_id=user['college_id'],**body.model_dump())
            if c.execute(select(subjects.c.id).where(subjects.c.college_id==user['college_id'],subjects.c.faculty_id==body.faculty_id,subjects.c.department==body.department,subjects.c.semester==body.semester,subjects.c.section==body.section,subjects.c.subject==body.subject)).first():raise HTTPException(409,'That assignment already exists.')
            c.execute(insert(subjects).values(**row));audit(c,user,'faculty.assigned',{'faculty_id':body.faculty_id,'subject':body.subject})
        return row

    @app.get('/api/entries')
    def list_entries(user=Depends(identity)):
        roles(user,'admin','faculty')
        with engine.connect() as c:
            q=select(entries,roster.c.student_id,roster.c.full_name,subjects.c.subject).join(roster,entries.c.roster_id==roster.c.id).join(subjects,entries.c.assignment_id==subjects.c.id).where(entries.c.college_id==user['college_id'])
            if user['role']=='faculty':q=q.where(subjects.c.faculty_id==user['id'])
            result=[dict(r) for r in c.execute(q.order_by(entries.c.updated_at.desc()).limit(250)).mappings()]
        return {'items':clean(result)}

    @app.post('/api/entries')
    def save_entry(body:EntryData,user=Depends(identity)):
        roles(user,'faculty')
        if body.kind not in ('marks','attendance') or body.status not in ('draft','published'):
            raise HTTPException(400,'Invalid entry kind or status.')
        if body.period_end>date.today():raise HTTPException(400,'Reporting date cannot be in the future.')
        if body.kind=='attendance' and (body.attended is None or body.held is None or not 0<=body.attended<=body.held):raise HTTPException(400,'Attendance must satisfy 0 <= attended <= held.')
        if body.kind=='marks' and (body.marks_pct is None or not 0<=body.marks_pct<=100):raise HTTPException(400,'Marks percentage must be 0 to 100.')
        with engine.begin() as c:
            r=authorized_student(c,user,body.student_id)
            assignment=c.execute(select(subjects).where(subjects.c.id==body.assignment_id,subjects.c.college_id==user['college_id'])).mappings().first()
            if not assignment or (user['role']=='faculty' and assignment['faculty_id']!=user['id']):raise HTTPException(403,'Not assigned to this subject.')
            if (r['department'],r['semester'],r['section'])!=(assignment['department'],assignment['semester'],assignment['section']):raise HTTPException(400,'Student is not enrolled in this assigned class.')
            old=c.execute(select(entries.c.id).where(entries.c.roster_id==r['id'],entries.c.assignment_id==body.assignment_id,entries.c.kind==body.kind,entries.c.period_end==body.period_end)).scalar_one_or_none()
            values=dict(attended=body.attended if body.kind=='attendance' else None,held=body.held if body.kind=='attendance' else None,marks_pct=body.marks_pct if body.kind=='marks' else None,status=body.status,updated_by=user['id'],updated_at=now())
            if old:c.execute(update(entries).where(entries.c.id==old,entries.c.college_id==user['college_id']).values(**values))
            else:c.execute(insert(entries).values(id=uid(),college_id=user['college_id'],roster_id=r['id'],assignment_id=body.assignment_id,kind=body.kind,period_end=body.period_end,**values))
            audit(c,user,'academic.entry.saved',{'student_id':body.student_id,'kind':body.kind,'status':body.status,'subject':assignment['subject']})
        return {'ok':True,'status':body.status}

    @app.get('/api/actions')
    def list_actions(user=Depends(identity)):
        with engine.connect() as c:
            ids=visible_ids(c,user)
            if not ids:return {'items':[]}
            records=c.execute(select(actions,roster.c.student_id,roster.c.full_name).join(roster,actions.c.roster_id==roster.c.id).where(actions.c.college_id==user['college_id'],actions.c.roster_id.in_(ids)).order_by(actions.c.due_date)).mappings().all()
        return {'items':clean([dict(x) for x in records])}

    @app.post('/api/actions')
    def make_action(body:ActionData,user=Depends(identity)):
        roles(user,'admin','faculty')
        with engine.begin() as c:
            r=authorized_student(c,user,body.student_id)
            item=dict(id=uid(),college_id=user['college_id'],roster_id=r['id'],owner=body.owner,action=body.action,status='Planned',due_date=body.due_date,note=body.note,version=1,updated_by=user['id'],updated_at=now())
            c.execute(insert(actions).values(**item));audit(c,user,'action.created',{'student_id':body.student_id})
        return clean(item)

    @app.patch('/api/actions/{action_id}')
    def edit_action(action_id:str,body:ActionUpdate,user=Depends(identity)):
        roles(user,'admin','faculty')
        if body.status not in STATUS:raise HTTPException(400,'Unknown action status.')
        if body.status in ('Reviewed','Closed') and not body.note.strip():raise HTTPException(400,'Review note required to close or review.')
        with engine.begin() as c:
            old=c.execute(select(actions).where(actions.c.id==action_id,actions.c.college_id==user['college_id'])).mappings().first()
            if not old or old['roster_id'] not in visible_ids(c,user):raise HTTPException(404,'Action not found in your classes.')
            if old['version']!=body.version:raise HTTPException(409,'Action changed. Refresh before editing.')
            result=c.execute(update(actions).where(actions.c.id==action_id,actions.c.college_id==user['college_id'],actions.c.version==body.version).values(**body.model_dump(exclude={'version'}),version=body.version+1,updated_by=user['id'],updated_at=now()))
            if result.rowcount!=1:raise HTTPException(409,'Action changed. Refresh before editing.')
            audit(c,user,'action.updated',{'action_id':action_id,'status':body.status})
        return {'ok':True,'version':body.version+1}

    @app.get('/api/admin/connections')
    def get_connections(user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:rows=c.execute(select(connections).where(connections.c.college_id==user['college_id']).order_by(connections.c.created_at.desc())).mappings().all()
        return {'items':[{'id':x['id'],'name':x['name'],'kind':x['kind'],'mapping':x['mapping'],'created_at':clean(x['created_at']),'configured':True} for x in rows]}

    @app.post('/api/admin/connections')
    def create_connection(body:SourceData,user=Depends(identity)):
        roles(user,'admin')
        try:validate_config(body.kind,body.details,body.mapping)
        except ConnectorError as e:raise HTTPException(400,str(e))
        with engine.begin() as c:
            pk=uid()
            c.execute(insert(connections).values(id=pk,college_id=user['college_id'],name=body.name,kind=body.kind,encrypted_dsn=encrypt(settings.app_secret,body.details),mapping=body.mapping,created_at=now()))
            audit(c,user,'connection.created',{'connection_id':pk,'kind':body.kind})
        return {'id':pk,'name':body.name,'kind':body.kind}

    def get_connection(user,source_id):
        with engine.connect() as c:
            row=c.execute(select(connections).where(connections.c.id==source_id,connections.c.college_id==user['college_id'])).mappings().first()
        if not row:raise HTTPException(404,'Connection not found.')
        return row,decrypt(settings.app_secret,row['encrypted_dsn'])

    @app.get('/api/admin/connections/{source_id}/discover')
    def inspect_connection(source_id:str,user=Depends(identity)):
        roles(user,'admin');source,details=get_connection(user,source_id)
        try:return {'tables':discover(source['kind'],details)}
        except Exception:raise HTTPException(502,'Could not inspect this source. Check credentials, driver, network access and read permissions.')

    @app.put('/api/admin/connections/{source_id}/mapping')
    def update_mapping(source_id:str,body:MappingData,user=Depends(identity)):
        roles(user,'admin');source,details=get_connection(user,source_id)
        try:validate_config(source['kind'],details,body.mapping)
        except ConnectorError as e:raise HTTPException(400,str(e))
        with engine.begin() as c:
            c.execute(update(connections).where(connections.c.id==source_id,connections.c.college_id==user['college_id']).values(mapping=body.mapping))
            audit(c,user,'connection.mapping.saved',{'connection_id':source_id})
        return {'ok':True}

    @app.delete('/api/admin/connections/{source_id}')
    def delete_connection(source_id:str,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            outcome=c.execute(delete(connections).where(connections.c.id==source_id,connections.c.college_id==user['college_id']))
            if outcome.rowcount==0:raise HTTPException(404,'Connection not found.')
            audit(c,user,'connection.deleted',{'connection_id':source_id})
        return {'ok':True}

    @app.get('/api/admin/connections/{source_id}/preview')
    def preview_connection(source_id:str,user=Depends(identity)):
        roles(user,'admin');source,details=get_connection(user,source_id)
        try:
            from .validation import validate_records
            raw=fetch(source['kind'],details,source['mapping'],settings.database_url)
            normalized,warnings=validate_records(raw)
            return {'counts':{k:len(rows) for k,rows in normalized.items()},'sample':{k:clean(rows[:2]) for k,rows in normalized.items()},'warnings':warnings[:20]}
        except InvalidSnapshot as exc:raise HTTPException(400,{'message':'Mapped source validation failed','report':exc.report[:30]})
        except ConnectorError as exc:raise HTTPException(400,str(exc))
        except Exception:raise HTTPException(502,'Could not preview mapped data. Verify mapping and network access.')

    @app.post('/api/admin/connections/{source_id}/sync')
    def sync_connection(source_id:str,user=Depends(identity)):
        roles(user,'admin')
        source,details=get_connection(user,source_id)
        try:
            raw=fetch(source['kind'],details,source['mapping'],settings.database_url)
            return sync_records(engine,user,raw,source['name'])
        except InvalidSnapshot as e:raise HTTPException(400,{'message':'Source validation failed; existing data preserved.','report':e.report[:30]})
        except ConnectorError as e:raise HTTPException(400,str(e))
        except Exception:raise HTTPException(502,'Connection or sync failed. Verify connection, field mapping and institutional network access.')

    @app.get('/api/admin/audit')
    def audit_history(user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:records=c.execute(select(logs).where(logs.c.college_id==user['college_id']).order_by(logs.c.at.desc()).limit(100)).mappings().all()
        return {'items':clean([dict(r) for r in records])}

    # ---- Additional operational modules: announcements, support, timetable ----
    from .tenant_db import announcements as an_table, requests as req_table, timetable as tt_table
    from .tenant_db import ml_examples as ml_examples_table, ml_models as ml_models_table
    from .traditional_ml import FEATURES as ML_FEATURES, train as train_ml, predict as predict_ml

    class AnnouncementInput(BaseModel):
        title:str=Field(min_length=3,max_length=250)
        body:str=Field(min_length=3,max_length=4000)
        audience:str='all'
        department:str|None=None
    class RequestInput(BaseModel):
        subject:str=Field(min_length=3,max_length=200)
        detail:str=Field(min_length=3,max_length=4000)
    class RequestReply(BaseModel):
        status:str
        reply:str=Field(min_length=3,max_length=4000)
    class TimetableInput(BaseModel):
        assignment_id:str
        weekday:int=Field(ge=0,le=6)
        start_time:str=Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
        end_time:str=Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
        room:str=Field(min_length=1,max_length=60)
    class MLExample(BaseModel):
        features:dict[str,float|None]
        outcome:int=Field(ge=0,le=1)
    class MLTrainOptions(BaseModel):
        demo:bool=False

    @app.get('/api/announcements')
    def get_announcements(user=Depends(identity)):
        with engine.connect() as c:
            q=select(an_table).where(an_table.c.college_id==user['college_id'])
            rows=c.execute(q.order_by(an_table.c.created_at.desc()).limit(200)).mappings().all()
            departments=set(user.get('departments') or [])
            if user['role']=='student':
                r=authorized_student(c,user,user['student_id'])
                departments.add(r['department'])
        return {'items':[clean(dict(x)) for x in rows if x['audience']=='all' or user['role']=='admin' or x['audience']==user['role'] or (x['audience']=='department' and x['department'] in departments)]}

    @app.post('/api/announcements',status_code=201)
    def create_announcement(body:AnnouncementInput,user=Depends(identity)):
        roles(user,'admin','faculty')
        if body.audience not in ('all','student','faculty','department'):raise HTTPException(400,'Invalid audience')
        if user['role']=='faculty' and body.audience not in ('student','department'):raise HTTPException(403,'Faculty announcements must target students or departments.')
        if body.audience=='department' and not body.department:raise HTTPException(400,'Select a department.')
        if user['role']=='faculty' and body.department and body.department not in user['departments']:raise HTTPException(403,'Unauthorized department.')
        item=dict(id=uid(),college_id=user['college_id'],author_id=user['id'],**body.model_dump(),created_at=now())
        with engine.begin() as c:c.execute(insert(an_table).values(**item));audit(c,user,'announcement.created',{'id':item['id']})
        return clean(item)

    @app.get('/api/requests')
    def get_support_requests(user=Depends(identity)):
        with engine.connect() as c:
            ids=visible_ids(c,user)
            if not ids:return {'items':[]}
            rows=c.execute(select(req_table,roster.c.student_id,roster.c.full_name).join(roster,req_table.c.roster_id==roster.c.id).where(req_table.c.college_id==user['college_id'],req_table.c.roster_id.in_(ids)).order_by(req_table.c.created_at.desc())).mappings().all()
        return {'items':clean([dict(x) for x in rows])}

    @app.post('/api/requests',status_code=201)
    def create_support_request(body:RequestInput,user=Depends(identity)):
        roles(user,'student')
        with engine.begin() as c:
            r=authorized_student(c,user,user['student_id'])
            item=dict(id=uid(),college_id=user['college_id'],roster_id=r['id'],**body.model_dump(),status='Open',reply='',created_at=now())
            c.execute(insert(req_table).values(**item));audit(c,user,'request.created',{'id':item['id']})
        return clean(item)

    @app.patch('/api/requests/{request_id}')
    def answer_support_request(request_id:str,body:RequestReply,user=Depends(identity)):
        roles(user,'admin','faculty')
        if body.status not in ('In progress','Resolved'):raise HTTPException(400,'Invalid status')
        with engine.begin() as c:
            target=c.execute(select(req_table).where(req_table.c.id==request_id,req_table.c.college_id==user['college_id'])).mappings().first()
            if not target or target['roster_id'] not in visible_ids(c,user):raise HTTPException(404,'Request not found in your assigned classes')
            c.execute(update(req_table).where(req_table.c.id==request_id).values(status=body.status,reply=body.reply))
            audit(c,user,'request.answered',{'id':request_id})
        return {'ok':True}

    @app.get('/api/timetable')
    def get_timetable(user=Depends(identity)):
        with engine.connect() as c:
            q=select(tt_table,subjects.c.subject,subjects.c.department,subjects.c.semester,subjects.c.section,accounts.c.full_name.label('faculty_name')).join(subjects,tt_table.c.assignment_id==subjects.c.id).join(accounts,subjects.c.faculty_id==accounts.c.id).where(tt_table.c.college_id==user['college_id'])
            if user['role']=='faculty':q=q.where(subjects.c.faculty_id==user['id'])
            elif user['role']=='student':
                r=authorized_student(c,user,user['student_id'])
                q=q.where(subjects.c.department==r['department'],subjects.c.semester==r['semester'],subjects.c.section==r['section'])
            result=c.execute(q.order_by(tt_table.c.weekday,tt_table.c.start_time)).mappings().all()
        return {'items':clean([dict(x) for x in result])}

    @app.post('/api/timetable',status_code=201)
    def save_timetable(body:TimetableInput,user=Depends(identity)):
        roles(user,'admin')
        if body.start_time>=body.end_time:raise HTTPException(400,'End time must be later than start time')
        with engine.begin() as c:
            subj=c.execute(select(subjects).where(subjects.c.id==body.assignment_id,subjects.c.college_id==user['college_id'])).mappings().first()
            if not subj:raise HTTPException(403,'Teaching assignment unavailable')
            conflict=c.execute(select(tt_table.c.id).join(subjects,subjects.c.id==tt_table.c.assignment_id).where(tt_table.c.college_id==user['college_id'],tt_table.c.weekday==body.weekday,tt_table.c.start_time<body.end_time,tt_table.c.end_time>body.start_time,((subjects.c.faculty_id==subj['faculty_id'])|((subjects.c.department==subj['department'])&(subjects.c.semester==subj['semester'])&(subjects.c.section==subj['section']))))).first()
            if conflict:raise HTTPException(409,'Overlapping class or faculty time slot')
            item=dict(id=uid(),college_id=user['college_id'],**body.model_dump())
            c.execute(insert(tt_table).values(**item));audit(c,user,'timetable.created',{'assignment_id':body.assignment_id})
        return item

    @app.delete('/api/timetable/{slot_id}')
    def delete_timetable(slot_id:str,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            target=c.execute(select(tt_table.c.id).where(tt_table.c.id==slot_id,tt_table.c.college_id==user['college_id'])).first()
            if not target:raise HTTPException(404,'Timetable slot not found.')
            c.execute(delete(tt_table).where(tt_table.c.id==slot_id,tt_table.c.college_id==user['college_id']))
            audit(c,user,'timetable.removed',{'slot_id':slot_id})
        return {'ok':True}

    @app.get('/api/ml/status')
    def model_status(user=Depends(identity)):
        with engine.connect() as c:
            model=c.execute(select(ml_models_table.c.metadata,ml_models_table.c.trained_at).where(ml_models_table.c.college_id==user['college_id'])).mappings().first()
            n=c.execute(select(func.count()).where(ml_examples_table.c.college_id==user['college_id'])).scalar_one()
        return {'trained':bool(model),'model':clean(dict(model)) if model else None,'labeled_examples':n,'required_examples':40,'features':ML_FEATURES}

    @app.post('/api/admin/ml/examples',status_code=201)
    def add_ml_example(body:MLExample,user=Depends(identity)):
        roles(user,'admin')
        if set(body.features)-set(ML_FEATURES):raise HTTPException(400,'Unknown feature')
        if sum(v is not None for v in body.features.values())<2:raise HTTPException(400,'At least two observed features required')
        for k,v in body.features.items():
            if v is not None and not(0<=v<=(20 if k=='backlog_count' else 100)):raise HTTPException(400,'Invalid feature range')
        with engine.begin() as c:
            c.execute(insert(ml_examples_table).values(id=uid(),college_id=user['college_id'],features=body.features,outcome=body.outcome,created_at=now()))
            audit(c,user,'ml.example.created',{})
        return {'ok':True}

    @app.post('/api/admin/ml/train')
    def train_model(body:MLTrainOptions,user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:
            examples=c.execute(select(ml_examples_table.c.features,ml_examples_table.c.outcome).where(ml_examples_table.c.college_id==user['college_id'])).mappings().all()
        try:blob,meta=train_ml([dict(x) for x in examples],demo=body.demo)
        except ValueError as e:raise HTTPException(400,str(e))
        with engine.begin() as c:
            c.execute(delete(ml_models_table).where(ml_models_table.c.college_id==user['college_id']))
            c.execute(insert(ml_models_table).values(college_id=user['college_id'],artifact=blob,metadata=meta,trained_at=now()))
            audit(c,user,'ml.model.trained',{'source':meta['source'],'examples':meta['total_examples']})
        return {'trained':True,'model':meta}

    @app.get('/api/ml/predictions')
    def ml_predictions(user=Depends(identity)):
        with engine.connect() as c:
            model=c.execute(select(ml_models_table).where(ml_models_table.c.college_id==user['college_id'])).mappings().first()
        if not model:return {'trained':False,'items':[]}
        rows,_,_=academic(engine,user)
        def flt(v):
            if v is None:return None
            try:
                x=float(v)
                return x if __import__('math').isfinite(x) else None
            except (ValueError,TypeError):return None
        records=[]
        for r in rows:
            att=flt(r.get('classes_attended'))
            held=flt(r.get('classes_held'))
            pct=round(att/held*100,1) if att is not None and held and held>0 else None
            lmc=flt(r.get('assignments_completed')); lma=flt(r.get('assignments_assigned'))
            lp=round(lmc/lma*100,1) if lmc is not None and lma and lma>0 else None
            pl=[flt(r.get(k)) for k in ('aptitude_pct','coding_pct','interview_pct')]
            sk=[flt(r.get(k)) for k in ('technical_pct','communication_pct')]
            eng=flt(r.get('activities_completed'));ea=flt(r.get('activities_available'))
            features=dict(marks_pct=flt(r.get('marks_pct')),attendance_pct=pct,lms_pct=lp,placement_pct=sum(pl)/3 if all(p is not None for p in pl) else None,skills_pct=sum(sk)/2 if all(s is not None for s in sk) else None,engagement_pct=eng/ea*100 if eng is not None and ea and ea>0 else None,backlog_count=flt(r.get('backlog_count')))
            records.append(dict(student_id=r['student_id'],full_name=r['full_name'],features=features,observed=sum(v is not None for v in features.values())))
        eligible=[x for x in records if x['observed']>=2]
        p=predict_ml(model['artifact'],[x['features'] for x in eligible])
        return {'trained':True,'model':clean(model['metadata']),'items':[{'student_id':x['student_id'],'full_name':x['full_name'],'risk_probability':q,'observed_features':x['observed']} for x,q in zip(eligible,p)],'excluded_missing_data':len(records)-len(eligible)}

    class ChangePassword(BaseModel):
        current_password:str
        new_password:str=Field(min_length=6,max_length=200)
    class ResetPassword(BaseModel):
        new_password:str=Field(min_length=6,max_length=200)

    @app.post('/api/auth/change-password')
    def change_password(body:ChangePassword,request:Request,user=Depends(identity)):
        with engine.begin() as c:
            account=c.execute(select(accounts).where(accounts.c.id==user['id'],accounts.c.college_id==user['college_id'])).mappings().one()
            if not passwords.verify(body.current_password,account['password_hash']):raise HTTPException(400,'Current password incorrect.')
            if body.current_password==body.new_password:raise HTTPException(400,'Choose a different new password.')
            c.execute(update(accounts).where(accounts.c.id==user['id']).values(password_hash=passwords.hash(body.new_password)))
            keep=digest(request.cookies.get(COOKIE,''),settings.app_secret)
            c.execute(delete(sessions).where(sessions.c.user_id==user['id'],sessions.c.token_hash!=keep))
            audit(c,user,'account.password.changed',{})
        return {'ok':True}

    @app.post('/api/admin/accounts/{account_id}/reset-password')
    def reset_account_password(account_id:str,body:ResetPassword,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            target=c.execute(select(accounts.c.id,accounts.c.email).where(accounts.c.id==account_id,accounts.c.college_id==user['college_id'])).mappings().first()
            if not target:raise HTTPException(404,'Account not found')
            if account_id==user['id']:raise HTTPException(400,'Use change-password for your own account')
            c.execute(update(accounts).where(accounts.c.id==account_id).values(password_hash=passwords.hash(body.new_password)))
            c.execute(delete(sessions).where(sessions.c.user_id==account_id))
            audit(c,user,'account.password.reset',{'account_id':account_id})
        return {'ok':True}

    @app.patch('/api/admin/students/{student_id}/toggle')
    def toggle_student(student_id:str,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            r=c.execute(select(roster).where(roster.c.college_id==user['college_id'],roster.c.student_id==student_id)).mappings().first()
            if not r:raise HTTPException(404,'Student not found')
            c.execute(update(roster).where(roster.c.id==r['id']).values(active=not r['active']))
            audit(c,user,'roster.toggled',{'student_id':student_id,'active':not r['active']})
        return {'ok':True,'active':not r['active']}

    @app.delete('/api/admin/assignments/{assignment_id}')
    def remove_assignment(assignment_id:str,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            item=c.execute(select(subjects).where(subjects.c.id==assignment_id,subjects.c.college_id==user['college_id'])).mappings().first()
            if not item:raise HTTPException(404,'Assignment not found')
            used=c.execute(select(func.count()).where(entries.c.assignment_id==assignment_id)).scalar_one()
            if used:raise HTTPException(409,'Cannot remove an assignment with existing marks or attendance; preserve the historical record.')
            c.execute(delete(tt_table).where(tt_table.c.assignment_id==assignment_id,tt_table.c.college_id==user['college_id']))
            c.execute(delete(subjects).where(subjects.c.id==assignment_id))
            audit(c,user,'faculty.assignment.removed',{'assignment_id':assignment_id})
        return {'ok':True}

    @app.patch('/api/entries/{entry_id}/publish')
    def publish_entry(entry_id:str,user=Depends(identity)):
        roles(user,'admin','faculty')
        with engine.begin() as c:
            row=c.execute(select(entries,subjects.c.faculty_id,roster.c.student_id).join(subjects,subjects.c.id==entries.c.assignment_id).join(roster,roster.c.id==entries.c.roster_id).where(entries.c.id==entry_id,entries.c.college_id==user['college_id'])).mappings().first()
            if not row:raise HTTPException(404,'Entry not found')
            if user['role']=='faculty' and row['faculty_id']!=user['id']:raise HTTPException(403,'Not your teaching assignment')
            c.execute(update(entries).where(entries.c.id==entry_id).values(status='published',updated_by=user['id'],updated_at=now()))
            audit(c,user,'academic.entry.published',{'id':entry_id,'student_id':row['student_id']})
        return {'ok':True}

    dist=ROOT/'frontend'/'dist'
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/{path:path}',include_in_schema=False)
    def web(path:str):
        if path.startswith(('api/','assets/')):raise HTTPException(404,'Not found.')
        if not (dist/'index.html').exists():return JSONResponse({'detail':'Frontend build not found. Build using Dockerfile.'},status_code=503)
        return FileResponse(dist/'index.html')
    return app
