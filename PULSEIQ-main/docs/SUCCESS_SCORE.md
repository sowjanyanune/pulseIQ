# Student Success Score — judge note

The score is a transparent support indicator from 0–100, not a graduation probability.

| Component | Indicator (0–100) | Weight |
|---|---|---:|
| Academic A | marks percentage | 30% |
| Attendance T | attended / held × 100 | 20% |
| LMS L | assignments completed / assigned × 100 | 15% |
| Placement P | mean aptitude, coding, interview percentages | 25% |
| Skills S | mean technical and communication percentages | 5% |
| Engagement E | activities completed / available × 100 | 5% |

SSS = (0.30A + 0.20T + 0.15L + 0.25P + 0.05S + 0.05E) / observed weight.
A missing component contributes neither numerator nor denominator. Coverage below
80% gives no overall score. 80–<100% is Provisional; 100% is Complete. Coverage
means weighted data availability, not statistical confidence. Evidence older than
365 days is excluded by the API default; reports are evaluated as of their selected
period. Historical imported dates and source names remain visible in explanations.

Feedback is the seventh integrated category. Support requests trigger recommendations;
it has zero numerical weight to avoid penalizing a student for asking for help.
Current feedback fields are request/category, not free-text sentiment analysis.

Academic support: marks <50, attendance <75%, or recorded official backlogs >0.
Placement support: placement average <60 or coding <50. Missing evidence is
Undetermined, never proof that a student is safe. These are challenge-model rules
in backend/config.json, distinct from operational pass/attendance preferences.
Segments include strong academics (≥70) with placement gap, academic support,
placement support, dual support, currently on track and insufficient evidence.
Segments may overlap. No forced ranking or automated punitive action is intended.

Recorded faculty exams use total earned / total maximum marks; attendance uses
recorded present / recorded sessions. New operational snapshots override imported
values on the same date and otherwise participate in the latest-as-of-date join.
Backlogs are preserved from imports, not inferred from failed internal exams.

Per-student explanation lists values, weights, effective score points, source and
period. Recommendations link directly to observed triggers. Support actions have
owner, due date, state and review note. What-if changes do not modify actual records.
A strong-academics/weak-placement demo student scores 68: 24+18+10.5+10+3+2.5.

Limitations: weights and thresholds are proposed policy choices, not learned or
causally validated. Test sensitivity and fairness with the college before operational
use. Optional Random Forest probabilities and holdout metrics are separate from SSS.
