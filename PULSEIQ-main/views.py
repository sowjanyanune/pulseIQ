"""Streamlit views: cohort insights, evidence, review actions and scenarios."""
from __future__ import annotations
from datetime import date, timedelta
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from data_io import ROOT, SCHEMAS, import_files, csv_bytes, templates_zip
from scoring import CONFIG, COMPONENTS, component_breakdown, simulate, export_scores
from interventions import STATUSES, create_action, update_action, action_frame, history_frame

TEAL = '#0c8b83'
NAVY = '#17324d'


def style():
    st.markdown('''<style>
    .stApp {background:#f7f9fc;color:#17324d;}
    [data-testid="stSidebar"] {background:#eef3f8;}
    .block-container {padding-top:4rem;max-width:1250px;}
    h1,h2,h3 {letter-spacing:-.035em;}
    [data-testid="stMetric"] {background:white;border:1px solid #dce5ed;border-radius:12px;padding:15px;}
    [data-testid="stMetricLabel"] {color:#52687b;}
    .stButton>button[kind="primary"] {background:#0c8b83;border-color:#0c8b83;}
    </style>''', unsafe_allow_html=True)


def chart(figure, key):
    figure.update_layout(font=dict(family='Arial', color=NAVY), paper_bgcolor='rgba(0,0,0,0)',
                         plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=15,r=15,t=40,b=15))
    st.plotly_chart(figure, use_container_width=True, key=key)


def score_text(value):
    return 'Unavailable' if value is None or pd.isna(value) else f'{value:.1f}'


def overview(frame):
    st.title('Student success, with a clear next step')
    st.caption('Identify support needs · inspect evidence · agree on an action')
    if frame.empty:
        st.info('No students match these filters. Select another department, semester or support segment.')
        return
    cols=st.columns(4)
    cols[0].metric('Students in this cohort',len(frame))
    cols[1].metric('Academic support',int(frame.academic_flag.eq('Support needed').sum()))
    cols[2].metric('Placement support',int(frame.placement_flag.eq('Support needed').sum()))
    cols[3].metric('Support requests',int(frame.support_request.sum()))
    st.subheader('Check evidence coverage first')
    counts=frame.score_status.value_counts()
    st.write(f"**Complete:** {counts.get('Complete',0)} · **Provisional:** {counts.get('Provisional',0)} · **Insufficient data:** {counts.get('Insufficient data',0)}")
    left,right=st.columns(2)
    with left:
        st.subheader('Support segments')
        segments=frame.segments.explode().value_counts().rename_axis('segment').reset_index(name='students')
        chart(px.bar(segments,x='students',y='segment',orientation='h',color_discrete_sequence=[TEAL]),'segments')
        st.caption('Segments overlap. One student may appear in several bars; do not sum them as cohort totals.')
    with right:
        st.subheader('Score distribution by evidence status')
        scored=frame[frame.score_status.ne('Insufficient data')]
        if scored.empty:
            st.info('No overall scores meet the minimum evidence coverage.')
        else:
            chart(px.histogram(scored,x='overall_score',color='score_status',barmode='group',nbins=15,
                               color_discrete_map={'Complete':TEAL,'Provisional':'#e5a636'},
                               labels={'overall_score':'Support indicator (0–100)','score_status':'Evidence status'}),'scores')
        st.caption('A score is a support indicator. Provisional scores rescale available weights and are shown separately.')
    st.subheader('Cohort review list')
    st.caption('Listed by student ID, with no student ranking. Use Student Profile to inspect the source evidence.')
    display=export_scores(frame)[['student_id','department','semester','overall_score','score_status','coverage',
                                  'academic_flag','placement_flag','support_request','segments']].sort_values('student_id')
    st.dataframe(display,hide_index=True,width='stretch',
                 column_config={'coverage':st.column_config.ProgressColumn('Evidence coverage',min_value=0,max_value=1,format='%.2f'),
                                'overall_score':st.column_config.NumberColumn('Success Score',format='%.1f')})
    st.download_button('Download cohort evidence CSV',csv_bytes(export_scores(frame)),file_name='pulseiq_cohort_evidence.csv',mime='text/csv')


