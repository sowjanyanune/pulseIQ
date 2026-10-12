import os
os.environ['BOOTSTRAP_COLLEGE_NAME']='Demo Engineering College'
os.environ['BOOTSTRAP_COLLEGE_DOMAIN']='democollege.edu.in'
os.environ['BOOTSTRAP_ADMIN_EMAIL']='admin@democollege.edu.in'
os.environ['REGISTRATION_INVITE_CODE']='invite-very-long-test-code'
from fastapi.testclient import TestClient
from backend.api_v3 import create_app
from backend.settings import Settings
from backend.db import engine_for
from sqlalchemy import text, select
from backend.tenant_db import accounts,roster,subjects
S=Settings('sqlite+pysqlite:///:memory:','a'*44,'SomeStrongPass1234',environment='test',cookie_secure=False)
e=engine_for('sqlite+pysqlite:///:memory:')
app=create_app(S,e)
with TestClient(app) as guest:
    def show(name,r,expected):
        print(name,r.status_code, r.json())
        assert r.status_code==expected,(name,r.text)
    show('registration status',guest.get('/api/colleges/registration-status'),200)
    show('invalid invite',guest.post('/api/colleges/register',json={'name':'Second Campus','domain':'second.edu.in','admin_name':'Campus Admin','admin_email':'admin@second.edu.in','admin_password':'Password123456','registration_code':'wrong'}),403)
    show('register second college',guest.post('/api/colleges/register',json={'name':'Second Campus','domain':'second.edu.in','admin_name':'Campus Admin','admin_email':'admin@second.edu.in','admin_password':'Password123456','registration_code':'invite-very-long-test-code'}),201)
    if True:
        admin=TestClient(app)
        show('admin login',admin.post('/api/auth/login',json={'email':'admin@democollege.edu.in','password':'SomeStrongPass1234'}),200)
        csrf=admin.get('/api/auth/me').json()['csrf_token'];h={'X-CSRF-Token':csrf}
        show('prefs default',admin.get('/api/college/preferences'),200)
        show('prefs update',admin.put('/api/college/preferences',json={'academic_year':'2026-2027','attendance_threshold':78,'pass_percentage':40,'departments':['CSE','ECE']},headers=h),200)
        show('admin add student',admin.post('/api/admin/students',json={'student_id':'26CSE0001','full_name':'Aarav Reddy','email':'student001@democollege.edu.in','department':'CSE','semester':5,'section':'A'},headers=h),200)
        fac=admin.post('/api/admin/accounts',json={'email':'faculty001@democollege.edu.in','full_name':'Faculty One','password':'FacultyPass1234','role':'faculty','departments':['CSE']},headers=h)
        show('add faculty',fac,201)
        stu=admin.post('/api/admin/accounts',json={'email':'student001@democollege.edu.in','full_name':'Aarav Reddy','password':'StudentPass1234','role':'student','student_id':'26CSE0001'},headers=h)
        show('add student account',stu,201)
        ass=admin.post('/api/admin/assignments',json={'faculty_id':fac.json()['id'],'department':'CSE','semester':5,'section':'A','subject':'Machine Learning'},headers=h)
        show('faculty class',ass,201)
        show('task role protected',guest.post('/api/learning/tasks',json={},headers=h),401)
        task=admin.post('/api/learning/tasks',json={'assignment_id':ass.json()['id'],'kind':'quiz','title':'ML Basics Quiz','description':'Read the unit','due_at':'2030-01-01T10:00:00+00:00','max_points':10,'questions':[{'prompt':'What is supervised learning?','options':['Labelled data','No data'],'correct_index':0,'points':10}],'published':True},headers=h)
        show('create quiz',task,201)
        tid=task.json()['id']
        show('create resource',admin.post('/api/learning/resources',json={'assignment_id':ass.json()['id'],'title':'ML Study Link','url':'https://example.com/tutorial','description':'Study resource'},headers=h),201)
        show('focus',admin.get('/api/insights/focus'),200)
        if True:
            student=TestClient(app)
            login=student.post('/api/auth/login',json={'email':'student001@democollege.edu.in','password':'StudentPass1234'})
            show('student login',login,200)
            sh={'X-CSRF-Token':login.json()['csrf_token']}
            tasks=student.get('/api/learning/tasks');show('student task list',tasks,200)
            assert len(tasks.json()['items'])==1
            assert 'correct_index' not in tasks.json()['items'][0]['questions'][0]
            show('submit answers',student.post(f'/api/learning/tasks/{tid}/submit',json={'answers':{'0':0}},headers=sh),201)
            show('duplicate submit rejected',student.post(f'/api/learning/tasks/{tid}/submit',json={'answers':{'0':0}},headers=sh),409)
            show('student resources',student.get('/api/learning/resources'),200)
            show('student cannot grade',student.patch('/api/learning/submissions/nonexistent/grade',json={'score':10},headers=sh),403)
        show('submission list',admin.get(f'/api/learning/tasks/{tid}/submissions'),200)
        if True:
            college2=TestClient(app)
            r=college2.post('/api/auth/login',json={'email':'admin@second.edu.in','password':'Password123456'});show('other college login',r,200)
            assert college2.get('/api/students').json()['items']==[]
            assert college2.get('/api/learning/tasks').json()['items']==[]
            # no unauthorized direct refs
            assert college2.get(f'/api/learning/tasks/{tid}/submissions').status_code==404
print('ALL INTEGRATION CHECKS PASSED')
