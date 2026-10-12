# Dataset sources and reuse

## Complete synthetic college demo

`demo_data/` is generated specifically for PULSEIQ using seed 42. It has 200 fictional students, four fictional department labels and two periods. There are eight CSVs: a roster plus the seven PRD categories. It contains no real student identities or institutional records.

Designed examples cover the 68.0 score fixture, academic support, dual support, strong academics with a placement gap, on-track flags, incomplete evidence, provisional scoring and support requests. Invalid fixtures are stored separately and never loaded by the normal demo.

Run `python scripts/generate_demo_data.py` to reproduce these assets. This synthetic dataset is suited to end-to-end workflow and arithmetic testing; it cannot establish real-world predictive accuracy or intervention effectiveness.

## UCI academic benchmark

**Title:** Predict Students' Dropout and Academic Success.

**Attribution:** Realinho, V., Vieira Martins, M., Machado, J., & Baptista, L. (2021). Predict Students' Dropout and Academic Success [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5MC89.

**Source:** https://archive.ics.uci.edu/dataset/697/predict+students+dropout+and+academic+success

**License:** Creative Commons Attribution 4.0 International (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/

**Retrieved:** 10 October 2026. Original CSV content hash is recorded in `benchmark_data/metadata.json`.

The source has 4,424 higher-education student records and 36 feature columns plus the three-category outcome. It comes from an institution in Portugal. Its course population, grade scale and outcome definitions are not validated for an Indian college, and it lacks several PULSEIQ evidence categories.

### Included adaptations

`benchmark_data/uci_academic_subset.csv` keeps the course code, first/second-semester enrolled/evaluation/approved counts and grades, plus Target. It adds stable row IDs `UCI00001` etc. These IDs are arbitrary derivative row references, not original student IDs. Demographics, family, financial and nationality fields from the source are excluded from the bundled derivative.

`benchmark_data/import_sample/` selects 400 records uniformly using pandas seed 42, so each source stays within the application's 1,000-row limit across two periods. It maps:

- Course → opaque department label `UCI course <code>`; roster semester is 2.
- Semester grade, on a 0–20 scale → `marks_pct = grade × 5`, only when evaluations >0 and grade >0.
- Zero/no-evaluation grade → missing evidence. This cautious adaptation is explicit; it is not a claim that the source authors define every zero as missing.
- `backlog_count` → missing. Units not approved are not assumed to be backlogs.
- First and second semesters → artificial period dates 2026-08-31 and 2026-09-30. These are demonstration labels, not actual observed dates.
- Attendance, LMS, placement, skills, engagement and feedback → absent, never fabricated.

`Target` is used only for descriptive benchmark charts. It is excluded from importer scoring. No predictor is trained on it, and no synthetic labels are represented as observed outcomes.

The adapter has at most 30% scoring coverage, so every record receives no overall Success Score. Low observed marks can still trigger an academic-support rule. If no mark trigger is known, academic status is Undetermined because attendance and backlog evidence is missing. Placement is always Undetermined. This tests handling of incomplete real evidence; it is not prediction validation.

Run `python scripts/prepare_uci_data.py` to refresh from the same source. Network access is needed only for this optional preparation step; the included app itself is offline after dependency installation. Retain this attribution and license notice when sharing the derivative. No endorsement by the dataset authors, UCI or KPMG is implied.