def import_view(activate):
    st.title('Import & data quality')
    st.write('The institution supplies these files. Students do not upload their education history.')
    st.info('This public prototype is for synthetic or appropriately de-identified samples. Uploads and actions stay in this session; export before resetting or leaving.')
    st.download_button('Download all eight CSV templates',templates_zip(),'pulseiq_csv_templates.zip','application/zip')
    with st.expander('Required fields and file limits'):
        st.write('UTF-8, comma-delimited CSV · up to 5 MiB and 1,000 rows per file · one roster and seven optional evidence sources.')
        st.dataframe(pd.DataFrame([{'file':k+'.csv','columns':', '.join(v)} for k,v in SCHEMAS.items()]),hide_index=True,width='stretch')
        st.write('Only students.csv is mandatory. Missing sources remain unknown. Use student_id + period_end as the unique source key; dates must use YYYY-MM-DD.')
    uploads={}
    with st.form('import_form'):
        st.subheader('Select source files')
        cols=st.columns(2)
        for i,source in enumerate(SCHEMAS):
            with cols[i%2]:
                uploads[source]=st.file_uploader(source+'.csv',type=['csv'],key='upload_'+source)
        acknowledged=st.checkbox('I confirm these are synthetic or appropriately de-identified demonstration records.')
        submitted=st.form_submit_button('Validate and activate files',type='primary')
    if submitted:
        if not acknowledged:
            st.error('Confirm the demonstration data scope before importing.')
        elif not uploads['students']:
            st.error('Select a students.csv roster first.')
        else:
            with st.spinner('Validating schemas, values and joins…'):
                result=import_files({source:(file.name,file.getvalue()) for source,file in uploads.items() if file is not None})
            st.session_state.last_validation=result
            if result.ok and result.periods:
                activate(result,'Uploaded demonstration files')
                st.success('Import accepted. Use Overview or Student Profile to review the evidence.')
            elif result.ok:
                st.error('No reporting periods were found. Supply at least one evidence CSV with period_end.')
            else:
                st.error('Import blocked. Fix the errors below and upload again. The previous dataset is still active.')
    result=st.session_state.get('last_validation',st.session_state.dataset)
    st.subheader('Most recent validation batch')
    st.dataframe(result.summary,hide_index=True,width='stretch')
    if result.report.empty:
        st.success('No validation errors or warnings in this batch.')
    else:
        severity=st.selectbox('Validation messages',['All','error','warning'],key='quality_severity')
        messages=result.report if severity=='All' else result.report[result.report.severity.eq(severity)]
        st.dataframe(messages,hide_index=True,width='stretch')
        st.download_button('Download validation report',csv_bytes(result.report),'pulseiq_validation_report.csv','text/csv')
    st.subheader('Active period source coverage')
    joined=st.session_state.joined
    stats=[]
    for source in list(SCHEMAS)[1:]:
        present=int(joined[f'{source}__present'].sum())
        fresh=int(joined[f'{source}__fresh'].sum())
        stats.append(dict(source=source,students=len(joined),present=present,missing=len(joined)-present,fresh=fresh,stale_or_future=present-fresh))
    st.dataframe(pd.DataFrame(stats),hide_index=True,width='stretch')
    st.caption('Present means a row exists for this exact reporting period. Freshness and valid constituent values determine score coverage. Earlier records are never silently substituted.')


def student_picker(frame,key):
    if frame.empty:
        st.info('No students match the current filters.')
        return None
    options=sorted(frame.student_id.tolist())
    sid=st.selectbox('Student ID',options,key=key)
    return frame.loc[frame.student_id.eq(sid)].iloc[0].to_dict()


def action_create(record):
    st.subheader('Agree on a support action')
    recs=record['recommendations']
    options=['Custom support action']+[r['action'] for r in recs]
    choice=st.selectbox('Support playbook',options,key='playbook_'+record['student_id'])
    recommendation=next((r for r in recs if r['action']==choice),None)
    rationale=recommendation['trigger'] if recommendation else 'Faculty-selected action; review student evidence.'
    st.caption('Rationale: '+rationale)
    with st.form('create_'+record['student_id']):
        owner=st.text_input('Owner alias',placeholder='e.g. Mentor CS-1',max_chars=80)
        action=st.text_area('Editable action',value=recommendation['action'] if recommendation else '',max_chars=2000)
        due=st.date_input('Review due date',value=date.today()+timedelta(days=7))
        submit=st.form_submit_button('Create support action',type='primary')
    if submit:
        try:
            actions,history=create_action(st.session_state.actions,st.session_state.history,student_id=record['student_id'],
                                         owner_alias=owner,action=action,due_date=due,rationale=rationale)
            st.session_state.actions,st.session_state.history=actions,history
            st.success('Action created. Review it on the Action Board and export your session records.')
        except ValueError as exc:
            st.error(str(exc))


