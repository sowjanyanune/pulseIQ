"""Admin/Faculty/Student revised workflows. All queries require college_id.

No fictitious success metrics: a score exists only after faculty-entered marks.
Attendance must be recorded/edited by a faculty member assigned to that class.
"""
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from uuid import uuid4
import base64, binascii, re
from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select,insert,update,delete,func
from .tenant_auth import identity,roles,passwords
from .tenant_data import visible_ids, authorized_student, audit
from .tenant_db import (roster, accounts, subjects, timetable, entries, colleges,
    student_contacts, faculty_presence, class_sessions, class_attendance,
    exam_results, student_achievements, college_preferences, observations, now)
from .repository import clean


def college_local_date(c, college_id: str, at_utc: datetime | None = None) -> tuple[date, str]:
    """Use each college's declared timezone (default India), not Render's UTC clock.

    Accept an aware UTC time for deterministic boundary tests.
    """
    configuration = c.execute(select(college_preferences.c.configuration).where(
        college_preferences.c.college_id == college_id)).scalar_one_or_none() or {}
    tz = configuration.get('timezone', 'Asia/Kolkata')
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        zone = ZoneInfo('Asia/Kolkata')
        tz = 'Asia/Kolkata'
    instant = at_utc.astimezone(zone) if at_utc else datetime.now(zone)
    return instant.date(), tz


def ident():return str(uuid4())

class StudentWithLogin(BaseModel):
    student_id:str=Field(min_length=1,max_length=100)
    full_name:str=Field(min_length=1,max_length=150)
    email:str=Field(min_length=5,max_length=250)
    password:str=Field(min_length=6,max_length=200)
    department:str=Field(min_length=1,max_length=100)
    semester:int=Field(ge=1,le=12)
    section:str=Field(min_length=1,max_length=50)
    phone:str=Field(default='',max_length=30)
    interests:list[str]=Field(default_factory=list,max_length=20)

class StudentUpdate(BaseModel):
    phone:str=Field(default='',max_length=30)
    interests:list[str]=Field(default_factory=list,max_length=20)

class FacultyPresenceInput(BaseModel):
    faculty_id:str
    on_date:date
    present:bool

class AttendanceRow(BaseModel):
    student_id:str
    present:bool

class AttendanceBatch(BaseModel):
    assignment_id:str
    on_date:date
    time_slot:str=Field(min_length=1,max_length=70)
    topic:str=Field(min_length=1,max_length=250)
    items:list[AttendanceRow]=Field(min_length=1,max_length=300)

class MarksRow(BaseModel):
    student_id:str
    marks:float=Field(ge=0)

class MarksBatch(BaseModel):
    assignment_id:str
    exam_name:str=Field(min_length=1,max_length=100)
    exam_date:date
    maximum:float=Field(gt=0,le=1000)
    items:list[MarksRow]=Field(min_length=1,max_length=300)

class AchievementInput(BaseModel):
    kind:str
    title:str=Field(min_length=2,max_length=250)
    description:str=Field(default='',max_length=1000)
    file_name:str|None=None
    mime_type:str|None=None
    base64_document:str|None=None


def assigned(c,user,assignment_id):
    a=c.execute(select(subjects).where(subjects.c.id==assignment_id,subjects.c.college_id==user['college_id'])).mappings().first()
    if not a or (user['role']=='faculty' and a['faculty_id']!=user['id']):
        raise HTTPException(403,'This subject is not assigned to you.')
    return a


def class_roster(c,assignment):
    return c.execute(select(roster).where(roster.c.college_id==assignment['college_id'],
        roster.c.department==assignment['department'],roster.c.semester==assignment['semester'],
        roster.c.section==assignment['section'],roster.c.active==True)
        .order_by(roster.c.student_id)).mappings().all()


