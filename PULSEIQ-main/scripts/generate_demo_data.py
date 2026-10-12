"""Reproducible fictional college records. Run from any directory."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from data_io import SCHEMAS


def generate():
    rng = np.random.default_rng(42)
    ids = [f'DEMO{i:03}' for i in range(1, 201)]
    departments = ['Computer Science', 'Electronics', 'Mechanical', 'Business']
    roster = pd.DataFrame({'student_id': ids, 'department': [departments[(i-1)%4] for i in range(1,201)],
                           'semester': [4 if i%2 else 6 for i in range(1,201)]})
    tables = {key: [] for key in SCHEMAS if key != 'students'}
    clip = lambda n: round(float(np.clip(n, 0, 100)), 1)
    for period in ['2026-08-31', '2026-09-30']:
        for i, sid in enumerate(ids):
            academic = clip(rng.normal(70, 17))
            coding = clip(academic + rng.normal(-10, 20))
            data = {
                'academic': dict(marks_pct=academic, backlog_count=int(academic<45)),
                'attendance': dict(classes_attended=int(rng.integers(24, 41)), classes_held=40),
                'lms': dict(assignments_completed=int(rng.integers(5, 11)), assignments_assigned=10),
                'placement': dict(aptitude_pct=clip(rng.normal(67, 18)), coding_pct=coding, interview_pct=clip(rng.normal(68, 16))),
                'skills': dict(technical_pct=clip(rng.normal(70, 15)), communication_pct=clip(rng.normal(72, 13))),
                'engagement': dict(activities_completed=int(rng.integers(0, 6)), activities_available=5),
                'feedback': dict(support_requested=bool(i%17==0), support_category='Academic' if i%17==0 else 'None'),
            }
            # Named fixtures have deliberate values in both periods.
            if i < 7:
                data = {
                    'academic': dict(marks_pct=80, backlog_count=0),
                    'attendance': dict(classes_attended=36, classes_held=40),
                    'lms': dict(assignments_completed=7, assignments_assigned=10),
                    'placement': dict(aptitude_pct=40, coding_pct=40, interview_pct=40),
                    'skills': dict(technical_pct=60, communication_pct=60),
                    'engagement': dict(activities_completed=1, activities_available=2),
                    'feedback': dict(support_requested=False, support_category='None'),
                }
                if i==1: # Academic support only
                    data['academic']=dict(marks_pct=42,backlog_count=1)
                    data['attendance']['classes_attended']=26
                    data['placement']=dict(aptitude_pct=80,coding_pct=80,interview_pct=80)
                if i==2: # Dual support
                    data['academic']=dict(marks_pct=45,backlog_count=1)
                    data['attendance']['classes_attended']=28
                if i==3: # Fully on track
                    data['academic']['marks_pct']=85
                    data['lms']['assignments_completed']=9
                    data['placement']=dict(aptitude_pct=80,coding_pct=85,interview_pct=80)
                if i==4: # Placement absent: 75% coverage
                    data['placement']=dict(aptitude_pct=None,coding_pct=None,interview_pct=None)
                if i==5: # Engagement absent: 95% coverage
                    data['engagement']=dict(activities_completed=0,activities_available=0)
                if i==6: # Request despite no observed trigger
                    data['placement']=dict(aptitude_pct=80,coding_pct=80,interview_pct=80)
                    data['feedback']=dict(support_requested=True,support_category='Other')
            if i >= 7 and i % 29 == 0:
                data['skills']['communication_pct']=None
            if i >= 7 and i % 31 == 0:
                data['lms']=dict(assignments_completed=0,assignments_assigned=0)
            for source, values in data.items():
                tables[source].append(dict(student_id=sid,period_end=period,**values))
    frames = {'students': roster, **{k: pd.DataFrame(v) for k,v in tables.items()}}
    for source,frame in frames.items():
        frame.to_csv(ROOT/'demo_data'/f'{source}.csv',index=False)
        pd.DataFrame(columns=SCHEMAS[source]).to_csv(ROOT/'templates'/f'{source}.csv',index=False)
    invalid=frames['academic'].iloc[:3].copy()
    invalid.loc[invalid.index[0],'marks_pct']=120
    invalid.loc[invalid.index[1],'backlog_count']=-1
    invalid=pd.concat([invalid,invalid.iloc[[2]]],ignore_index=True)
    invalid.to_csv(ROOT/'fixtures'/'invalid'/'academic.csv',index=False)
    frames['students'].iloc[:3].to_csv(ROOT/'fixtures'/'invalid'/'students.csv',index=False)
    unmatched=frames['attendance'].iloc[:1].copy()
    unmatched['student_id']='UNKNOWN'
    unmatched.to_csv(ROOT/'fixtures'/'invalid'/'attendance_unmatched.csv',index=False)
    print('Generated 200 fictional students, two periods, eight CSVs and validation fixtures.')

if __name__ == '__main__':
    generate()
