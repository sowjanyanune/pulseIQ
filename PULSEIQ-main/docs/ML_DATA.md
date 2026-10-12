# Historical model workflow

The optional model targets binary later academic support/poor-performance outcome.
Define outcome=1 consistently with the institution before collecting examples;
outcome=0 is the contrasting observed outcome. Placement flags are rule-based.
Do not create labels from the same input threshold score and call this validation.

An admin can POST /api/admin/ml/examples using a signed-in session and CSRF token:

```json
{"features":{"marks_pct":62,"attendance_pct":78,"lms_pct":70,"placement_pct":55,"skills_pct":60,"engagement_pct":40,"backlog_count":0},"outcome":1}
```

At least 40 labeled examples and at least 8 per class are required. Each example
should represent a different student, with features captured BEFORE its outcome.
The current schema does not enforce student/cohort uniqueness or temporal ordering;
clean these upstream. Do not mix repeat observations across train/test splits.
Enable ENABLE_API_DOCS=true temporarily to use /api/docs; authenticate and pass the
X-CSRF-Token from /api/auth/login for write calls. The web UI trains existing examples.

Implementation: median imputation (stable empty columns), RandomForestClassifier,
130 trees, max depth 7, min leaf 5, balanced class weights; stratified 75/25 holdout,
fixed seed 42. Metrics: ROC-AUC, accuracy, precision, recall and split counts.
These are internal holdout metrics, not a prospective or external evaluation.
Before live use, perform cohort/time-separated validation, calibration, subgroup
error analysis and institutional review. Exported model artifacts are not accepted;
only artifacts created by this backend are loaded.