def mark_stats(c,cid,student_ids=None,start=None,end=None):
    q=select(exam_results,roster.c.student_id,subjects.c.subject,subjects.c.department,
        subjects.c.section,subjects.c.semester).join(roster,roster.c.id==exam_results.c.roster_id)\
        .join(subjects,subjects.c.id==exam_results.c.assignment_id).where(exam_results.c.college_id==cid)
    if student_ids is not None:
        if not student_ids:return []
        q=q.where(roster.c.id.in_(student_ids))
    if start:q=q.where(exam_results.c.exam_date>=start)
    if end:q=q.where(exam_results.c.exam_date<=end)
    records = [dict(z) for z in c.execute(q.order_by(exam_results.c.exam_date.desc())).mappings()]
    # Older faculty Marks Entry screens persisted percentage marks in pi3_entries.
    # Preserve those *published* assessments when no v4 exam mark for the
    # same student/subject exists; never double-count the same subject.
    existing = {(r['roster_id'], r['assignment_id']) for r in records}
    legacy_q = select(entries.c.roster_id,entries.c.assignment_id,entries.c.marks_pct,
        entries.c.period_end,roster.c.student_id,subjects.c.subject,subjects.c.department,
        subjects.c.section,subjects.c.semester).join(roster,roster.c.id==entries.c.roster_id)\
        .join(subjects,subjects.c.id==entries.c.assignment_id).where(
        entries.c.college_id==cid,entries.c.kind=='marks',
        entries.c.status=='published',entries.c.marks_pct.is_not(None))
    if student_ids is not None:
        legacy_q=legacy_q.where(roster.c.id.in_(student_ids))
    if start:legacy_q=legacy_q.where(entries.c.period_end>=start)
    if end:legacy_q=legacy_q.where(entries.c.period_end<=end)
    for legacy in c.execute(legacy_q).mappings():
        if (legacy['roster_id'],legacy['assignment_id']) in existing:continue
        records.append({'roster_id':legacy['roster_id'],
            'assignment_id':legacy['assignment_id'],
            'student_id':legacy['student_id'],'subject':legacy['subject'],
            'department':legacy['department'],'section':legacy['section'],
            'semester':legacy['semester'],'marks':legacy['marks_pct'],
            'maximum':100.0,'exam_name':'Published previous marks',
            'exam_date':legacy['period_end'],'source':'published_legacy_marks'})
    return records


def attendance_stats(c,cid,student_ids=None,start=None,end=None):
    q=select(class_attendance.c.roster_id,class_attendance.c.present,class_sessions.c.on_date,
        class_sessions.c.time_slot,class_sessions.c.topic,subjects.c.subject,subjects.c.department,
        subjects.c.section,subjects.c.semester,roster.c.student_id)\
        .join(class_sessions,class_attendance.c.session_id==class_sessions.c.id)\
        .join(subjects,class_sessions.c.assignment_id==subjects.c.id)\
        .join(roster,class_attendance.c.roster_id==roster.c.id)\
        .where(class_attendance.c.college_id==cid)
    if student_ids is not None:
        if not student_ids:return []
        q=q.where(class_attendance.c.roster_id.in_(student_ids))
    if start:q=q.where(class_sessions.c.on_date>=start)
    if end:q=q.where(class_sessions.c.on_date<=end)
    return [dict(z) for z in c.execute(q.order_by(class_sessions.c.on_date.desc())).mappings()]


def summarize(scores,pass_percentage=40):
    groups=defaultdict(list)
    for r in scores:groups[r['student_id']].append(100*r['marks']/r['maximum'])
    return {k:round(sum(v)/len(v),2) for k,v in groups.items()}


