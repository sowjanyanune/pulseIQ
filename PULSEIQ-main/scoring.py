"""Rules-based support indicators, evidence templates and coverage. No trained model."""
from __future__ import annotations
from copy import deepcopy
import json
import math
from pathlib import Path
import pandas as pd

CONFIG = json.loads((Path(__file__).resolve().parent / 'config.json').read_text())
COMPONENTS = {'A': ('Academic', 'academic'), 'T': ('Attendance', 'attendance'),
              'L': ('LMS completion', 'lms'), 'P': ('Placement readiness', 'placement'),
              'S': ('Skills', 'skills'), 'E': ('Engagement', 'engagement')}


def validate_config(config):
    if set(config['weights']) != set(COMPONENTS) or any(v < 0 for v in config['weights'].values()):
        raise ValueError('Weights must include exactly A, T, L, P, S, E and be non-negative.')
    if not math.isclose(sum(config['weights'].values()), 1):
        raise ValueError('Weights must sum to 1.')
    if not 0 < config['minimum_coverage'] <= 1:
        raise ValueError('minimum_coverage must be in (0, 1].')


def _number(row, field, source):
    value = row.get(field)
    if not bool(row.get(f'{source}__fresh', False)) or pd.isna(value):
        return None
    return float(value)


def _ratio(row, numerator, denominator, source):
    n, d = _number(row, numerator, source), _number(row, denominator, source)
    return 100 * n / d if n is not None and d is not None and d > 0 else None


def _mean(row, fields, source):
    values = [_number(row, field, source) for field in fields]
    return sum(values) / len(values) if all(v is not None for v in values) else None


def score_student(row: dict, config: dict | None = None) -> dict:
    cfg = config or CONFIG
    validate_config(cfg)
    values = {
        'A': _number(row, 'marks_pct', 'academic'),
        'T': _ratio(row, 'classes_attended', 'classes_held', 'attendance'),
        'L': _ratio(row, 'assignments_completed', 'assignments_assigned', 'lms'),
        'P': _mean(row, ['aptitude_pct', 'coding_pct', 'interview_pct'], 'placement'),
        'S': _mean(row, ['technical_pct', 'communication_pct'], 'skills'),
        'E': _ratio(row, 'activities_completed', 'activities_available', 'engagement'),
    }
    coverage = sum(cfg['weights'][key] for key, value in values.items() if value is not None)
    numerator = sum(cfg['weights'][key] * value for key, value in values.items() if value is not None)
    status = 'Complete' if coverage >= 1 - 1e-9 else ('Provisional' if coverage + 1e-9 >= cfg['minimum_coverage'] else 'Insufficient data')
    overall = round(numerator / coverage, 2) if status != 'Insufficient data' else None
    backlog = _number(row, 'backlog_count', 'academic')
    coding = _number(row, 'coding_pct', 'placement')
    academic_reasons, placement_reasons = [], []
    if values['A'] is not None and values['A'] < cfg['academic_threshold']:
        academic_reasons.append(f"marks_pct={values['A']:g} < {cfg['academic_threshold']} (academic)")
    if values['T'] is not None and values['T'] < cfg['attendance_threshold']:
        academic_reasons.append(f"attendance={values['T']:.1f}% < {cfg['attendance_threshold']}% (classes_attended/classes_held)")
    if backlog is not None and backlog > 0:
        academic_reasons.append(f'backlog_count={backlog:g} > 0 (academic)')
    if values['P'] is not None and values['P'] < cfg['placement_threshold']:
        placement_reasons.append(f"placement mean={values['P']:.1f}% < {cfg['placement_threshold']}% (aptitude_pct, coding_pct, interview_pct)")
    if coding is not None and coding < cfg['coding_threshold']:
        placement_reasons.append(f"coding_pct={coding:g} < {cfg['coding_threshold']} (placement)")
    def flag(reasons, complete):
        return 'Support needed' if reasons else ('No observed trigger' if complete else 'Undetermined')
    academic_flag = flag(academic_reasons, all(v is not None for v in (values['A'], values['T'], backlog)))
    placement_flag = flag(placement_reasons, values['P'] is not None and coding is not None)
    academic_support, placement_support = bool(academic_reasons), bool(placement_reasons)
    strong_gap = values['A'] is not None and values['A'] >= cfg['strong_academic_threshold'] and placement_support
    on_track = academic_flag == placement_flag == 'No observed trigger'
    insufficient = status == 'Insufficient data' or 'Undetermined' in (academic_flag, placement_flag)
    segments = []
    for label, enabled in [('Strong academics with placement gap', strong_gap), ('Academic support', academic_support),
                           ('Placement support', placement_support), ('Dual support', academic_support and placement_support),
                           ('Currently on track', on_track), ('Insufficient evidence', insufficient)]:
        if enabled:
            segments.append(label)
    requests = bool(row.get('feedback__fresh', False)) and row.get('support_requested') is True
    # numpy.bool_ is possible after joins; pd.NA must not be evaluated as a boolean.
    if bool(row.get('feedback__fresh', False)) and not pd.isna(row.get('support_requested')):
        requests = bool(row.get('support_requested'))
    recommendations = []
    def recommend(trigger, action):
        recommendations.append({'trigger': trigger, 'action': action})
    if coding is not None and coding < cfg['coding_threshold']:
        recommend(f'coding_pct={coding:g}', 'Schedule coding practice and a mock coding assessment.')
    if placement_support:
        recommend('; '.join(placement_reasons), 'Plan aptitude practice and a mock interview with the placement team.')
    if academic_support:
        recommend('; '.join(academic_reasons), 'Arrange an academic mentor check-in and agree on a support plan.')
    if values['T'] is not None and values['T'] < cfg['attendance_threshold']:
        recommend(f"attendance={values['T']:.1f}%", 'Discuss attendance barriers with the student; confirm context before acting.')
    if values['L'] is not None and values['L'] < 70:
        recommend(f"assignment completion={values['L']:.1f}%", 'Check in about missed assignments and agree on a manageable completion plan.')
    if requests:
        recommend(f"support_requested=true; support_category={row.get('support_category')}", 'Review the student support request and agree on an appropriate next step.')
    out = dict(row)
    out.update({**values, 'overall_score': overall, 'coverage': round(coverage, 6), 'score_status': status,
                'academic_flag': academic_flag, 'placement_flag': placement_flag,
                'academic_reasons': academic_reasons, 'placement_reasons': placement_reasons,
                'segments': segments, 'recommendations': recommendations, 'support_request': requests,
                'scoring_version': cfg['scoring_version']})
    return out


