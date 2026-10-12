"""Tenant-scoped assignments, quizzes, learning links, and personalized evidence-based focus areas."""
from datetime import datetime, timezone
import uuid
from urllib.parse import urlparse
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, insert, update
from .tenant_db import (learning_tasks,learning_submissions,learning_resources,
    subjects,roster,accounts,observations,entries,college_preferences,now)
from .tenant_auth import identity,roles
from .tenant_data import authorized_student,visible_ids,academic,audit
from .repository import clean

uid=lambda:str(uuid.uuid4())
class Question(BaseModel):
    prompt:str=Field(min_length=3,max_length=1000)
    options:list[str]=Field(min_length=2,max_length=6)
    correct_index:int=Field(ge=0,le=5)
    points:int=Field(default=1,ge=1,le=100)
class NewTask(BaseModel):
    assignment_id:str
    kind:str
    title:str=Field(min_length=3,max_length=200)
    description:str=Field(default='',max_length=5000)
    due_at:datetime
    max_points:int=Field(default=100,ge=1,le=1000)
    questions:list[Question]=Field(default_factory=list,max_length=60)
    published:bool=True
class NewSubmission(BaseModel):
    answers:dict[str,str|int]=Field(default_factory=dict)
class GradeSubmission(BaseModel):
    score:float=Field(ge=0)
    feedback:str=Field(default='',max_length=3000)
class NewResource(BaseModel):
    assignment_id:str
    title:str=Field(min_length=3,max_length=200)
    url:str=Field(min_length=10,max_length=2000)
    description:str=Field(default='',max_length=3000)


def visible_assignment(c,user,assignment_id):
    item=c.execute(select(subjects).where(subjects.c.id==assignment_id,subjects.c.college_id==user['college_id'])).mappings().first()
    if not item:raise HTTPException(404,'Class assignment not found.')
    if user['role']=='faculty' and item['faculty_id']!=user['id']:
        raise HTTPException(403,'This class is not assigned to you.')
    if user['role']=='student':
        s=authorized_student(c,user,user['student_id'])
        if (s['department'],s['semester'],s['section'])!=(item['department'],item['semester'],item['section']):
            raise HTTPException(404,'Class not found in your timetable.')
    return item

def safe_task(t,user):
    row=clean(dict(t))
    if user['role']=='student':
        row['questions']=[{'prompt':q['prompt'],'options':q['options'],'points':q['points']} for q in (row['questions'] or [])]
    return row


