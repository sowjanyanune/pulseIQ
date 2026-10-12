"""Measure importer/scorer behavior; save no personal data. Run after setup."""
from pathlib import Path
import sys
from time import perf_counter
import json
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from data_io import load_directory,integrate
from scoring import score_dataset


def run(path,label):
    start=perf_counter()
    imported=load_directory(path)
    validated=perf_counter()
    joined=integrate(imported,'2026-09-30','2026-10-10')
    scores=score_dataset(joined)
    done=perf_counter()
    return {'dataset':label,'accepted':bool(imported.ok),'students':len(scores),
            'validation_seconds':round(validated-start,4),'join_and_score_seconds':round(done-validated,4),
            'total_seconds':round(done-start,4),'score_status_counts':scores.score_status.value_counts().to_dict(),
            'academic_support':int(scores.academic_flag.eq('Support needed').sum()),
            'placement_support':int(scores.placement_flag.eq('Support needed').sum()),
            'maximum_coverage':float(scores.coverage.max())}

if __name__=='__main__':
    print(json.dumps([run(ROOT/'demo_data','Synthetic full demo'),
                      run(ROOT/'benchmark_data'/'import_sample','UCI academic-only sample')],indent=2))