def profile(frame):
    st.title('Student Profile')
    record=student_picker(frame,'profile_student')
    if record is None:
        return
    st.write(f"**{record['student_id']}** · {record['department']} · Semester {int(record['semester'])}")
    cols=st.columns(3)
    cols[0].metric('Student Success Score',score_text(record['overall_score']))
    cols[1].metric('Evidence coverage',f"{record['coverage']:.0%}")
    cols[2].metric('Score status',record['score_status'])
    st.caption(f"Data period: {record['period_end']} · Analysis date: {record['analysis_date']} · Scoring: {record['scoring_version']}")
    if record['score_status']=='Provisional':
        st.warning('Provisional: the weighted sum is divided by available coverage. This rescaling is not comparable to a complete score for ranking.')
    elif record['score_status']=='Insufficient data':
        st.warning('Insufficient data: less than 80% of component weight is available and fresh. No overall score is displayed.')
    left,right=st.columns(2)
    with left:
        st.subheader('Academic support')
        st.write(('⚠️ ' if record['academic_flag']=='Support needed' else 'ℹ️ ')+record['academic_flag'])
        for reason in record['academic_reasons']:
            st.write('• '+reason)
    with right:
        st.subheader('Placement support')
        st.write(('⚠️ ' if record['placement_flag']=='Support needed' else 'ℹ️ ')+record['placement_flag'])
        for reason in record['placement_reasons']:
            st.write('• '+reason)
    st.write('**Segments:** '+', '.join(record['segments']))
    if record['support_request']:
        st.info(f"Support request: {record.get('support_category')}. This request does not reduce the score.")
    st.subheader('Where the score comes from')
    breakdown=component_breakdown(record)
    chart(px.bar(breakdown.dropna(subset=['value']),x='component',y='value',range_y=[0,100],
                 color_discrete_sequence=[TEAL],labels={'component':'','value':'Component score'}),'components')
    st.dataframe(breakdown,hide_index=True,width='stretch',
                 column_config={'weight':st.column_config.NumberColumn('Weight',format='%.2f'),
                                'value':st.column_config.NumberColumn('Component score',format='%.2f'),
                                'weighted_points':st.column_config.NumberColumn('Original weighted points',format='%.2f'),
                                'effective_points':st.column_config.NumberColumn('Points after coverage rescaling',format='%.2f')})
    with st.expander('Inspect raw source values and provenance'):
        rows=[]
        for source,fields in list(SCHEMAS.items())[1:]:
            present=record.get(f'{source}__present',False)
            fresh=record.get(f'{source}__fresh',False)
            state='Fresh' if fresh else ('Stale or future' if present else 'Missing')
            for field in fields[2:]:
                rows.append(dict(source=source,field=field,value=str(record.get(field)),status=state,
                                 period=record.get(f'{source}__period_end'),filename=record.get(f'{source}__filename'),
                                 imported_at=record.get(f'{source}__imported_at')))
        st.dataframe(pd.DataFrame(rows),hide_index=True,width='stretch')
    action_create(record)
    st.subheader('This student’s intervention history')
    events=history_frame(st.session_state.history)
    st.dataframe(events.loc[events.student_id.eq(record['student_id'])],hide_index=True,width='stretch')


