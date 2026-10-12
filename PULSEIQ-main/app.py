"""PULSEIQ entrypoint. Run: python -m streamlit run app.py"""
from datetime import date
import streamlit as st
from data_io import ROOT, load_directory, integrate
from scoring import CONFIG, score_dataset
import views

st.set_page_config(page_title='PULSEIQ · Student Success',page_icon='🧭',layout='wide')
views.style()


def set_dataset(result,label):
    if not result.ok or not result.periods:
        raise ValueError('A valid roster and at least one evidence period are required.')
    st.session_state.dataset=result
    st.session_state.dataset_label=label
    st.session_state.actions=[]
    st.session_state.history=[]
    st.session_state.period=result.periods[-1]
    st.session_state.analysis_date=date(2026,10,10)
    st.session_state.stale_days=CONFIG['stale_days']
    for key in list(st.session_state):
        if key.startswith(('filter_','profile_','scenario_','playbook_')) or key in ('edit_action','board_statuses'):
            del st.session_state[key]


def activate(result,label):
    # Defer widget resets until the next run, before any widgets are instantiated.
    st.session_state.pending_activation=(result,label)
    st.rerun()


if 'pending_activation' in st.session_state:
    result,label=st.session_state.pop('pending_activation')
    set_dataset(result,label)
if 'dataset' not in st.session_state:
    set_dataset(load_directory(ROOT/'demo_data'),'Synthetic college demo · 200 students')

with st.sidebar:
    st.title('PULSEIQ')
    st.caption('Student Success Intelligence')
    st.write('**Institutional demo**')
    st.caption(st.session_state.dataset_label)
    page=st.radio('Workspace',['Overview','Import & data quality','Student Profile','Action Board','What-if Simulator','Method & architecture','Real academic benchmark'],key='workspace_page')
    st.divider()
    st.caption('Switching datasets or resetting clears session actions. Export your work first.')
    if st.button('Load synthetic demo',width='stretch'):
        st.session_state.pop('last_validation',None)
        activate(load_directory(ROOT/'demo_data'),'Synthetic college demo · 200 students')
        st.rerun()
    if st.button('Reset session',width='stretch'):
        for key in list(st.session_state):
            del st.session_state[key]
        st.rerun()
    st.divider()
    period=st.selectbox('Reporting period',st.session_state.dataset.periods,key='period')
    analysis=st.date_input('Analysis date',key='analysis_date',help='Demo reference date starts at 10 October 2026. Change it to test stale evidence.')
    stale=st.number_input('Freshness window (days)',min_value=0,max_value=365,step=1,key='stale_days')

joined=integrate(st.session_state.dataset,period,analysis,int(stale))
scored=score_dataset(joined)
st.session_state.joined=joined
with st.sidebar:
    st.subheader('Cohort filters')
    departments=st.multiselect('Department',sorted(scored.department.unique()),default=sorted(scored.department.unique()),key='filter_department')
    semesters=st.multiselect('Semester',sorted(int(v) for v in scored.semester.unique()),default=sorted(int(v) for v in scored.semester.unique()),key='filter_semester')
    segment=st.selectbox('Support segment',['All','Strong academics with placement gap','Academic support','Placement support','Dual support','Currently on track','Insufficient evidence','Support requested'],key='filter_segment')
    st.caption('View selectors are not access controls. This prototype has no authentication or student portal.')

frame=scored[scored.department.isin(departments)&scored.semester.isin(semesters)].copy()
if segment=='Support requested':
    frame=frame[frame.support_request]
elif segment!='All':
    frame=frame[frame.segments.map(lambda items:segment in items)]

st.caption(f"{st.session_state.dataset_label} · Period {period} · Analysis {analysis} · {CONFIG['scoring_version']} · {len(frame)} students in view")
if joined.data_age_days.iloc[0] < 0:
    st.warning('This reporting period is after the analysis date. Future-dated evidence is excluded from scoring.')
elif joined.data_age_days.iloc[0] > stale:
    st.warning('This reporting period is stale for the chosen analysis date. Stale evidence is visible but excluded from scores and support rules.')

if page=='Overview':views.overview(frame)
elif page=='Import & data quality':views.import_view(activate)
elif page=='Student Profile':views.profile(frame)
elif page=='Action Board':views.action_board(frame)
elif page=='What-if Simulator':views.simulator(frame)
elif page=='Method & architecture':views.methodology()
elif page=='Real academic benchmark':views.research(activate)
st.divider()
st.caption('PULSEIQ · Explainable support indicators, not outcome predictions. Session data is temporary; download exports before leaving.')
