from copy import deepcopy
import pandas as pd
import pytest
from data_io import integrate
from scoring import score_student,simulate,component_breakdown


def student(frame,sid):
    return frame.loc[frame.student_id.eq(sid)].iloc[0].to_dict()


def test_reference_68_and_independent_placement_flag(scored):
    row=student(scored,'DEMO001')
    assert row['overall_score']==68.0
    assert row['coverage']==1
    assert row['academic_flag']=='No observed trigger'
    assert row['placement_flag']=='Support needed'
    assert 'Strong academics with placement gap' in row['segments']
    assert component_breakdown(row).weighted_points.sum()==pytest.approx(68)


def test_missing_placement_yields_no_score(scored):
    row=student(scored,'DEMO005')
    assert row['coverage']==.75
    assert pd.isna(row['overall_score'])
    assert row['score_status']=='Insufficient data'
    assert row['placement_flag']=='Undetermined'
    assert 'Currently on track' not in row['segments']


def test_missing_5pct_rescales(scored):
    row=student(scored,'DEMO006')
    assert row['coverage']==.95
    assert row['score_status']=='Provisional'
    assert row['overall_score']==pytest.approx(65.5/.95,abs=.005)
    assert component_breakdown(row).effective_points.sum()==pytest.approx(65.5/.95)


def test_dual_support_and_on_track(scored):
    assert 'Dual support' in student(scored,'DEMO003')['segments']
    assert 'Currently on track' in student(scored,'DEMO004')['segments']


def test_trigger_survives_missing_other_evidence(joined):
    row=student(joined,'DEMO001')
    row['aptitude_pct']=None
    result=score_student(row)
    assert result['P'] is None
    assert result['placement_flag']=='Support needed'  # coding=40 is still known
    assert 'coding_pct=40' in result['placement_reasons'][0]


def test_feedback_never_changes_score(joined):
    row=student(joined,'DEMO007')
    baseline=score_student(row)
    row['support_requested']=False
    after=score_student(row)
    assert baseline['support_request']
    assert baseline['overall_score']==after['overall_score']

@pytest.mark.parametrize('analysis',['2026-11-10','2026-09-20'])
def test_stale_and_future_are_excluded(demo,analysis):
    rows=integrate(demo,'2026-09-30',analysis)
    result=score_student(student(rows,'DEMO001'))
    assert result['coverage']==0
    assert result['overall_score'] is None
    assert result['academic_flag']==result['placement_flag']=='Undetermined'
    assert not result['support_request']


def test_scenario_preserves_baseline(scored):
    baseline=student(scored,'DEMO001')
    snapshot=deepcopy(baseline)
    result=simulate(baseline,{'aptitude_pct':80,'coding_pct':80,'interview_pct':80})
    assert baseline==snapshot
    assert result['overall_score']==78
    assert result['placement_flag']=='No observed trigger'

@pytest.mark.parametrize('changes',[{'coding_pct':101},{'classes_attended':41},{'marks_pct':-1},{'backlog_count':0},{'assignments_completed':7.5}])
def test_scenario_rejects_invalid_changes(scored,changes):
    with pytest.raises(ValueError):simulate(student(scored,'DEMO001'),changes)
