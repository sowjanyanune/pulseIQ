from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]


def app():
    return AppTest.from_file(str(ROOT/'app.py'),default_timeout=20).run()


def test_all_screens_and_empty_filters():
    at=app()
    assert not at.exception
    assert at.metric[0].value=='200'
    for page in ['Import & data quality','Student Profile','Action Board','What-if Simulator','Method & architecture','Real academic benchmark']:
        at.radio(key='workspace_page').set_value(page).run()
        assert not at.exception, page
    at.radio(key='workspace_page').set_value('Overview').run()
    at.multiselect(key='filter_department').set_value([]).run()
    assert not at.exception
    assert any('No students match' in item.value for item in at.info)


def test_profile_action_review_reopen_and_independent_session():
    at=app()
    at.radio(key='workspace_page').set_value('Student Profile').run()
    at.selectbox(key='profile_student').set_value('DEMO001').run()
    at.selectbox(key='playbook_DEMO001').set_value('Schedule coding practice and a mock coding assessment.').run()
    at.text_input[0].set_value('Mentor CS-1')
    next(x for x in at.button if x.label=='Create support action').click().run()
    assert not at.exception
    assert len(at.session_state.actions)==1
    independent=app()
    assert independent.session_state.actions==[]
    at.radio(key='workspace_page').set_value('Action Board').run()
    # Only the form Status selectbox, not the cohort support segment.
    next(x for x in at.selectbox if x.label=='Status').set_value('Reviewed')
    next(x for x in at.text_area if x.label=='Review note').set_value('Mock assessment reviewed.')
    next(x for x in at.button if x.label=='Save action revision').click().run()
    assert not at.exception
    assert at.session_state.actions[0]['status']=='Reviewed'
    next(x for x in at.selectbox if x.label=='Status').set_value('In progress')
    next(x for x in at.text_area if x.label=='Review note').set_value('Follow-up scheduled.')
    next(x for x in at.button if x.label=='Save action revision').click().run()
    assert not at.exception
    assert at.session_state.history[-1]['event']=='Reopened'
    assert len(at.session_state.history)==3


def test_simulator_and_dataset_switch():
    at=app()
    at.radio(key='workspace_page').set_value('What-if Simulator').run()
    baseline=at.session_state.joined.copy(deep=True)
    at.slider(key='scenario_DEMO001_coding_pct').set_value(90.0).run()
    assert not at.exception
    assert at.session_state.joined.equals(baseline)
    at.radio(key='workspace_page').set_value('Real academic benchmark').run()
    next(x for x in at.button if x.label=='Load 400-student academic-only sample').click().run()
    assert not at.exception
    assert len(at.session_state.joined)==400
    at.radio(key='workspace_page').set_value('Overview').run()
    assert any('No overall scores' in x.value for x in at.info)
    next(x for x in at.button if x.label=='Load synthetic demo').click().run()
    assert not at.exception
    assert len(at.session_state.joined)==200