def install_learning_routes(app,engine):
    @app.get('/api/learning/tasks')
    def task_list(user=Depends(identity)):
        with engine.connect() as c:
            q=select(learning_tasks,subjects.c.department,subjects.c.semester,subjects.c.section,
                     subjects.c.subject,accounts.c.full_name.label('teacher_name')).join(subjects,learning_tasks.c.assignment_id==subjects.c.id).join(accounts,learning_tasks.c.created_by==accounts.c.id).where(learning_tasks.c.college_id==user['college_id'])
            if user['role']=='faculty':q=q.where(subjects.c.faculty_id==user['id'])
            if user['role']=='student':
                st=authorized_student(c,user,user['student_id'])
                q=q.where(subjects.c.department==st['department'],subjects.c.semester==st['semester'],subjects.c.section==st['section'],learning_tasks.c.published==True)
            result=c.execute(q.order_by(learning_tasks.c.due_at.desc()).limit(500)).mappings().all()
            submap={}
            if user['role']=='student' and result:
                ids=[r['id'] for r in result]
                raw=c.execute(select(learning_submissions).where(learning_submissions.c.college_id==user['college_id'],learning_submissions.c.task_id.in_(ids),learning_submissions.c.roster_id==st['id'])).mappings().all()
                submap={s['task_id']:clean(dict(s)) for s in raw}
        items=[]
        for r in result:
            item=safe_task(r,user)
            if user['role']=='student':item['my_submission']=submap.get(r['id'])
            items.append(item)
        return {'items':items}

    @app.post('/api/learning/tasks',status_code=201)
    def task_create(body:NewTask,user=Depends(identity)):
        roles(user,'admin','faculty')
        if body.kind not in ('assignment','quiz'):
            raise HTTPException(400,'Choose assignment or quiz.')
        if body.kind=='quiz' and not body.questions:
            raise HTTPException(400,'A quiz needs at least one question.')
        for q in body.questions:
            if q.correct_index>=len(q.options):raise HTTPException(400,'Question correct answer index is invalid.')
        if body.kind=='quiz' and sum(q.points for q in body.questions)>body.max_points:
            raise HTTPException(400,'Quiz question points exceed maximum.')
        with engine.begin() as c:
            visible_assignment(c,user,body.assignment_id)
            item=dict(id=uid(),college_id=user['college_id'],assignment_id=body.assignment_id,
                      created_by=user['id'],kind=body.kind,title=body.title.strip(),description=body.description,
                      due_at=body.due_at,max_points=body.max_points,
                      questions=[q.model_dump() for q in body.questions],published=body.published,created_at=now())
            c.execute(insert(learning_tasks).values(**item))
            audit(c,user,'learning.task.created',{'task_id':item['id'],'kind':body.kind})
        return {'id':item['id'],'ok':True}

    @app.post('/api/learning/tasks/{task_id}/submit',status_code=201)
    def task_submit(task_id:str,body:NewSubmission,user=Depends(identity)):
        roles(user,'student')
        with engine.begin() as c:
            task=c.execute(select(learning_tasks).where(learning_tasks.c.id==task_id,learning_tasks.c.college_id==user['college_id'],learning_tasks.c.published==True)).mappings().first()
            if not task:raise HTTPException(404,'Task is unavailable.')
            visible_assignment(c,user,task['assignment_id'])
            st=authorized_student(c,user,user['student_id'])
            if c.execute(select(learning_submissions.c.id).where(learning_submissions.c.task_id==task_id,learning_submissions.c.roster_id==st['id'])).first():
                raise HTTPException(409,'This task was already submitted.')
            if now()>task['due_at'].replace(tzinfo=task['due_at'].tzinfo or timezone.utc):
                raise HTTPException(400,'Submission deadline has passed.')
            answers=body.answers
            if task['kind']=='quiz':
                if any(str(i) not in answers for i in range(len(task['questions']))):
                    raise HTTPException(400,'Answer all quiz questions.')
                try:score=sum(int(q['points']) for i,q in enumerate(task['questions']) if int(answers[str(i)])==int(q['correct_index']))
                except (ValueError,TypeError):raise HTTPException(400,'Answers must be option numbers.')
                status='graded';feedback='Automatically scored multiple-choice answers.'
            else:
                if not str(answers.get('text','')).strip():raise HTTPException(400,'Enter your assignment response.')
                score=None;status='submitted';feedback='Awaiting faculty review.'
            item=dict(id=uid(),college_id=user['college_id'],task_id=task_id,roster_id=st['id'],answers=answers,
                      score=score,feedback=feedback,status=status,submitted_at=now())
            c.execute(insert(learning_submissions).values(**item))
            audit(c,user,'learning.submission.created',{'task_id':task_id,'status':status})
        return {'ok':True,'status':status,'score':score,'max_points':task['max_points']}

    @app.get('/api/learning/tasks/{task_id}/submissions')
    def task_submissions(task_id:str,user=Depends(identity)):
        roles(user,'admin','faculty')
        with engine.connect() as c:
            task=c.execute(select(learning_tasks).where(learning_tasks.c.id==task_id,learning_tasks.c.college_id==user['college_id'])).mappings().first()
            if not task:raise HTTPException(404,'Task unavailable.')
            visible_assignment(c,user,task['assignment_id'])
            rows=c.execute(select(learning_submissions,roster.c.student_id,roster.c.full_name)
                .join(roster,learning_submissions.c.roster_id==roster.c.id)
                .where(learning_submissions.c.college_id==user['college_id'],learning_submissions.c.task_id==task_id)
                .order_by(roster.c.student_id)).mappings().all()
        return {'items':clean([dict(r) for r in rows])}

    @app.patch('/api/learning/submissions/{submission_id}/grade')
    def grade_submission(submission_id:str,body:GradeSubmission,user=Depends(identity)):
        roles(user,'admin','faculty')
        with engine.begin() as c:
            s=c.execute(select(learning_submissions,learning_tasks.c.assignment_id,learning_tasks.c.max_points)
                .join(learning_tasks,learning_submissions.c.task_id==learning_tasks.c.id)
                .where(learning_submissions.c.id==submission_id,learning_submissions.c.college_id==user['college_id'])).mappings().first()
            if not s:raise HTTPException(404,'Submission not found.')
            visible_assignment(c,user,s['assignment_id'])
            if body.score>s['max_points']:raise HTTPException(400,'Score cannot exceed maximum points.')
            c.execute(update(learning_submissions).where(learning_submissions.c.id==submission_id,learning_submissions.c.college_id==user['college_id']).values(score=body.score,feedback=body.feedback,status='graded'))
            audit(c,user,'learning.submission.graded',{'submission_id':submission_id})
        return {'ok':True}

    @app.get('/api/learning/resources')
    def resources_list(user=Depends(identity)):
        with engine.connect() as c:
            q=select(learning_resources,subjects.c.subject,subjects.c.department,subjects.c.semester,subjects.c.section).join(subjects,learning_resources.c.assignment_id==subjects.c.id).where(learning_resources.c.college_id==user['college_id'])
            if user['role']=='faculty':q=q.where(subjects.c.faculty_id==user['id'])
            if user['role']=='student':
                st=authorized_student(c,user,user['student_id'])
                q=q.where(subjects.c.department==st['department'],subjects.c.semester==st['semester'],subjects.c.section==st['section'])
            rows=c.execute(q.order_by(learning_resources.c.created_at.desc()).limit(500)).mappings().all()
        return {'items':clean([dict(r) for r in rows])}

    @app.post('/api/learning/resources',status_code=201)
    def resource_create(body:NewResource,user=Depends(identity)):
        roles(user,'admin','faculty')
        parsed=urlparse(body.url.strip())
        if parsed.scheme not in ('http','https') or not parsed.netloc or parsed.username or parsed.password:
            raise HTTPException(400,'Share a valid public http/https resource link without credentials.')
        with engine.begin() as c:
            visible_assignment(c,user,body.assignment_id)
            item=dict(id=uid(),college_id=user['college_id'],assignment_id=body.assignment_id,created_by=user['id'],title=body.title.strip(),url=body.url.strip(),description=body.description,created_at=now())
            c.execute(insert(learning_resources).values(**item))
            audit(c,user,'learning.resource.added',{'id':item['id']})
        return {'ok':True,'id':item['id']}

    @app.get('/api/insights/focus')
    def focus_recommendations(user=Depends(identity)):
        records,periods,current=academic(engine,user)
        with engine.connect() as c:
            prefs=c.execute(select(college_preferences.c.configuration).where(college_preferences.c.college_id==user['college_id'])).scalar_one_or_none() or {}
        attendance_target=int(prefs.get('attendance_threshold',75))
        academic_target=max(60,int(prefs.get('pass_percentage',40)))
        out=[]
        for r in records:
            hints=[]
            attendance=(100*r['classes_attended']/r['classes_held']) if r.get('classes_held') else None
            if attendance is not None and attendance<attendance_target:
                hints.append({'area':'Attendance','observed':round(attendance,1),'target':attendance_target,'priority':round(attendance_target-attendance,1),'recommendation':'Attend scheduled classes and follow up on absences.'})
            marks=r.get('marks_pct')
            if marks is not None and marks<academic_target:
                hints.append({'area':'Academic marks','observed':round(marks,1),'target':academic_target,'priority':round(academic_target-marks,1),'recommendation':'Revise weak subjects, attend remedial sessions and practice assessments.'})
            if r.get('assignments_assigned') and r.get('assignments_completed') is not None:
                completion=100*r['assignments_completed']/r['assignments_assigned']
                if completion<80:
                    hints.append({'area':'LMS assignments','observed':round(completion,1),'target':80,'priority':round(80-completion,1),'recommendation':'Complete pending activities and request feedback on submissions.'})
            for field,area,target,recommendation in [
                ('coding_pct','Coding skills',70,'Practice coding challenges and review problem-solving concepts.'),
                ('aptitude_pct','Placement aptitude',70,'Practice aptitude mock tests and interview preparation.')]:
                x=r.get(field)
                if x is not None and x<target:
                    hints.append({'area':area,'observed':round(x,1),'target':target,'priority':round(target-x,1),'recommendation':recommendation})
            hints.sort(key=lambda x:x['priority'],reverse=True)
            out.append({'student_id':r['student_id'],'full_name':r['full_name'],'coverage':r.get('coverage'),'score':r.get('overall_score'),'focus_areas':hints[:5]})
        return {'items':out,'notice':'Evidence-based guidance from observed student records; not a causal prediction of future improvement. Train the separate ML model on labeled historical outcomes for model-based risk estimates.'}
