"""College-isolated academic retrieval, published faculty overrides and validated sync."""
from datetime import date
from uuid import uuid4
from sqlalchemy import select, insert, update, delete, and_
from fastapi import HTTPException
from .tenant_db import roster,subjects,entries,observations,logs,now
from .db import SCHEMAS
from .validation import validate_records, joined_records, InvalidSnapshot
from .scoring import score_dataset, component_breakdown
from .repository import clean


def audit(c,user,event,details=None):
    c.execute(insert(logs).values(id=str(uuid4()),college_id=user['college_id'],actor_id=user.get('id'),event=event,details=details or {},at=now()))


def visible_ids(c,user):
    cid=user['college_id']
    if user['role']=='admin':
        return {r[0] for r in c.execute(select(roster.c.id).where(roster.c.college_id==cid,roster.c.active==True))}
    if user['role']=='student':
        return {r[0] for r in c.execute(select(roster.c.id).where(roster.c.college_id==cid,roster.c.student_id==user['student_id'],roster.c.active==True))}
    assignments=c.execute(select(subjects.c.department,subjects.c.semester,subjects.c.section).where(subjects.c.college_id==cid,subjects.c.faculty_id==user['id'])).all()
    if not assignments: return set()
    allowed=set(assignments)
    return {r['id'] for r in c.execute(select(roster).where(roster.c.college_id==cid,roster.c.active==True)).mappings() if (r['department'],r['semester'],r['section']) in allowed}


def authorized_student(c,user,student_id):
    r=c.execute(select(roster).where(roster.c.college_id==user['college_id'],roster.c.student_id==student_id,roster.c.active==True)).mappings().first()
    if not r or r['id'] not in visible_ids(c,user): raise HTTPException(404,'Student not found in your authorized classes.')
    return r


def list_roster(engine,user):
    with engine.connect() as c:
        ids=visible_ids(c,user)
        if not ids:return []
        rows=c.execute(select(roster).where(roster.c.college_id==user['college_id'],roster.c.id.in_(ids)).order_by(roster.c.department,roster.c.student_id)).mappings().all()
        return clean([dict(r) for r in rows])


def academic(engine,user,period=None,stale_days=365):
    with engine.connect() as c:
        ids=visible_ids(c,user)
        if not ids: return [],[],None
        students=list(c.execute(select(roster).where(roster.c.college_id==user['college_id'],roster.c.id.in_(ids))).mappings())
        ids={r['id'] for r in students}
        canonical={'students':[{'student_id':r['student_id'],'department':r['department'],'semester':r['semester']} for r in students]}
        for kind in list(SCHEMAS)[1:]:canonical[kind]=[]
        obs=c.execute(select(observations).where(observations.c.college_id==user['college_id'],observations.c.roster_id.in_(ids))).mappings().all()
        bypk={r['id']:r['student_id'] for r in students}
        data={}
        for o in obs:
            item={**o['payload'],'student_id':bypk[o['roster_id']], 'period_end':o['period_end'].isoformat(),'source_name':o['source_name'],'imported_at':o['created_at'].isoformat()}
            data[(o['roster_id'],o['kind'],o['period_end'])]=item
        published=c.execute(select(entries).where(entries.c.college_id==user['college_id'],entries.c.roster_id.in_(ids),entries.c.status=='published')).mappings().all()
        aggregate={}
        for e in published:
            key=(e['roster_id'],'attendance' if e['kind']=='attendance' else 'academic',e['period_end'])
            aggregate.setdefault(key,[]).append(e)
        for key, group in aggregate.items():
            pk,kind,d=key
            base=data.get(key,{'student_id':bypk[pk],'period_end':d.isoformat()})
            if kind=='attendance':
                base.update(classes_attended=sum(x['attended'] or 0 for x in group),classes_held=sum(x['held'] or 0 for x in group))
            else:
                base.update(marks_pct=round(sum(x['marks_pct'] for x in group if x['marks_pct'] is not None)/len([x for x in group if x['marks_pct'] is not None]),2) if any(x['marks_pct'] is not None for x in group) else None)
                base.setdefault('backlog_count',0)
            base.update(source_name='published faculty entries',imported_at=now().isoformat())
            data[key]=base
        # Operational marks/attendance must feed the same score as imported snapshots.
        from .tenant_db import exam_results, class_sessions, class_attendance
        exams=c.execute(select(exam_results).where(exam_results.c.college_id==user['college_id'],exam_results.c.roster_id.in_(ids))).mappings().all()
        attendance_rows=c.execute(select(class_attendance.c.roster_id,class_attendance.c.present,class_sessions.c.on_date).join(class_sessions,class_attendance.c.session_id==class_sessions.c.id).where(class_attendance.c.college_id==user['college_id'],class_attendance.c.roster_id.in_(ids))).mappings().all()
        for pk in ids:
            for kind, records, datefield in [('academic',[x for x in exams if x['roster_id']==pk],'exam_date'),('attendance',[x for x in attendance_rows if x['roster_id']==pk],'on_date')]:
                for day in sorted({x[datefield] for x in records}):
                    group=[x for x in records if x[datefield]<=day]
                    previous=[(key[2],value) for key,value in data.items() if key[0]==pk and key[1]==kind and key[2]<=day]
                    base=dict(max(previous,key=lambda x:x[0])[1]) if previous else {'student_id':bypk[pk]}
                    base.update(period_end=day.isoformat(),source_name='faculty recorded '+kind,imported_at=now().isoformat())
                    if kind=='academic':
                        base.update(marks_pct=round(100*sum(x['marks'] for x in group)/sum(x['maximum'] for x in group),2))
                        base.setdefault('backlog_count',None) # An internal exam failure is not an official backlog.
                    else:
                        base.update(classes_held=len(group),classes_attended=sum(bool(x['present']) for x in group))
                    data[(pk,kind,day)]=base
        for (_,kind,_),row in data.items():
            if kind in canonical:
                canonical[kind].append({f:row.get(f) for f in SCHEMAS[kind]}|{'source_name':row.get('source_name'),'imported_at':row.get('imported_at')})
        periods=sorted({x['period_end'] for k in list(SCHEMAS)[1:] for x in canonical[k]})
        chosen=period or (periods[-1] if periods else date.today().isoformat())
        if period and period not in periods: raise HTTPException(400,'No data for that reporting period.')
        if (date.today()-date.fromisoformat(chosen)).days<0: raise HTTPException(400,'Reporting period cannot be in the future.')
        joined=joined_records(canonical,chosen,date.today(),stale_days)
        computed=score_dataset(joined).to_dict('records')
        detail={r['student_id']:r for r in students}
        result=[]
        for item in computed:
            r=clean(item)
            source=detail[r['student_id']]
            r.update(full_name=source['full_name'],email=source['email'],section=source['section'])
            result.append(r)
        return result,periods,chosen


