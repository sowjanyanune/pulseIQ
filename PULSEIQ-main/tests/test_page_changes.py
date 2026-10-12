"""October 2026 page-by-page requirements integration tests (SQLite only)."""
from datetime import date,timedelta
from test_tenants import client,signin,post,PASSWORD


def test_new_student_login_admin_pie_and_faculty_directory(client):
    signin(client,'admin@test.edu')
    profile=post(client,'/api/v4/students',{
        'student_id':'S100','full_name':'Asha Rao','email':'asha@test.edu','password':PASSWORD,
        'department':'CSE','semester':3,'section':'B','phone':'9876543210','interests':['Robotics','Programming']})
    assert profile['student_id']=='S100'
    dash=client.get('/api/v4/dashboard').json()
    assert dash['students_total']==1 and dash['students_by_branch'][0]['name']=='CSE'
    s=client.get('/api/v4/directory',params={'department':'CSE','section':'B','q':'Asha'}).json()['items']
    assert len(s)==1 and s[0]['phone']=='9876543210'
    assert client.get('/api/v4/directory',params={'section':'C'}).json()['items']==[]
    signin(client,'asha@test.edu')
    self=client.get('/api/v4/student/me').json()
    assert self['record']['student_id']=='S100' and self['interests']==['Robotics','Programming']
    assert client.get('/api/v4/dashboard').status_code==403


def test_faculty_marks_attendance_slot_topic_and_student_view(client):
    signin(client,'admin@test.edu')
    post(client,'/api/v4/students',{'student_id':'ROLL1','full_name':'Learner One',
        'email':'learner@test.edu','password':PASSWORD,'department':'CSE','semester':3,'section':'A'})
    faculty=post(client,'/api/admin/accounts',{'email':'teach@test.edu','full_name':'Teacher',
        'password':PASSWORD,'role':'faculty','departments':['CSE']})
    a=post(client,'/api/admin/assignments',{'faculty_id':faculty['id'],'department':'CSE',
        'semester':3,'section':'A','subject':'Data Structures'})
    aid=a['id'];day=date.today().isoformat()
    tim=post(client,'/api/timetable',{'assignment_id':aid,'weekday':0,'start_time':'09:00','end_time':'10:00','room':'CSE101'})
    assert client.get('/api/timetable').json()['items'][0]['subject']=='Data Structures'
    # Admin may not change class presence.
    bad=client.post('/api/v4/attendance/batch',json={'assignment_id':aid,'on_date':day,'time_slot':'09:00-10:00',
        'topic':'Graphs','items':[{'student_id':'ROLL1','present':True}]})
    assert bad.status_code==403
    signin(client,'teach@test.edu')
    assert client.post('/api/timetable',json={'assignment_id':aid,'weekday':1,'start_time':'10:00','end_time':'11:00','room':'CSE101'}).status_code==403
    assert len(client.get('/api/v4/class/'+aid+'/students').json()['items'])==1
    post(client,'/api/v4/attendance/batch',{'assignment_id':aid,'on_date':day,'time_slot':'09:00-10:00',
        'topic':'Intro to graphs','items':[{'student_id':'ROLL1','present':False}]})
    post(client,'/api/v4/attendance/batch',{'assignment_id':aid,'on_date':day,'time_slot':'09:00-10:00',
        'topic':'Graph traversal','items':[{'student_id':'ROLL1','present':True}]})
    s=client.get('/api/v4/attendance/session',params={'assignment_id':aid,'on_date':day,'time_slot':'09:00-10:00'}).json()
    assert s['items'][0]['present'] is True and s['topic']=='Graph traversal'
    post(client,'/api/v4/marks/batch',{'assignment_id':aid,'exam_name':'Mid 1','exam_date':day,'maximum':30,
        'items':[{'student_id':'ROLL1','marks':21}]})
    post(client,'/api/v4/marks/batch',{'assignment_id':aid,'exam_name':'Mid 2','exam_date':day,'maximum':30,
        'items':[{'student_id':'ROLL1','marks':12}]})
    insights=client.get('/api/v4/success').json()['items']
    assert len(insights)==1 and insights[0]['success_rate']==55.0
    assert insights[0]['exam_count']==2
    stat=client.get('/api/v4/class-analytics',params={'assignment_id':aid}).json()
    assert stat['pass_percentage']==100.0 and stat['attendance_session_count']==1
    signin(client,'learner@test.edu')
    report=client.get('/api/v4/attendance/report').json()
    assert report['summary'][0]['percentage']==100.0 and report['items'][0]['topic']=='Graph traversal'
    result=client.get('/api/v4/performance').json()
    assert len(result['marks'])==2 and result['marks'][0]['subject']=='Data Structures'
    assert client.get('/api/timetable').json()['items'][0]['room']=='CSE101'
    assert client.post('/api/v4/marks/batch',json={'assignment_id':aid,'exam_name':'Fraud','exam_date':day,'maximum':30,'items':[{'student_id':'ROLL1','marks':30}]}).status_code==403


