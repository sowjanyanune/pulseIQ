"""Integration tests for the React-backed operational and traditional-ML API."""
from datetime import date
from test_tenants import client,signin,setup_class,post,PASSWORD

def test_announcements_are_persistent_and_role_secured(client):
    setup_class(client)
    signin(client,'admin@test.edu')
    post(client,'/api/announcements',{'title':'Midterm notice','body':'Check your academic calendar.','audience':'student'})
    signin(client,'student@test.edu')
    items=client.get('/api/announcements').json()['items']
    assert len(items)==1 and items[0]['title']=='Midterm notice'
    assert client.post('/api/announcements',json={'title':'Forged','body':'A fake notice','audience':'all'}).status_code==403

def test_student_requests_and_assigned_faculty_responses(client):
    setup_class(client)
    signin(client,'student@test.edu')
    req=post(client,'/api/requests',{'subject':'Attendance question','detail':'Please check Tuesday attendance.'})
    assert req['status']=='Open'
    signin(client,'teacher@test.edu')
    response=client.patch('/api/requests/'+req['id'],json={'status':'Resolved','reply':'Attendance was reviewed.'})
    assert response.status_code==200
    signin(client,'student@test.edu')
    assert client.get('/api/requests').json()['items'][0]['reply']=='Attendance was reviewed.'

def test_timetable_student_scope(client):
    assignment=setup_class(client)
    signin(client,'admin@test.edu')
    post(client,'/api/timetable',{'assignment_id':assignment,'weekday':0,'start_time':'09:00','end_time':'10:00','room':'Room 12'})
    assert client.post('/api/timetable',json={'assignment_id':assignment,'weekday':0,'start_time':'09:30','end_time':'10:30','room':'Room 12'}).status_code==409
    signin(client,'student@test.edu')
    rows=client.get('/api/timetable').json()['items']
    assert len(rows)==1 and rows[0]['subject']=='Mathematics'

def test_faculty_publishes_existing_draft_and_student_sees_it(client):
    assignment=setup_class(client)
    signin(client,'teacher@test.edu')
    post(client,'/api/entries',{'student_id':'S001','assignment_id':assignment,'kind':'marks','period_end':date.today().isoformat(),'marks_pct':84,'status':'draft'})
    rows=client.get('/api/entries').json()['items']
    assert rows[0]['status']=='draft'
    assert client.patch('/api/entries/'+rows[0]['id']+'/publish').status_code==200
    signin(client,'student@test.edu')
    rows=client.get('/api/students/S001').json()['faculty_records']
    assert len(rows)==1 and rows[0]['marks_pct']==84

def test_password_rotation_and_admin_reset(client):
    setup_class(client)
    signin(client,'student@test.edu')
    r=client.post('/api/auth/change-password',json={'current_password':PASSWORD,'new_password':'a-different-long-password'})
    assert r.status_code==200
    assert client.post('/api/auth/login',json={'email':'student@test.edu','password':PASSWORD}).status_code==401
    signin(client,'student@test.edu','a-different-long-password')
    signin(client,'admin@test.edu')
    target=next(x for x in client.get('/api/admin/accounts').json()['items'] if x['email']=='student@test.edu')
    post(client,f"/api/admin/accounts/{target['id']}/reset-password",{'new_password':'the-admin-reset-password'})
    assert client.post('/api/auth/login',json={'email':'student@test.edu','password':'a-different-long-password'}).status_code==401
    signin(client,'student@test.edu','the-admin-reset-password')

def test_ml_training_and_missing_data_truthfully_reported(client):
    setup_class(client)
    signin(client,'admin@test.edu')
    assert client.get('/api/ml/status').json()['trained'] is False
    r=client.post('/api/admin/ml/train',json={'demo':False})
    assert r.status_code==400 and '40 labeled' in r.json()['detail']
    report=post(client,'/api/admin/ml/train',{'demo':True})
    assert report['model']['source']=='synthetic_demo'
    status=client.get('/api/ml/status').json()
    assert status['trained'] is True
    assert status['model']['metadata']['source']=='synthetic_demo'
    predictions=client.get('/api/ml/predictions').json()
    assert predictions['trained'] is True
    assert predictions['items']==[] # roster-only students are NOT given fabricated features
    assert predictions['excluded_missing_data']==2
    signin(client,'student@test.edu')
    assert client.post('/api/admin/ml/train',json={'demo':True}).status_code==403
    assert client.get('/api/ml/status').json()['trained'] is True
