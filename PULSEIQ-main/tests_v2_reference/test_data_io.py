from io import BytesIO
import zipfile
import pandas as pd
import pytest
from data_io import import_files,integrate,validate_csv,ROOT,MAX_BYTES,csv_bytes,templates_zip,SCHEMAS,load_directory


def imported(academic,students=b'student_id,department,semester\n001,CS,4\n'):
    return import_files({'students':('students.csv',students),'academic':('academic.csv',academic)})


def test_valid_demo_rows_and_dates(demo,joined):
    assert demo.ok
    assert demo.periods==['2026-08-31','2026-09-30']
    assert len(joined)==200
    assert joined.student_id.nunique()==200
    assert all(joined[f'{s}__present'].all() for s in list(SCHEMAS)[1:])
    assert all(joined[f'{s}__period_end'].eq('2026-09-30').all() for s in list(SCHEMAS)[1:])


def test_duplicate_cannot_inflate_join():
    raw=b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-30,80,0\n001,2026-09-30,70,0\n'
    result=imported(raw)
    assert not result.ok
    assert result.tables['academic'].empty
    with pytest.raises(ValueError):integrate(result,'2026-09-30','2026-10-10')


def test_leading_zero_id_is_preserved():
    result=imported(b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-30,80,0\n')
    assert result.ok
    assert result.tables['students'].student_id.iloc[0]=='001'
    assert len(integrate(result,'2026-09-30','2026-10-10'))==1


def test_unmatched_is_reported_and_excluded():
    result=imported(b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-30,80,0\nXYZ,2026-09-30,80,0\n')
    assert result.ok
    assert len(result.tables['academic'])==1
    assert result.report.message.str.contains('Unmatched').any()
    assert result.summary.set_index('source').loc['academic','rejected_rows']==1

@pytest.mark.parametrize('raw',[
    b'student_id,period_end,marks_pct,backlog_count\n,2026-09-30,80,0\n',
    b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-30,101,0\n',
    b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-30,80,-1\n',
    b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-31,80,0\n',
    b'student_id,period_end,marks_pct,backlog_count\n001,2026-09-30,inf,0\n',
    b'student_id,marks_pct\n001,80\n'])
def test_invalid_values_and_schema_block_import(raw):
    assert not imported(raw).ok


def test_zero_denominator_and_numerator_validation():
    zero=b'student_id,period_end,classes_attended,classes_held\n001,2026-09-30,0,0\n'
    table,report,_,_=validate_csv('attendance',zero,'a.csv','now')
    assert len(table)==1
    assert any('zero' in r['message'] for r in report)
    bad=zero.replace(b',0,0',b',1,0')
    assert validate_csv('attendance',bad,'a.csv','now')[0].empty


def test_size_and_row_limits():
    table,report,_,_=validate_csv('students',b' '*(MAX_BYTES+1),'big.csv','now')
    assert table.empty and report[0]['severity']=='error'
    raw=('student_id,department,semester\n'+''.join(f'{i},CS,4\n' for i in range(1001))).encode()
    assert validate_csv('students',raw,'many.csv','now')[0].empty


def test_mixed_periods_never_substitute(demo):
    demo.tables['placement']=demo.tables['placement'].query("period_end == '2026-08-31'")
    joined=integrate(demo,'2026-09-30','2026-10-10')
    assert len(joined)==200
    assert not joined['placement__present'].any()
    assert joined.coding_pct.isna().all()


def test_templates_and_export_protection():
    with zipfile.ZipFile(BytesIO(templates_zip())) as archive:
        assert len(archive.namelist())==8
        for source,fields in SCHEMAS.items():
            assert pd.read_csv(archive.open(source+'.csv')).columns.tolist()==fields
    export=csv_bytes(pd.DataFrame({'note':['=1+1',' @SUM(A1)','plain'],'number':[1,2,3]})).decode('utf-8-sig')
    assert "'=1+1" in export and "' @SUM" in export


def test_uci_importer_does_not_fabricate_evidence():
    from scoring import score_dataset
    result=load_directory(ROOT/'benchmark_data'/'import_sample')
    assert result.ok
    assert len(result.tables['students'])==400
    assert len(result.tables['academic'])==800
    scores=score_dataset(integrate(result,'2026-09-30','2026-10-10'))
    assert scores.coverage.max()<=.30
    assert scores.overall_score.isna().all()
    assert scores.placement_flag.eq('Undetermined').all()
    assert not scores.segments.map(lambda items:'Currently on track' in items).any()
    raw=pd.read_csv(ROOT/'benchmark_data'/'uci_academic_subset.csv')
    assert len(raw)==4424
    assert not any(x in raw.columns for x in ['Gender','Nacionality','Debtor','Age at enrollment'])