def test_achievements_file_upload_and_role_scoping(client):
    signin(client,'admin@test.edu')
    post(client,'/api/v4/students',{'student_id':'S01','full_name':'First','email':'first@test.edu','password':PASSWORD,'department':'IT','semester':2,'section':'A'})
    post(client,'/api/v4/students',{'student_id':'S02','full_name':'Second','email':'second@test.edu','password':PASSWORD,'department':'IT','semester':2,'section':'A'})
    signin(client,'first@test.edu')
    import base64
    f=post(client,'/api/v4/achievements',{'kind':'certificate','title':'Python Certificate','description':'Learning','mime_type':'application/pdf','file_name':'certificate.pdf','base64_document':base64.b64encode(b'%PDF-1.4 sample demo').decode()})
    ach=client.get('/api/v4/performance').json()['achievements']
    assert len(ach)==1 and ach[0]['title']=='Python Certificate'
    response=client.get(f'/api/v4/achievements/{f["id"]}/file')
    assert response.status_code==200 and response.content.startswith(b'%PDF-')
    signin(client,'second@test.edu')
    assert client.get(f'/api/v4/achievements/{f["id"]}/file').status_code==404


def test_admin_faculty_attendance_and_timetable_delete(client):
    signin(client,'admin@test.edu')
    fac=post(client,'/api/admin/accounts',{'email':'teacher@test.edu','full_name':'Teacher','password':PASSWORD,'role':'faculty','departments':['CSE']})
    cid=post(client,'/api/admin/assignments',{'faculty_id':fac['id'],'department':'CSE','semester':3,'section':'A','subject':'ML'})['id']
    post(client,'/api/v4/faculty/attendance',{'faculty_id':fac['id'],'on_date':date.today().isoformat(),'present':False})
    post(client,'/api/v4/faculty/attendance',{'faculty_id':fac['id'],'on_date':date.today().isoformat(),'present':True})
    detail=client.get('/api/v4/faculty').json()['items'][0]
    assert detail['present_days']==1 and detail['total_days']==1
    t=post(client,'/api/timetable',{'assignment_id':cid,'weekday':3,'start_time':'09:00','end_time':'10:00','room':'A1'})
    assert client.delete('/api/timetable/'+t['id']).status_code==200
    assert client.get('/api/timetable').json()['items']==[]


def test_new_pages_isolate_colleges_with_same_roll_number(client):
    from uuid import uuid4
    from sqlalchemy import insert
    from backend.tenant_db import colleges,accounts,roster,now
    from backend.tenant_auth import passwords
    signin(client,'admin@test.edu')
    post(client,'/api/v4/students',{'student_id':'DUP1','full_name':'Campus One Student',
        'email':'one@test.edu','password':PASSWORD,'department':'CSE','semester':1,'section':'A'})
    engine=client.app.state.engine
    with engine.begin() as c:
        cid=str(uuid4())
        c.execute(insert(colleges).values(id=cid,name='Second College',domain='second.edu',created_at=now()))
        c.execute(insert(accounts).values(id=str(uuid4()),college_id=cid,email='admin@second.edu',full_name='Second Admin',password_hash=passwords.hash(PASSWORD),role='admin',departments=[],student_id=None,active=True))
        c.execute(insert(roster).values(id=str(uuid4()),college_id=cid,student_id='DUP1',full_name='Second Student',email='second@second.edu',department='ECE',semester=2,section='B',active=True))
    signin(client,'admin@second.edu')
    assert client.get('/api/v4/dashboard').json()['students_by_branch']==[{'name':'ECE','count':1}]
    rows=client.get('/api/v4/directory').json()['items']
    assert len(rows)==1 and rows[0]['full_name']=='Second Student'
    assert client.get('/api/v4/success').json()['items'][0]['full_name']=='Second Student'
    signin(client,'admin@test.edu')
    assert client.get('/api/v4/directory').json()['items'][0]['full_name']=='Campus One Student'


def test_only_original_faculty_can_correct_attendance(client):
    signin(client,'admin@test.edu')
    post(client,'/api/v4/students',{'student_id':'O1','full_name':'Only Student','email':'only@test.edu','password':PASSWORD,'department':'IT','semester':2,'section':'B'})
    first=post(client,'/api/admin/accounts',{'email':'fac1@test.edu','full_name':'First Teacher','password':PASSWORD,'role':'faculty','departments':['IT']})
    second=post(client,'/api/admin/accounts',{'email':'fac2@test.edu','full_name':'Second Teacher','password':PASSWORD,'role':'faculty','departments':['IT']})
    aid=post(client,'/api/admin/assignments',{'faculty_id':first['id'],'department':'IT','semester':2,'section':'B','subject':'Science'})['id']
    signin(client,'fac1@test.edu')
    packet={'assignment_id':aid,'on_date':date.today().isoformat(),'time_slot':'11:00-12:00','topic':'Chemistry','items':[{'student_id':'O1','present':True}]}
    post(client,'/api/v4/attendance/batch',packet)
    signin(client,'fac2@test.edu')
    assert client.post('/api/v4/attendance/batch',json=packet).status_code==403
    assert client.get('/api/v4/attendance/session',params={'assignment_id':aid,'on_date':date.today().isoformat(),'time_slot':'11:00-12:00'}).status_code==403
