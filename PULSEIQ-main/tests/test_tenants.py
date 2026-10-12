"""Run with: pip install -r requirements.txt -r requirements-dev.txt && pytest -q"""
from datetime import date
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert,select
from backend.api_v3 import create_app
from backend.settings import Settings
from backend.tenant_db import colleges, accounts, roster, now
from backend.tenant_auth import passwords

PASSWORD='testing-a-very-long-password'

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('BOOTSTRAP_COLLEGE_NAME','Test University')
    monkeypatch.setenv('BOOTSTRAP_ADMIN_EMAIL','admin@test.edu')
    monkeypatch.setenv('BOOTSTRAP_COLLEGE_DOMAIN','test.edu')
    settings=Settings('sqlite:///'+str(tmp_path/'test.sqlite'),'a-super-secret-value-longer-than-32-characters',PASSWORD,False,200,False,'test')
    with TestClient(create_app(settings)) as c:
        yield c

def signin(c,email,password=PASSWORD):
    resp=c.post('/api/auth/login',json={'email':email,'password':password})
    assert resp.status_code==200,resp.text
    c.headers['X-CSRF-Token']=resp.json()['csrf_token']
    return resp.json()['user']

def post(c,url,data):
    r=c.post(url,json=data)
    assert 200<=r.status_code<300,(url,r.status_code,r.text)
    return r.json()

def setup_class(c):
    signin(c,'admin@test.edu')
    post(c,'/api/admin/students',{'student_id':'S001','full_name':'Sample One','department':'CS','semester':4,'section':'A'})
    post(c,'/api/admin/students',{'student_id':'S002','full_name':'Sample Two','department':'CS','semester':4,'section':'B'})
    faculty=post(c,'/api/admin/accounts',{'email':'teacher@test.edu','full_name':'Teacher','password':PASSWORD,'role':'faculty'})
    post(c,'/api/admin/accounts',{'email':'student@test.edu','full_name':'Student','password':PASSWORD,'role':'student','student_id':'S001'})
    assignment=post(c,'/api/admin/assignments',{'faculty_id':faculty['id'],'department':'CS','semester':4,'section':'A','subject':'Mathematics'})
    return assignment['id']

def test_login_college_detection_and_roles(client):
    assert client.get('/api/colleges/resolve',params={'email':'whoever@test.edu'}).json()['college_name']=='Test University'
    assert client.get('/api/colleges/resolve',params={'email':'whoever@outside.org'}).json()['recognized'] is False
    setup_class(client)
    signin(client,'student@test.edu')
    assert len(client.get('/api/students').json()['items'])==1
    assert client.get('/api/students/S002').status_code==404
    assert client.get('/api/admin/accounts').status_code==403
    assert client.post('/api/admin/students',json={'student_id':'HI','full_name':'No','department':'CS','semester':1}).status_code==403

def test_faculty_only_assigned_class_and_publishing(client):
    assignment=setup_class(client)
    signin(client,'teacher@test.edu')
    assert {r['student_id'] for r in client.get('/api/students').json()['items']}=={'S001'}
    data=dict(assignment_id=assignment,kind='attendance',period_end=date.today().isoformat(),attended=34,held=40,status='published')
    assert client.post('/api/entries',json={**data,'student_id':'S002'}).status_code==404
    post(client,'/api/entries',{**data,'student_id':'S001'})
    profile=client.get('/api/students/S001').json()
    assert profile['record']['classes_attended']==34
    assert len(profile['faculty_records'])==1
    signin(client,'student@test.edu')
    r=client.get('/api/students/S001')
    assert r.status_code==200 and r.json()['faculty_records'][0]['held']==40
    assert client.post('/api/entries',json={**data,'student_id':'S001'}).status_code==403

def test_csrf_and_domain_restrictions(client):
    signin(client,'admin@test.edu')
    assert client.post('/api/admin/accounts',json={'email':'x@other.edu','full_name':'X','password':PASSWORD,'role':'faculty'}).status_code==400
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/admin/students',json={'student_id':'X1','full_name':'X','department':'CS','semester':2}).status_code==403

def test_draft_not_published_and_bulk_atomic(client):
    assignment=setup_class(client)
    signin(client,'admin@test.edu')
    r=client.post('/api/admin/students/bulk',json=[
        {'student_id':'B1','full_name':'One','department':'CS','semester':4,'section':'A'},
        {'student_id':'B1','full_name':'Two','department':'CS','semester':4,'section':'A'}])
    assert r.status_code==400
    assert all(x['student_id']!='B1' for x in client.get('/api/students').json()['items'])
    signin(client,'teacher@test.edu')
    post(client,'/api/entries',{'student_id':'S001','assignment_id':assignment,'kind':'marks','period_end':date.today().isoformat(),'marks_pct':88,'status':'draft'})
    signin(client,'student@test.edu')
    p=client.get('/api/students/S001').json()
    assert p['faculty_records']==[] and p['record']['marks_pct'] is None

def test_isolates_second_college_even_reused_student_id(client):
    assignment=setup_class(client)
    signin(client,'admin@test.edu')
    eng=client.app.state.engine
    cid=str(uuid4());admin_id=str(uuid4());other_stu=str(uuid4())
    with eng.begin() as c:
        c.execute(insert(colleges).values(id=cid,name='Second Campus',domain='second.edu',created_at=now()))
        c.execute(insert(accounts).values(id=admin_id,college_id=cid,email='admin@second.edu',full_name='Second Admin',password_hash=passwords.hash(PASSWORD),role='admin',departments=[],student_id=None,active=True))
        c.execute(insert(roster).values(id=other_stu,college_id=cid,student_id='S001',full_name='Other Student',email=None,department='ME',semester=2,section='A',active=True))
    signin(client,'admin@second.edu')
    assert len(client.get('/api/students').json()['items'])==1
    assert client.get('/api/students/S001').json()['record']['full_name']=='Other Student'
    assert client.get('/api/admin/accounts').json()['items'][0]['email']=='admin@second.edu'
    assert client.post('/api/entries',json={'student_id':'S001','assignment_id':assignment,'kind':'marks','period_end':date.today().isoformat(),'marks_pct':85,'status':'published'}).status_code==403
    assert len(client.get('/api/assignments').json()['items'])==0

def test_action_create_and_update(client):
    setup_class(client)
    signin(client,'teacher@test.edu')
    v=post(client,'/api/actions',{'student_id':'S001','owner':'Counselor','action':'Plan tutoring','due_date':date.today().isoformat()})
    assert v['status']=='Planned'
    good={'owner':'Counselor','action':'Plan tutoring','due_date':date.today().isoformat(),'status':'Reviewed','note':'Discussed progress','version':1}
    assert client.patch('/api/actions/'+v['id'],json=good).status_code==200
    assert client.patch('/api/actions/'+v['id'],json=good).status_code==409