def action_board(frame):
    st.title('Action Board')
    st.write('Assign an owner, agree on an action and record what was reviewed. Faculty make the final decision.')
    st.info('Actions and revision history are session-only. Download both files before resetting or leaving.')
    ids=set(frame.student_id)
    actions=action_frame(st.session_state.actions)
    visible=actions.loc[actions.student_id.isin(ids)].copy()
    if len(actions)>len(visible):
        st.caption(f'{len(actions)-len(visible)} actions are outside the current cohort filters.')
    statuses=st.multiselect('Action statuses',STATUSES,default=STATUSES,key='board_statuses')
    visible=visible[visible.status.isin(statuses)]
    if visible.empty:
        st.info('No actions match these filters. Create one from a Student Profile, or adjust your filters.')
        return
    overdue=visible.status.isin(['Planned','In progress']) & pd.to_datetime(visible.due_date).dt.date.lt(date.today())
    cols=st.columns(3)
    cols[0].metric('Visible actions',len(visible))
    cols[1].metric('Overdue reviews',int(overdue.sum()))
    cols[2].metric('Reviewed or closed',int(visible.status.isin(['Reviewed','Closed']).sum()))
    st.dataframe(visible,hide_index=True,width='stretch')
    selected=st.selectbox('Choose an action to edit',visible.intervention_id.tolist(),
                          format_func=lambda v: f"{v} · {visible.loc[visible.intervention_id.eq(v),'student_id'].iloc[0]}",key='edit_action')
    current=visible.loc[visible.intervention_id.eq(selected)].iloc[0].to_dict()
    with st.form('edit_'+selected):
        owner=st.text_input('Owner alias',value=current['owner_alias'],max_chars=80)
        action=st.text_area('Action',value=current['action'],max_chars=2000)
        due=st.date_input('Due date',value=date.fromisoformat(current['due_date']))
        status=st.selectbox('Status',STATUSES,index=STATUSES.index(current['status']))
        note=st.text_area('Review note',value=current['review_note'],max_chars=2000)
        save=st.form_submit_button('Save action revision',type='primary')
    if save:
        try:
            st.session_state.actions,st.session_state.history=update_action(st.session_state.actions,st.session_state.history,selected,
                                                                          owner_alias=owner,action=action,due_date=due,status=status,review_note=note)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    st.download_button('Export visible actions CSV',csv_bytes(visible),'pulseiq_actions.csv','text/csv')
    history=history_frame(st.session_state.history)
    history=history.loc[history.intervention_id.isin(visible.intervention_id)]
    st.download_button('Export action revision history CSV',csv_bytes(history),'pulseiq_action_history.csv','text/csv')
    st.dataframe(history,hide_index=True,width='stretch')


def simulator(frame):
    st.title('What-if Simulator')
    st.info('Illustrative score change, not a prediction of improvement. Scenario inputs never overwrite source records.')
    record=student_picker(frame,'scenario_student')
    if record is None:
        return
    changes={}
    fields={'marks_pct':('Academic marks (%)','academic',100),
            'classes_attended':('Classes attended','attendance',record.get('classes_held')),
            'assignments_completed':('Assignments completed','lms',record.get('assignments_assigned')),
            'aptitude_pct':('Aptitude (%)','placement',100), 'coding_pct':('Coding (%)','placement',100),
            'interview_pct':('Interview (%)','placement',100)}
    for field,(label,source,maximum) in fields.items():
        value=record.get(field)
        if not record.get(f'{source}__fresh') or pd.isna(value) or pd.isna(maximum):
            continue
        key='scenario_'+record['student_id']+'_'+field
        is_count=field in ('classes_attended','assignments_completed')
        if is_count:
            changes[field]=st.number_input(label,min_value=0,max_value=int(maximum),value=int(value),step=1,key=key)
        else:
            changes[field]=st.slider(label,0.0,float(maximum),float(value),step=1.0,key=key)
    if not changes:
        st.warning('This student has no fresh, observed indicators available for a scenario.')
        return
    scenario=simulate(record,changes)
    left,right=st.columns(2)
    with left:
        st.subheader('Baseline')
        st.metric(record['score_status'],score_text(record['overall_score']))
        st.write('Academic: '+record['academic_flag'])
        st.write('Placement: '+record['placement_flag'])
    with right:
        st.subheader('Scenario')
        delta=None if record['overall_score'] is None or pd.isna(record['overall_score']) or scenario['overall_score'] is None else round(scenario['overall_score']-record['overall_score'],2)
        st.metric(scenario['score_status'],score_text(scenario['overall_score']),delta=delta)
        st.write('Academic: '+scenario['academic_flag'])
        st.write('Placement: '+scenario['placement_flag'])
    compare=pd.DataFrame([dict(component=COMPONENTS[k][0],baseline=record[k],scenario=scenario[k]) for k in COMPONENTS])
    st.dataframe(compare,hide_index=True,width='stretch')
    out=export_scores(pd.DataFrame([scenario]));out['export_type']='Illustrative scenario; not a prediction'
    st.download_button('Export scenario separately',csv_bytes(out),'pulseiq_scenario.csv','text/csv')
    if st.button('Reset scenario inputs'):
        for key in list(st.session_state):
            if key.startswith('scenario_'+record['student_id']+'_'):
                del st.session_state[key]
        st.rerun()


