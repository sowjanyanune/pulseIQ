from datetime import date
import csv,io
from test_tenants import client, signin, post, setup_class
from backend.seed import generate
from backend.db import SCHEMAS

def test_seven_source_import_explanation_and_atomic_validation(client):
    signin(client,'admin@test.edu')
    records=generate(8)
    files={}
    for name, rows in records.items():
        out=io.StringIO(); w=csv.DictWriter(out,fieldnames=SCHEMAS[name]);w.writeheader();w.writerows(rows);files[name]=out.getvalue()
    result=post(client,'/api/admin/import-csv',{'files':files})
    assert result['students']==8
    detail=client.get('/api/students/DEMO0001').json()
    assert detail['record']['overall_score']==68
    assert sum(c['effective_points'] for c in detail['components'])==68
    assert 'Strong academics with placement gap' in detail['record']['segments']
    assert client.get('/api/students/DEMO0007').json()['record']['support_request'] is True
    assert len(client.get('/api/analytics/trends').json()['items'])==2
    files['academic']=files['academic'].replace(',80,',',999,')
    assert client.post('/api/admin/import-csv',json={'files':files}).status_code==422
    assert client.get('/api/students/DEMO0001').json()['record']['overall_score']==68

def test_new_marks_and_attendance_feed_score(client):
    aid=setup_class(client);signin(client,'teacher@test.edu');day=date.today().isoformat()
    post(client,'/api/v4/marks/batch',{'assignment_id':aid,'exam_name':'Mid','exam_date':day,'maximum':50,'items':[{'student_id':'S001','marks':20}]})
    post(client,'/api/v4/attendance/batch',{'assignment_id':aid,'on_date':day,'time_slot':'09:00-10:00','topic':'Graphs','items':[{'student_id':'S001','present':False}]})
    detail=client.get('/api/students/S001').json()['record']
    assert detail['A']==40 and detail['T']==0
    assert detail['academic_flag']=='Support needed'
    assert detail['overall_score'] is None and detail['backlog_count'] is None
    assert client.post('/api/admin/demo-data').status_code==403

def test_demo_empty_guard_and_model(client):
    signin(client,'admin@test.edu');post(client,'/api/admin/demo-data',{})
    assert client.post('/api/admin/demo-data').status_code==409
    post(client,'/api/admin/ml/train',{'demo':True})
    result=client.get('/api/ml/predictions').json()
    assert result['trained'] and len(result['items'])==200
    assert result['model']['source']=='synthetic_demo'