def routes(app,engine):
    @app.get('/api/v4/college-date')
    def current_college_date(user=Depends(identity)):
        with engine.connect() as c:
            local_day,zone=college_local_date(c,user['college_id'])
        return {'today':local_day.isoformat(),'timezone':zone}

    @app.get('/api/v4/dashboard')
    def dashboard(user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:
            students=c.execute(select(roster.c.department,func.count()).where(roster.c.college_id==user['college_id'],roster.c.active==True).group_by(roster.c.department)).all()
            faculty_rows=c.execute(select(accounts.c.departments).where(accounts.c.college_id==user['college_id'],accounts.c.role=='faculty',accounts.c.active==True)).all()
        faculties=defaultdict(int)
        for f in faculty_rows:
            for dept in (f[0] or ['Unassigned']):faculties[dept]+=1
        return {'students_by_branch':[{'name':str(k),'count':n} for k,n in students],
                'faculty_by_branch':[{'name':k,'count':n} for k,n in sorted(faculties.items())],
                'students_total':sum(n for _,n in students),'faculty_total':len(faculty_rows)}

    @app.get('/api/v4/directory')
    def directory(department:str='',section:str='',q:str='',user=Depends(identity)):
        with engine.connect() as c:
            ids=visible_ids(c,user)
            if not ids:return {'items':[]}
            query=select(roster,student_contacts.c.phone,student_contacts.c.interests)\
                .outerjoin(student_contacts,student_contacts.c.roster_id==roster.c.id)\
                .where(roster.c.college_id==user['college_id'],roster.c.id.in_(ids),roster.c.active==True)
            if department:query=query.where(roster.c.department==department)
            if section:query=query.where(roster.c.section==section)
            if q:query=query.where((roster.c.student_id.ilike('%'+q+'%'))|(roster.c.full_name.ilike('%'+q+'%')))
            rows=c.execute(query.order_by(roster.c.student_id)).mappings().all()
        return {'items':clean([{**dict(r),'interests':r['interests'] or [],'phone':r['phone'] or ''} for r in rows])}

    @app.post('/api/v4/students',status_code=201)
    def create_student(body:StudentWithLogin,user=Depends(identity)):
        roles(user,'admin')
        email=body.email.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(400,'Enter a valid email address.')
        with engine.begin() as c:
            existing=c.execute(select(roster.c.id).where(roster.c.college_id==user['college_id'],roster.c.student_id==body.student_id)).scalar_one_or_none()
            if existing:raise HTTPException(409,'Student roll number already exists in this college.')
            if c.execute(select(accounts.c.id).where(accounts.c.email==email)).first():raise HTTPException(409,'This email already has a login account.')
            rid=ident();aid=ident()
            c.execute(insert(roster).values(id=rid,college_id=user['college_id'],student_id=body.student_id,full_name=body.full_name,email=email,department=body.department,semester=body.semester,section=body.section,active=True))
            c.execute(insert(student_contacts).values(roster_id=rid,college_id=user['college_id'],phone=body.phone,interests=body.interests,updated_at=now()))
            c.execute(insert(accounts).values(id=aid,college_id=user['college_id'],email=email,full_name=body.full_name,password_hash=passwords.hash(body.password),role='student',departments=[],student_id=body.student_id,active=True))
            audit(c,user,'student.created_with_login',{'student_id':body.student_id})
        return {'ok':True,'student_id':body.student_id,'login_email':email}

    @app.get('/api/v4/student/me')
    def my_student(user=Depends(identity)):
        roles(user,'student')
        with engine.connect() as c:
            r=authorized_student(c,user,user['student_id'])
            z=c.execute(select(student_contacts).where(student_contacts.c.roster_id==r['id'])).mappings().first()
        return {'record':clean(dict(r)),'phone':z['phone'] if z else '', 'interests':z['interests'] if z else []}

    @app.put('/api/v4/student/interests')
    def update_interests(body:StudentUpdate,user=Depends(identity)):
        roles(user,'student')
        if any(len(s)>65 for s in body.interests):raise HTTPException(400,'Interest names must be 65 characters or shorter.')
        with engine.begin() as c:
            r=authorized_student(c,user,user['student_id'])
            v={'phone':body.phone,'interests':body.interests,'updated_at':now()}
            existing=c.execute(select(student_contacts.c.roster_id).where(student_contacts.c.roster_id==r['id'])).first()
            if existing:c.execute(update(student_contacts).where(student_contacts.c.roster_id==r['id']).values(**v))
            else:c.execute(insert(student_contacts).values(roster_id=r['id'],college_id=user['college_id'],**v))
            audit(c,user,'student.profile.updated',{'student_id':r['student_id']})
        return {'ok':True}

    @app.get('/api/v4/faculty')
    def faculty_directory(user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:
            people=c.execute(select(accounts.c.id,accounts.c.full_name,accounts.c.email,accounts.c.departments).where(accounts.c.college_id==user['college_id'],accounts.c.role=='faculty')).mappings().all()
            presence=c.execute(select(faculty_presence.c.faculty_id,faculty_presence.c.present,faculty_presence.c.on_date).where(faculty_presence.c.college_id==user['college_id'])).mappings().all()
        d=defaultdict(lambda:[0,0])
        for p in presence:
            d[p['faculty_id']][1]+=1;d[p['faculty_id']][0]+=int(p['present'])
        return {'items':[dict(x)|{'present_days':d[x['id']][0],'total_days':d[x['id']][1]} for x in people]}

    @app.post('/api/v4/faculty/attendance')
    def faculty_attendance(body:FacultyPresenceInput,user=Depends(identity)):
        roles(user,'admin')
        with engine.begin() as c:
            local_day,timezone_name=college_local_date(c,user['college_id'])
            if body.on_date>local_day:raise HTTPException(400,f'Future attendance cannot be recorded. College date: {local_day} ({timezone_name}).')
            valid=c.execute(select(accounts.c.id).where(accounts.c.id==body.faculty_id,accounts.c.college_id==user['college_id'],accounts.c.role=='faculty')).first()
            if not valid:raise HTTPException(404,'Faculty member not found.')
            old=c.execute(select(faculty_presence.c.id).where(faculty_presence.c.faculty_id==body.faculty_id,faculty_presence.c.on_date==body.on_date)).scalar_one_or_none()
            values={'present':body.present,'recorded_by':user['id']}
            if old:c.execute(update(faculty_presence).where(faculty_presence.c.id==old).values(**values))
            else:c.execute(insert(faculty_presence).values(id=ident(),college_id=user['college_id'],faculty_id=body.faculty_id,on_date=body.on_date,**values))
            audit(c,user,'faculty.attendance.saved',{'faculty_id':body.faculty_id})
        return {'ok':True}

    @app.get('/api/v4/class/{assignment_id}/students')
    def assigned_students(assignment_id:str,user=Depends(identity)):
        roles(user,'faculty','admin')
        with engine.connect() as c:
            a=assigned(c,user,assignment_id)
            rows=class_roster(c,a)
        return {'assignment':clean(dict(a)),'items':[{'student_id':r['student_id'],'full_name':r['full_name']} for r in rows]}

    @app.post('/api/v4/attendance/batch')
    def attendance_batch(body:AttendanceBatch,user=Depends(identity)):
        roles(user,'faculty')
        if len({i.student_id for i in body.items})!=len(body.items):raise HTTPException(400,'Duplicate student in attendance list.')
        with engine.begin() as c:
            local_day,timezone_name=college_local_date(c,user['college_id'])
            if body.on_date>local_day:raise HTTPException(400,f'Cannot take future attendance. College date: {local_day} ({timezone_name}).')
            a=assigned(c,user,body.assignment_id)
            members={r['student_id']:r['id'] for r in class_roster(c,a)}
            if set(i.student_id for i in body.items)!=set(members):raise HTTPException(400,'Mark every enrolled student exactly once.')
            existing=c.execute(select(class_sessions).where(class_sessions.c.assignment_id==a['id'],class_sessions.c.on_date==body.on_date,class_sessions.c.time_slot==body.time_slot)).mappings().first()
            if existing:
                sid=existing['id']
                if existing['created_by']!=user['id']:raise HTTPException(403,'Only the faculty who recorded this session may correct it.')
                c.execute(update(class_sessions).where(class_sessions.c.id==sid).values(topic=body.topic))
            else:
                sid=ident();c.execute(insert(class_sessions).values(id=sid,college_id=user['college_id'],assignment_id=a['id'],on_date=body.on_date,time_slot=body.time_slot,topic=body.topic,created_by=user['id']))
            for item in body.items:
                rid=members[item.student_id]
                old=c.execute(select(class_attendance.c.id).where(class_attendance.c.session_id==sid,class_attendance.c.roster_id==rid)).scalar_one_or_none()
                values={'present':item.present,'updated_by':user['id'],'updated_at':now()}
                if old:c.execute(update(class_attendance).where(class_attendance.c.id==old).values(**values))
                else:c.execute(insert(class_attendance).values(id=ident(),college_id=user['college_id'],session_id=sid,roster_id=rid,**values))
            audit(c,user,'faculty.class.attendance',{'assignment_id':a['id'],'date':body.on_date.isoformat(),'slot':body.time_slot,'topic':body.topic})
        return {'ok':True,'session_id':sid,'marked':len(body.items)}

    @app.get('/api/v4/attendance/session')
    def attendance_session(assignment_id:str,on_date:date,time_slot:str,user=Depends(identity)):
        roles(user,'faculty','admin')
        with engine.connect() as c:
            a=assigned(c,user,assignment_id)
            s=c.execute(select(class_sessions).where(class_sessions.c.college_id==user['college_id'],class_sessions.c.assignment_id==a['id'],class_sessions.c.on_date==on_date,class_sessions.c.time_slot==time_slot)).mappings().first()
            if not s:return {'items':[],'topic':''}
            rows=c.execute(select(roster.c.student_id,class_attendance.c.present).join(roster,roster.c.id==class_attendance.c.roster_id).where(class_attendance.c.session_id==s['id'],class_attendance.c.college_id==user['college_id'])).mappings().all()
        return {'items':[dict(r) for r in rows],'topic':s['topic']}

    @app.post('/api/v4/marks/batch')
    def marks_batch(body:MarksBatch,user=Depends(identity)):
        roles(user,'faculty')
        if len({i.student_id for i in body.items})!=len(body.items):raise HTTPException(400,'Duplicate student marks.')
        with engine.begin() as c:
            local_day,timezone_name=college_local_date(c,user['college_id'])
            if body.exam_date>local_day:raise HTTPException(400,f'Cannot enter future exam marks. College date: {local_day} ({timezone_name}).')
            a=assigned(c,user,body.assignment_id)
            members={r['student_id']:r['id'] for r in class_roster(c,a)}
            if any(i.student_id not in members for i in body.items):raise HTTPException(400,'Student is not enrolled in the selected class.')
            if any(i.marks>body.maximum for i in body.items):raise HTTPException(400,'Marks cannot exceed maximum.')
            for item in body.items:
                rid=members[item.student_id]
                old=c.execute(select(exam_results.c.id).where(exam_results.c.assignment_id==a['id'],exam_results.c.roster_id==rid,exam_results.c.exam_name==body.exam_name,exam_results.c.exam_date==body.exam_date)).scalar_one_or_none()
                values=dict(marks=item.marks,maximum=body.maximum,entered_by=user['id'],updated_at=now())
                if old:c.execute(update(exam_results).where(exam_results.c.id==old).values(**values))
                else:c.execute(insert(exam_results).values(id=ident(),college_id=user['college_id'],assignment_id=a['id'],roster_id=rid,exam_name=body.exam_name,exam_date=body.exam_date,**values))
            audit(c,user,'faculty.exam.marks',{'assignment_id':a['id'],'exam_name':body.exam_name,'count':len(body.items)})
        return {'ok':True,'saved':len(body.items)}

    @app.get('/api/v4/marks/exam')
    def exam_marks(assignment_id:str,exam_name:str,exam_date:date,user=Depends(identity)):
        roles(user,'faculty','admin')
        with engine.connect() as c:
            assigned(c,user,assignment_id)
            rows=c.execute(select(roster.c.student_id,exam_results.c.marks,exam_results.c.maximum).join(roster,roster.c.id==exam_results.c.roster_id).where(exam_results.c.college_id==user['college_id'],exam_results.c.assignment_id==assignment_id,exam_results.c.exam_name==exam_name,exam_results.c.exam_date==exam_date)).mappings().all()
        return {'items':[dict(r) for r in rows]}

    @app.get('/api/v4/performance')
    def performance(start:date|None=None,end:date|None=None,user=Depends(identity)):
        if start and end and start>end:raise HTTPException(400,'Start date must come before end date.')
        with engine.connect() as c:
            ids=visible_ids(c,user)
            marks=mark_stats(c,user['college_id'],ids,start,end)
            if user['role']=='student':
                r=authorized_student(c,user,user['student_id'])
                achievements=c.execute(select(student_achievements.c.id,student_achievements.c.title,student_achievements.c.description,student_achievements.c.kind,student_achievements.c.file_name,student_achievements.c.created_at).where(student_achievements.c.roster_id==r['id'],student_achievements.c.college_id==user['college_id']).order_by(student_achievements.c.created_at.desc())).mappings().all()
            else:achievements=[]
        return {'marks':clean(marks),'achievements':clean([dict(x) for x in achievements]),'averages':summarize(marks)}

    @app.get('/api/v4/attendance/report')
    def attendance_report(start:date|None=None,end:date|None=None,user=Depends(identity)):
        if start and end and start>end:raise HTTPException(400,'Invalid date range.')
        with engine.connect() as c:
            ids=visible_ids(c,user)
            records=attendance_stats(c,user['college_id'],ids,start,end)
        d=defaultdict(lambda:[0,0])
        for r in records:
            d[r['student_id']][1]+=1;d[r['student_id']][0]+=int(r['present'])
        return {'items':clean(records),'summary':[{'student_id':sid,'present':nums[0],'total':nums[1],'percentage':round(100*nums[0]/nums[1],2)} for sid,nums in d.items()]}

    @app.get('/api/v4/success')
    def success(user=Depends(identity)):
        with engine.connect() as c:
            ids=visible_ids(c,user)
            marks=mark_stats(c,user['college_id'],ids)
            students=c.execute(select(roster.c.id,roster.c.student_id,roster.c.full_name,roster.c.department,roster.c.section,roster.c.semester,student_contacts.c.interests).outerjoin(student_contacts,student_contacts.c.roster_id==roster.c.id).where(roster.c.college_id==user['college_id'],roster.c.id.in_(ids))).mappings().all() if ids else []
            achievements=c.execute(select(student_achievements.c.roster_id,student_achievements.c.kind,student_achievements.c.title).where(student_achievements.c.college_id==user['college_id'],student_achievements.c.roster_id.in_(ids))).mappings().all() if ids else []
            recorded_backlogs=c.execute(select(observations.c.roster_id,observations.c.period_end,observations.c.payload,observations.c.source_name).where(observations.c.college_id==user['college_id'],observations.c.kind=='academic',observations.c.roster_id.in_(ids)).order_by(observations.c.period_end.desc())).mappings().all() if ids else []
        av=summarize(marks)
        act=defaultdict(list)
        for a in achievements:act[a['roster_id']].append({'kind':a['kind'],'title':a['title']})
        byid=defaultdict(list)
        for r in marks:byid[r['student_id']].append(r)
        backlogs={}
        for o in recorded_backlogs:
            if o['roster_id'] not in backlogs and 'synthetic' not in str(o['source_name']).lower():
                v=(o['payload'] or {}).get('backlog_count')
                if isinstance(v,int) and v>=0:backlogs[o['roster_id']]=v
        results=[]
        for s in students:
            bysubject=defaultdict(list)
            for mark in byid[s['student_id']]:bysubject[mark['subject']].append(round(100*mark['marks']/mark['maximum'],1))
            strong=[{'subject':subject,'percentage':round(sum(vals)/len(vals),1)} for subject,vals in bysubject.items() if sum(vals)/len(vals)>=70]
            strong.sort(key=lambda v:v['percentage'],reverse=True)
            results.append({'student_id':s['student_id'],'full_name':s['full_name'],'department':s['department'],'section':s['section'],'semester':s['semester'],
                'success_rate':av.get(s['student_id']),'recorded_backlogs':backlogs.get(s['id']),'strong_subjects':strong,'exam_count':len(byid[s['student_id']]),'interests':s['interests'] or [],'achievements':act[s['id']],
                'weak_subjects':sorted([{'subject':r['subject'],'exam':r['exam_name'],'percentage':round(100*r['marks']/r['maximum'],1)} for r in byid[s['student_id']] if 100*r['marks']/r['maximum']<70],key=lambda x:x['percentage'])})
        return {'items':results,'formula':'Mean percentage across recorded faculty-entered exam results (marks / maximum × 100). Missing exams never count as zero. Interests and achievements are displayed, not invented or added to marks.'}

    @app.get('/api/v4/class-analytics')
    def class_analytics(assignment_id:str,user=Depends(identity)):
        roles(user,'faculty','admin')
        with engine.connect() as c:
            a=assigned(c,user,assignment_id)
            members=class_roster(c,a)
            ids={r['id'] for r in members}
            marks=[r for r in mark_stats(c,user['college_id'],ids) if r['subject']==a['subject']]
            attendance=[r for r in attendance_stats(c,user['college_id'],ids) if r['subject']==a['subject']]
            prefs=c.execute(select(college_preferences.c.configuration).where(college_preferences.c.college_id==user['college_id'])).scalar_one_or_none() or {}
        pass_pct=prefs.get('pass_percentage',40);threshold=prefs.get('attendance_threshold',75)
        averages=summarize(marks)
        graded=[v for v in averages.values()]
        passed=sum(v>=pass_pct for v in graded)
        counts=defaultdict(lambda:[0,0])
        for r in attendance:
            counts[r['student_id']][1]+=1;counts[r['student_id']][0]+=int(r['present'])
        # Do not mutate the defaultdict when checking students without attendance.
        # Previously this added zero-session rows and caused ZeroDivisionError
        # when a class had marks but not yet any attendance sessions.
        low=[]
        for student in members:
            p=counts.get(student['student_id'])
            if not p or p[1]==0:continue
            attendance_pct=round(100*p[0]/p[1],1)
            if attendance_pct<threshold:
                low.append({'student_id':student['student_id'],'full_name':student['full_name'],'attendance_pct':attendance_pct})
        eligible=sum(total>0 for present,total in counts.values())
        return {'class_size':len(members),'graded':len(graded),'exam_records_count':len(marks),'marks_note':'Only entered exam results and published legacy marks are included; no estimates.','pass_percentage':round(100*passed/len(graded),1) if graded else None,'fail_percentage':round(100*(len(graded)-passed)/len(graded),1) if graded else None,'attendance_threshold':threshold,'below_attendance':low,
                'attendance_fall_percentage':round(100*len(low)/eligible,1) if eligible else None,
                'attendance_session_count':len({(r['on_date'],r['time_slot']) for r in attendance})}

    @app.post('/api/v4/achievements',status_code=201)
    def achievement(body:AchievementInput,user=Depends(identity)):
        roles(user,'student')
        if body.kind not in ('achievement','certificate'):raise HTTPException(400,'Choose achievement or certificate.')
        if body.base64_document:
            if not body.mime_type or body.mime_type not in ('application/pdf','image/png','image/jpeg','image/webp'):
                raise HTTPException(400,'Only PDF/PNG/JPG/WebP documents are accepted.')
            try:data=base64.b64decode(body.base64_document,validate=True)
            except (ValueError,binascii.Error):raise HTTPException(400,'Invalid file data.')
            if len(data)>2*1024*1024:raise HTTPException(413,'Maximum upload size: 2 MB.')
            magic= data.startswith(b'%PDF-') if body.mime_type=='application/pdf' else (data.startswith(b'\x89PNG') if body.mime_type=='image/png' else data.startswith(b'\xff\xd8') if body.mime_type=='image/jpeg' else data.startswith(b'RIFF') and data[8:12]==b'WEBP')
            if not magic:raise HTTPException(400,'File content does not match its type.')
        else:data=None
        with engine.begin() as c:
            r=authorized_student(c,user,user['student_id'])
            identx=ident()
            c.execute(insert(student_achievements).values(id=identx,college_id=user['college_id'],roster_id=r['id'],kind=body.kind,title=body.title,description=body.description,file_name=body.file_name if data else None,mime_type=body.mime_type if data else None,document=data,created_at=now()))
            audit(c,user,'student.achievement.added',{'id':identx,'kind':body.kind})
        return {'id':identx,'ok':True}

    @app.get('/api/v4/achievements/{achievement_id}/file')
    def achievement_file(achievement_id:str,user=Depends(identity)):
        with engine.connect() as c:
            ids=visible_ids(c,user)
            row=c.execute(select(student_achievements).where(student_achievements.c.id==achievement_id,student_achievements.c.college_id==user['college_id'])).mappings().first()
            if not row or row['roster_id'] not in ids or row['document'] is None:raise HTTPException(404,'File unavailable.')
        safe_name=re.sub('[^a-zA-Z0-9_.-]','_',row['file_name'] or 'attachment')
        return Response(content=row['document'],media_type=row['mime_type'],headers={'Content-Disposition':f'attachment; filename="{safe_name}"','X-Content-Type-Options':'nosniff'})
