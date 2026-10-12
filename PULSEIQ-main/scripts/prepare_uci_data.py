"""Download UCI 697 and retain an academic-only derivative with attribution.
Never create fake attendance, placement or feedback for real study participants.
"""
import hashlib
import io
import json
from pathlib import Path
import sys
import urllib.request
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
URL='https://archive.ics.uci.edu/static/public/697/predict+students+dropout+and+academic+success.zip'


def prepare(raw):
    original=pd.read_csv(io.BytesIO(raw),sep=';')
    keep=['Course','Curricular units 1st sem (enrolled)','Curricular units 1st sem (evaluations)',
          'Curricular units 1st sem (approved)','Curricular units 1st sem (grade)',
          'Curricular units 2nd sem (enrolled)','Curricular units 2nd sem (evaluations)',
          'Curricular units 2nd sem (approved)','Curricular units 2nd sem (grade)','Target']
    derivative=original[keep].copy()
    derivative.insert(0,'record_id',[f'UCI{i:05}' for i in range(1,len(derivative)+1)])
    derivative.to_csv(ROOT/'benchmark_data'/'uci_academic_subset.csv',index=False)
    # Reproducible uniform sample; two artificial reporting dates allow use of the importer.
    sample=derivative.sample(n=min(400,len(derivative)),random_state=42).sort_index()
    out=ROOT/'benchmark_data'/'import_sample'
    out.mkdir(exist_ok=True)
    pd.DataFrame({'student_id':sample.record_id,'department':'UCI course '+sample.Course.astype(str),
                  'semester':2}).to_csv(out/'students.csv',index=False)
    periods={1:'2026-08-31',2:'2026-09-30'}
    records=[]
    for _,row in sample.iterrows():
        for sem,period in periods.items():
            grade=row[f'Curricular units {sem}'+('st' if sem==1 else 'nd')+' sem (grade)']
            evaluations=row[f'Curricular units {sem}'+('st' if sem==1 else 'nd')+' sem (evaluations)']
            # Grade scale 0-20. Zero grade/no evaluations treated as unavailable, not zero achievement.
            marks=float(grade)*5 if evaluations>0 and grade>0 else np.nan
            records.append(dict(student_id=row.record_id,period_end=period,marks_pct=marks,backlog_count=np.nan))
    pd.DataFrame(records).to_csv(out/'academic.csv',index=False)
    metadata={'dataset':'Predict Students\u2019 Dropout and Academic Success','uci_id':697,
              'doi':'10.24432/C5MC89','license':'CC BY 4.0','retrieved_on':'2026-10-10',
              'source_url':URL,'source_sha256':hashlib.sha256(raw).hexdigest(),
              'source_rows':len(original),'derivative_rows':len(derivative),'sample_students':len(sample),
              'changes':['Retained academic variables, course code and outcome only.',
                         'Added row identifiers; these are not original student IDs.',
                         'Removed demographics, financial, nationality and family attributes.',
                         'Sample adapter: grades multiplied by five; zero/no evaluation becomes missing.',
                         'Backlogs remain unknown; unapproved units are not assumed to be backlogs.',
                         'Reporting dates are artificial demo labels, not actual study dates.',
                         'No missing source category is fabricated; no predictor is trained.']}
    (ROOT/'benchmark_data'/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(f'Prepared {len(derivative)} real academic records and a {len(sample)}-student importer sample.')

if __name__=='__main__':
    if len(sys.argv)>1:
        prepare(Path(sys.argv[1]).read_bytes())
    else:
        archive=zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(URL,timeout=60).read()))
        prepare(archive.read('data.csv'))
