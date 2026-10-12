"""Strict CSV contracts and period-safe joins. No global dataset caching."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import io
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 1000
SCHEMAS = {
    'students': ['student_id', 'department', 'semester'],
    'academic': ['student_id', 'period_end', 'marks_pct', 'backlog_count'],
    'attendance': ['student_id', 'period_end', 'classes_attended', 'classes_held'],
    'lms': ['student_id', 'period_end', 'assignments_completed', 'assignments_assigned'],
    'placement': ['student_id', 'period_end', 'aptitude_pct', 'coding_pct', 'interview_pct'],
    'skills': ['student_id', 'period_end', 'technical_pct', 'communication_pct'],
    'engagement': ['student_id', 'period_end', 'activities_completed', 'activities_available'],
    'feedback': ['student_id', 'period_end', 'support_requested', 'support_category'],
}
COUNTS = {'semester', 'backlog_count', 'classes_attended', 'classes_held',
          'assignments_completed', 'assignments_assigned', 'activities_completed', 'activities_available'}
PAIRS = {'attendance': ('classes_attended', 'classes_held'),
         'lms': ('assignments_completed', 'assignments_assigned'),
         'engagement': ('activities_completed', 'activities_available')}
REPORT_COLUMNS = ['source', 'filename', 'row', 'severity', 'message']
SUMMARY_COLUMNS = ['source', 'filename', 'input_rows', 'accepted_rows', 'rejected_rows', 'imported_at']

@dataclass
class ImportResult:
    tables: dict[str, pd.DataFrame]
    report: pd.DataFrame
    summary: pd.DataFrame
    @property
    def ok(self):
        return 'students' in self.tables and not self.tables['students'].empty and not (self.report.severity == 'error').any()
    @property
    def periods(self):
        return sorted({str(v) for k, t in self.tables.items() if k != 'students' for v in t.period_end.dropna()})


def validate_csv(source: str, raw: bytes, filename: str, imported_at: str):
    required = SCHEMAS[source]
    report = []
    def issue(row, severity, message):
        report.append(dict(source=source, filename=filename, row=row, severity=severity, message=message))
    empty = pd.DataFrame(columns=required)
    if len(raw) > MAX_BYTES:
        issue(0, 'error', 'File exceeds 5 MiB. Split into smaller CSV files.')
        return empty, report, 0, 0
    try:
        # All identifiers stay as strings, preserving leading zeroes.
        frame = pd.read_csv(BytesIO(raw), dtype=str, keep_default_na=False, encoding='utf-8-sig')
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError, ValueError):
        issue(0, 'error', 'Cannot parse CSV. Use a UTF-8 comma-delimited template.')
        return empty, report, 0, 0
    n = len(frame)
    if n > MAX_ROWS:
        issue(0, 'error', 'File exceeds 1,000 rows. Reduce the import size.')
        return empty, report, n, n
    missing = set(required) - set(frame.columns)
    if missing:
        issue(0, 'error', f'Missing columns: {", ".join(sorted(missing))}. Download the template.')
        return empty, report, n, n
    extra = set(frame.columns) - set(required)
    if extra:
        issue(0, 'warning', f'Unused columns ignored: {", ".join(sorted(extra))}.')
    frame = frame[required].copy()
    for col in required:
        frame[col] = frame[col].str.strip()
    invalid = pd.Series(False, index=frame.index)
    def reject(mask, message):
        nonlocal invalid
        invalid |= mask
        for index in frame.index[mask]:
            issue(int(index) + 2, 'error', message)
    reject(frame.student_id.eq(''), 'student_id is required; blank IDs cannot be joined.')
    if source == 'students':
        reject(frame.department.eq(''), 'department is required.')
    else:
        date = pd.to_datetime(frame.period_end, format='%Y-%m-%d', errors='coerce')
        reject(date.isna() | ~frame.period_end.str.fullmatch(r'\d{4}-\d{2}-\d{2}'), 'period_end must be a valid YYYY-MM-DD date.')
    keys = ['student_id'] if source == 'students' else ['student_id', 'period_end']
    reject(frame.duplicated(keys, keep=False), 'Duplicate key: correct all ambiguous records; none are selected arbitrarily.')
    for col in required:
        if col not in COUNTS and not col.endswith('_pct'):
            continue
        original = frame[col]
        numeric = pd.to_numeric(original.mask(original.eq('')), errors='coerce')
        reject(original.ne('') & (numeric.isna() | ~np.isfinite(numeric)), f'{col} must be a finite number or blank.')
        reject(numeric.lt(0), f'{col} cannot be negative.')
        if col.endswith('_pct'):
            reject(numeric.gt(100), f'{col} must be between 0 and 100.')
        if col in COUNTS:
            reject(numeric.notna() & numeric.mod(1).ne(0), f'{col} must be a whole number.')
        if col == 'semester':
            reject(numeric.isna() | numeric.lt(1) | numeric.gt(12), 'semester must be an integer from 1 to 12.')
        frame[col] = numeric
    if source in PAIRS:
        numerator, denominator = PAIRS[source]
        reject(frame[numerator].gt(frame[denominator]), f'{numerator} cannot exceed {denominator}.')
        for index in frame.index[frame[denominator].eq(0) & ~invalid]:
            issue(int(index) + 2, 'warning', f'{denominator} is zero: this component is missing evidence, not a zero score.')
    if source == 'feedback':
        raw_bool = frame.support_requested.str.lower()
        allowed = {'true': True, 'false': False, '1': True, '0': False, '': None}
        reject(~raw_bool.isin(allowed), 'support_requested must be true, false, 1, 0 or blank.')
        frame['support_requested'] = raw_bool.map(allowed)
        categories = ['Academic', 'Placement', 'Attendance', 'LMS', 'Other', 'None', '']
        reject(~frame.support_category.isin(categories), 'support_category must be Academic, Placement, Attendance, LMS, Other or None.')
        reject(frame.support_requested.eq(True) & frame.support_category.isin(['None', '']), 'A support request needs a support_category.')
    for col in required:
        if col in ('student_id', 'department', 'period_end', 'support_category'):
            continue
        for index in frame.index[frame[col].isna() & ~invalid]:
            issue(int(index) + 2, 'warning', f'{col} is missing; no value will be imputed.')
    accepted = frame.loc[~invalid].copy()
    accepted['source_filename'] = filename
    accepted['imported_at'] = imported_at
    return accepted, report, n, int(invalid.sum())


def import_files(files: dict[str, tuple[str, bytes]]) -> ImportResult:
    """Validate all files transactionally; UI only activates an entirely error-free batch."""
    tables, messages, summary = {}, [], []
    imported_at = datetime.now(timezone.utc).isoformat()
    for source, (filename, raw) in files.items():
        if source not in SCHEMAS:
            raise ValueError(f'Unknown source: {source}')
        table, report, count, rejected = validate_csv(source, raw, filename, imported_at)
        tables[source] = table
        messages.extend(report)
        summary.append(dict(source=source, filename=filename, input_rows=count,
                            accepted_rows=len(table), rejected_rows=rejected, imported_at=imported_at))
    if 'students' not in tables or tables['students'].empty:
        messages.append(dict(source='students', filename='students.csv', row=0,
                             severity='error', message='Supply a non-empty students.csv roster.'))
    ids = set(tables.get('students', pd.DataFrame(columns=['student_id'])).student_id)
    for source, table in tables.items():
        if source == 'students':
            continue
        unmatched = ~table.student_id.isin(ids)
        for index in table.index[unmatched]:
            messages.append(dict(source=source, filename=table.loc[index, 'source_filename'], row=int(index)+2,
                                 severity='warning', message='Unmatched student_id: excluded until the roster is corrected.'))
        tables[source] = table.loc[~unmatched].copy()
        for item in summary:
            if item['source'] == source:
                item['accepted_rows'] = len(tables[source])
                item['rejected_rows'] += int(unmatched.sum())
    return ImportResult(tables, pd.DataFrame(messages, columns=REPORT_COLUMNS),
                        pd.DataFrame(summary, columns=SUMMARY_COLUMNS))


def load_directory(path: Path) -> ImportResult:
    return import_files({source: (f'{source}.csv', (path / f'{source}.csv').read_bytes())
                         for source in SCHEMAS if (path / f'{source}.csv').exists()})


def integrate(result: ImportResult, period_end: str, analysis_date, stale_days: int = 30):
    if not result.ok:
        raise ValueError('Correct blocking validation errors before activating this batch.')
    if period_end not in result.periods:
        raise ValueError('Select an available reporting period.')
    age = (pd.Timestamp(analysis_date).normalize() - pd.Timestamp(period_end)).days
    fresh = 0 <= age <= stale_days
    joined = result.tables['students'][SCHEMAS['students']].copy()
    joined['period_end'] = period_end
    for source, fields in SCHEMAS.items():
        if source == 'students':
            continue
        source_table = result.tables.get(source, pd.DataFrame(columns=fields + ['source_filename', 'imported_at']))
        subset = source_table.loc[source_table.period_end.eq(period_end)].copy()
        subset[f'{source}__present'] = True
        rename = {'period_end': f'{source}__period_end', 'source_filename': f'{source}__filename',
                  'imported_at': f'{source}__imported_at'}
        subset = subset.rename(columns=rename)
        joined = joined.merge(subset, on='student_id', how='left', validate='one_to_one')
        joined[f'{source}__present'] = joined[f'{source}__present'].eq(True)
        joined[f'{source}__fresh'] = joined[f'{source}__present'] & fresh
    joined['analysis_date'] = str(pd.Timestamp(analysis_date).date())
    joined['data_age_days'] = age
    return joined


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """Escape spreadsheet formulas in text supplied by users; preserve numeric columns."""
    safe = frame.copy()
    for col in safe.select_dtypes(include=['object', 'string']).columns:
        safe[col] = safe[col].map(lambda x: "'" + x if isinstance(x, str) and x.lstrip().startswith(('=', '+', '-', '@')) else x)
    return safe.to_csv(index=False).encode('utf-8-sig')


def templates_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for source, columns in SCHEMAS.items():
            archive.writestr(f'{source}.csv', pd.DataFrame(columns=columns).to_csv(index=False))
    return buffer.getvalue()