def methodology():
    st.title('Method & architecture')
    st.write('PULSEIQ is an institution-focused hackathon prototype. The implemented decision engine uses transparent rules; it does not contain a trained dropout or placement predictor.')
    st.code('Browser → Streamlit → CSV validation → Period-safe join → Rules engine → Evidence & charts → Action Board → Exports',language=None)
    st.subheader('Student Success Score')
    st.latex(r'Score = 0.30A + 0.20T + 0.15L + 0.25P + 0.05S + 0.05E')
    st.dataframe(pd.DataFrame([{'symbol':k,'component':v[0],'weight':CONFIG['weights'][k]} for k,v in COMPONENTS.items()]),hide_index=True)
    st.write('A = marks; T = attendance percentage; L = assignment completion; P = mean of aptitude, coding and interview; S = mean of technical and communication assessments; E = activity completion.')
    st.write('P and S require all constituents. Zero denominators are unknown. Stale or future records are excluded. Coverage is the sum of available component weights. Below 80% there is no overall score; partial coverage at or above 80% is provisional and divides the weighted sum by coverage.')
    st.write('**Academic support:** marks < 50, attendance < 75%, or backlogs > 0. **Placement support:** placement mean < 60 or coding < 50. A known trigger stays visible with missing evidence; absent triggers are Undetermined when required evidence is missing.')
    st.write('**Currently on track** means all required support-flag fields are fresh and observed, with no rule trigger. It does not mean every optional score component is complete or that success is guaranteed.')
    st.write('Thresholds are prototype defaults for faculty review. Feedback requests never reduce a score. LMS activity may reflect access barriers; recommendations need context and human review.')
    st.json(CONFIG)
    st.subheader('Delivery stages')
    st.dataframe(pd.DataFrame([
        ['1','Member 1','Project scaffold, dependency setup, GitHub workflow'],
        ['2','Member 2','CSV schemas, demo generator, validation and joins'],
        ['3','Member 3','Scores, coverage, support flags and evidence'],
        ['4','Member 4','Cohort dashboard, data quality and student profiles'],
        ['5','Member 5','Actions, review history, exports and tests'],
        ['6','Whole team','Integration, deployment validation and demo rehearsal']],columns=['Stage','Owner','Deliverable']),hide_index=True,width='stretch')
    st.caption('See docs/ARCHITECTURE.md and docs/TEAM_GUIDE.md for contracts, dependency order and detailed tasks.')


def research(activate):
    st.title('Real academic benchmark')
    st.write('UCI: Predict Students’ Dropout and Academic Success · 4,424 higher-education records · CC BY 4.0.')
    st.write('This separate benchmark contains observed academic data and outcomes. It does not contain the seven complete PULSEIQ categories. No missing categories have been invented, and outcomes are never used in PULSEIQ scoring.')
    path=ROOT/'benchmark_data'/'uci_academic_subset.csv'
    data=pd.read_csv(path,dtype={'record_id':str})
    left,right=st.columns(2)
    with left:
        counts=data.Target.value_counts().rename_axis('outcome').reset_index(name='records')
        chart(px.bar(counts,x='outcome',y='records',color_discrete_sequence=[TEAL]),'uci_outcomes')
    with right:
        grade='Curricular units 2nd sem (grade)'
        positive=data[data[grade]>0]
        chart(px.histogram(positive,x=grade,nbins=20,color_discrete_sequence=[TEAL]),'uci_grades')
        st.caption('Grade scale 0–20. Zero entries are excluded from this grade chart and treated as missing in the adapter.')
    st.dataframe(data.head(30),hide_index=True,width='stretch')
    st.download_button('Download academic-only UCI derivative',path.read_bytes(),'uci_academic_subset.csv','text/csv')
    st.write('The importer sample selects 400 students with seed 42. Grade percentages = grade × 5; backlogs remain unknown. Dates 2026-08-31 and 2026-09-30 are artificial reporting labels. Coverage is at most 30%, so no overall score can be assigned.')
    if st.button('Load 400-student academic-only sample',type='primary'):
        from data_io import load_directory
        activate(load_directory(ROOT/'benchmark_data'/'import_sample'),'UCI academic-only sample (artificial period dates)')
        st.rerun()
    st.markdown('Source: [UCI dataset 697](https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success) · [License](https://creativecommons.org/licenses/by/4.0/)')
    st.caption('Realinho, Vieira Martins, Machado and Baptista (2021). DOI: 10.24432/C5MC89. See DATA_SOURCES.md for modifications and limitations.')