def score_dataset(frame: pd.DataFrame, config: dict | None = None) -> pd.DataFrame:
    return pd.DataFrame([score_student(row, config) for row in frame.to_dict('records')])


def component_breakdown(record: dict, config: dict | None = None):
    cfg = config or CONFIG
    rows = []
    for key, (label, source) in COMPONENTS.items():
        value = record.get(key)
        available = value is not None and not pd.isna(value)
        weighted = cfg['weights'][key] * value if available else None
        coverage = record['coverage']
        effective = weighted / coverage if available and record['score_status'] != 'Insufficient data' else None
        rows.append(dict(component=label, symbol=key, value=value, weight=cfg['weights'][key],
                         weighted_points=weighted, effective_points=effective, source=source,
                         period_end=record.get(f'{source}__period_end'), filename=record.get(f'{source}__filename'),
                         imported_at=record.get(f'{source}__imported_at'), fresh=record.get(f'{source}__fresh', False)))
    return pd.DataFrame(rows)


def simulate(record: dict, changes: dict) -> dict:
    allowed = {'marks_pct', 'classes_attended', 'assignments_completed', 'aptitude_pct', 'coding_pct', 'interview_pct'}
    if set(changes) - allowed:
        raise ValueError('Only approved scenario fields can be changed.')
    scenario = deepcopy(record)
    for field, value in changes.items():
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'Invalid scenario value for {field}.')
        if field.endswith('_pct') and value > 100:
            raise ValueError(f'{field} must be <=100.')
        if field == 'classes_attended' and (int(value) != value or value > record['classes_held']):
            raise ValueError('Scenario attendance must be a whole count <= classes_held.')
        if field == 'assignments_completed' and (int(value) != value or value > record['assignments_assigned']):
            raise ValueError('Scenario assignments must be a whole count <= assignments_assigned.')
        scenario[field] = value
    return score_student(scenario)


def export_scores(frame):
    export = frame.copy()
    for col in ['segments', 'academic_reasons', 'placement_reasons']:
        if col in export:
            export[col] = export[col].map(lambda items: ' | '.join(items))
    if 'recommendations' in export:
        export['recommendations'] = export.recommendations.map(lambda items: ' | '.join(x['action'] for x in items))
    return export
