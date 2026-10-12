"""PULSEIQ October 11 regression tests: timezones, registration input, and marks analytics."""
from datetime import date, datetime, timezone
from test_tenants import client, signin, post, PASSWORD
from backend.campus_pages import college_local_date


def test_india_college_timezone_at_utc_midnight_boundary(client):
    signin(client, 'admin@test.edu')
    with client.app.state.engine.connect() as c:
        d, zone = college_local_date(c, client.get('/api/auth/me').json()['user']['college_id'],
                                     datetime(2026, 10, 10, 23, 40, tzinfo=timezone.utc))
    assert d == date(2026, 10, 11)
    assert zone == 'Asia/Kolkata'
    d = client.get('/api/v4/college-date')
    assert d.status_code == 200 and d.json()['timezone'] == 'Asia/Kolkata'


def test_public_registration_without_invite_and_six_character_password(client, monkeypatch):
    # No invite code configured or submitted. Registration remains publicly available.
    monkeypatch.delenv('REGISTRATION_INVITE_CODE', raising=False)
    status = client.get('/api/colleges/registration-status')
    assert status.status_code == 200
    assert status.json()['enabled'] is True
    assert status.json()['method'] == 'public_college_registration'
    base = dict(name='PulseIQ College', domain='clg@pulseiq.edu.in',
                admin_name='Teacher Admin', admin_email='teacher@pulseiq.edu.in',
                admin_password='secret')
    bad = client.post('/api/colleges/register', json=base)
    assert bad.status_code == 400
    assert 'valid college domain' in bad.json()['detail']
    badpw = client.post('/api/colleges/register', json={**base,'domain':'pulseiq.edu.in','admin_password':'short'})
    assert badpw.status_code == 422
    created = client.post('/api/colleges/register', json={**base,'domain':'pulseiq.edu.in'})
    assert created.status_code == 201,created.text
    duplicate = client.post('/api/colleges/register', json={**base,'domain':'pulseiq.edu.in'})
    assert duplicate.status_code == 409
    signin(client,'teacher@pulseiq.edu.in','secret')
    assert client.get('/api/auth/me').json()['user']['college_name']=='PulseIQ College'


def test_six_character_account_password_creation_and_rotation(client):
    from test_tenants import post
    signin(client,'admin@test.edu')
    user=post(client,'/api/admin/accounts',{'email':'simple@test.edu',
                'full_name':'Simple Faculty','password':'123456','role':'faculty'})
    assert user['email']=='simple@test.edu'
    bad=client.post('/api/admin/accounts',json={'email':'short@test.edu',
                'full_name':'Short Faculty','password':'12345','role':'faculty'})
    assert bad.status_code==422
    signin(client,'simple@test.edu','123456')
    changed=client.post('/api/auth/change-password',json={'current_password':'123456','new_password':'abcdef'})
    assert changed.status_code==200,changed.text
    signin(client,'simple@test.edu','abcdef')
    invalid=client.post('/api/auth/change-password',json={'current_password':'abcdef','new_password':'12345'})
    assert invalid.status_code==422


def test_class_analytics_reuses_published_legacy_marks_without_duplicates(client):
    signin(client,'admin@test.edu')
    post(client,'/api/v4/students',{'student_id':'BACK1','full_name':'Backward Compatible Student',
        'email':'back@test.edu','password':PASSWORD,'department':'CSE','semester':1,'section':'A'})
    faculty=post(client,'/api/admin/accounts',{'email':'legacy-teacher@test.edu',
        'full_name':'Legacy Teacher','password':PASSWORD,'role':'faculty','departments':['CSE']})
    assignment=post(client,'/api/admin/assignments',{'faculty_id':faculty['id'],
        'department':'CSE','semester':1,'section':'A','subject':'Algorithms'})['id']
    signin(client,'legacy-teacher@test.edu')
    post(client,'/api/entries',{'student_id':'BACK1','assignment_id':assignment,
        'kind':'marks','period_end':date.today().isoformat(),
        'marks_pct':65,'status':'published'})
    a=client.get('/api/v4/class-analytics',params={'assignment_id':assignment})
    assert a.status_code==200,a.text
    assert a.json()['exam_records_count']==1
    assert a.json()['pass_percentage']==100
    suc=client.get('/api/v4/success').json()['items']
    assert suc[0]['success_rate']==65
    post(client,'/api/v4/marks/batch',{'assignment_id':assignment,'exam_name':'Mid Semester 1',
        'exam_date':date.today().isoformat(),'maximum':30,
        'items':[{'student_id':'BACK1','marks':12}]})
    new=client.get('/api/v4/class-analytics',params={'assignment_id':assignment})
    assert new.status_code==200,new.text
    assert new.json()['exam_records_count']==1  # never double-count the older record
    assert new.json()['pass_percentage']==100
    assert client.get('/api/v4/success').json()['items'][0]['success_rate']==40


def test_empty_platform_can_register_first_college_without_bootstrap_or_invite(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.api_v3 import create_app
    from backend.settings import Settings
    for name in ('REGISTRATION_INVITE_CODE','BOOTSTRAP_COLLEGE_NAME','BOOTSTRAP_COLLEGE_DOMAIN',
                 'BOOTSTRAP_ADMIN_EMAIL','BOOTSTRAP_ADMIN_PASSWORD'):
        monkeypatch.delenv(name, raising=False)
    settings=Settings('sqlite:///'+str(tmp_path/'onboard.sqlite'),
                      'a-super-secret-value-longer-than-32-characters',
                      '',False,200,False,'test')
    with TestClient(create_app(settings)) as c:
        x=c.post('/api/colleges/register',json={
            'name':'Brand New Institute','domain':'brandnew.edu',
            'admin_name':'New Administrator','admin_email':'admin@brandnew.edu',
            'admin_password':'123456'})
        assert x.status_code==201,x.text
        login=c.post('/api/auth/login',json={'email':'admin@brandnew.edu','password':'123456'})
        assert login.status_code==200,login.text