def sync_records(engine,user,records,source_name):
    """Validate before changing anything. Imported snapshots never overwrite faculty entries."""
    normalized,report=validate_records(records)
    original={str(r['student_id']).strip():r for r in records['students']}
    cid=user['college_id']; stamp=now()
    with engine.begin() as c:
        known={r['student_id']:r for r in c.execute(select(roster).where(roster.c.college_id==cid)).mappings()}
        for s in normalized['students']:
            info=original[s['student_id']]
            # Imported email is informational, not an automatically provisioned login.
            fields=dict(full_name=str(info.get('full_name') or info.get('name') or s['student_id'])[:150],email=(str(info['email']).strip().lower()[:250] if info.get('email') else None),department=s['department'],semester=s['semester'],section=str(info.get('section') or 'A')[:50],active=True)
            if s['student_id'] in known:
                pk=known[s['student_id']]['id'];c.execute(update(roster).where(roster.c.id==pk).values(**fields))
            else:
                pk=str(uuid4());c.execute(insert(roster).values(id=pk,college_id=cid,student_id=s['student_id'],**fields));known[s['student_id']]={'id':pk}
        for kind in list(SCHEMAS)[1:]:
            for r in normalized[kind]:
                rid=known[r['student_id']]['id']; d=date.fromisoformat(r['period_end'])
                # Skip unrelated sources; upsert this category for this student and period.
                payload={f:r.get(f) for f in SCHEMAS[kind][2:]}
                current=c.execute(select(observations.c.id).where(observations.c.college_id==cid,observations.c.roster_id==rid,observations.c.kind==kind,observations.c.period_end==d)).scalar_one_or_none()
                v=dict(payload=payload,source_name=source_name,created_at=stamp)
                if current:c.execute(update(observations).where(observations.c.id==current).values(**v))
                else:c.execute(insert(observations).values(id=str(uuid4()),college_id=cid,roster_id=rid,kind=kind,period_end=d,**v))
        audit(c,user,'sync',{'source':source_name,'students':len(normalized['students']),'warnings':len(report)})
    return {'students':len(normalized['students']),'periods':sorted({r['period_end'] for k in list(SCHEMAS)[1:] for r in normalized[k]}),'warnings':report[:25],'source':source_name}
