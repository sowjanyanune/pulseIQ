"""Challenge-facing integration, trends and repeatable fictional demonstration."""
import csv
import io
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from .tenant_auth import identity, roles
from .tenant_db import roster
from .tenant_data import academic, sync_records
from .validation import InvalidSnapshot
from .db import SCHEMAS

class ImportData(BaseModel):
    files: dict[str, str]
    source_name: str = Field(default='CSV upload', min_length=1, max_length=150)

def install(app, engine):
    @app.post('/api/admin/import-csv')
    def import_csv(body: ImportData, user=Depends(identity)):
        roles(user, 'admin')
        if set(body.files)-set(SCHEMAS) or 'students' not in body.files:
            raise HTTPException(400, 'Include students.csv and only recognized category files.')
        if sum(len(v) for v in body.files.values()) > 8_000_000:
            raise HTTPException(413, 'Import limit is 8 MB.')
        records={}
        for name, content in body.files.items():
            reader=csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
            rows=list(reader)
            for row in rows:
                for key, value in row.items():
                    if value is not None and not value.strip(): row[key]=None
            records[name]=rows
        try: return sync_records(engine,user,records,body.source_name)
        except InvalidSnapshot as exc:
            raise HTTPException(422, {'message':str(exc),'report':exc.report})

    @app.post('/api/admin/demo-data')
    def demo(user=Depends(identity)):
        roles(user,'admin')
        with engine.connect() as c:
            if c.execute(select(func.count()).select_from(roster).where(roster.c.college_id==user['college_id'])).scalar_one():
                raise HTTPException(409,'Demo loading is only allowed in an empty college.')
        from .seed import generate
        return sync_records(engine,user,generate(200),'FICTIONAL challenge demo')

    @app.get('/api/analytics/trends')
    def trends(department: str | None=None, user=Depends(identity)):
        _, periods, _=academic(engine,user)
        points=[]
        for period in periods[-12:]:
            rows,_,_=academic(engine,user,period)
            if department: rows=[r for r in rows if r['department']==department]
            scores=[r['overall_score'] for r in rows if r['overall_score'] is not None]
            points.append(dict(period=period,mean_score=round(sum(scores)/len(scores),2) if scores else None,
                scored=len(scores),total=len(rows),support=sum(r['academic_flag']=='Support needed' or r['placement_flag']=='Support needed' for r in rows)))
        return {'items':points,'notice':'Available student cohort per period; descriptive trends, not intervention causal effects.'}
