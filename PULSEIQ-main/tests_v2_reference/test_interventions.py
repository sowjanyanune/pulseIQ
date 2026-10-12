import pytest
from interventions import create_action,update_action,action_frame,history_frame


def test_create_review_reopen_history_does_not_replace_notes():
    actions,history=create_action([],[],student_id='DEMO001',owner_alias='Mentor A',action='Coding practice',due_date='2026-10-20',rationale='coding_pct=40')
    ident=actions[0]['intervention_id']
    actions,history=update_action(actions,history,ident,owner_alias='Mentor A',action='Coding practice',due_date='2026-10-20',status='Reviewed',review_note='Reviewed mock assessment.')
    actions,history=update_action(actions,history,ident,owner_alias='Mentor A',action='More practice',due_date='2026-10-25',status='In progress',review_note='Student requested follow-up.')
    assert len(actions)==1 and len(history)==3
    assert history[1]['review_note']=='Reviewed mock assessment.'
    assert history[2]['event']=='Reopened'
    assert len(action_frame(actions))==1 and len(history_frame(history))==3


def test_validation_and_session_separation():
    with pytest.raises(ValueError):create_action([],[],student_id='DEMO001',owner_alias='',action='Practice',due_date='2026-10-20')
    actions,history=create_action([],[],student_id='DEMO001',owner_alias='Mentor',action='Practice',due_date='2026-10-20')
    with pytest.raises(ValueError):update_action(actions,history,actions[0]['intervention_id'],owner_alias='Mentor',action='Practice',due_date='2026-10-20',status='Closed',review_note='')
    other_actions,other_history=create_action([],[],student_id='DEMO002',owner_alias='Mentor B',action='Interview',due_date='2026-10-20')
    assert len(actions)==len(other_actions)==1
    assert other_actions[0]['student_id']=='DEMO002'
    assert history[0]['student_id']=='DEMO001'
