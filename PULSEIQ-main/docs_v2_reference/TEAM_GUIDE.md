# Five-member work guide

This package is implemented. Begin by running it as a team; use the stages below to understand dependencies, verify your ownership area and make changes without conflicting edits.

## Shared first step

Member 1 commits the package to the existing PULSEIQ repository. All five members clone it, run the synthetic demo, and agree to retain the CSV and module contracts. Everyone should understand DEMO001's 68.0 score and placement gap before changing any logic.

## Member 1 — project lead and integration

Own `app.py`, dependencies, `.streamlit/`, GitHub Actions, README and deployment.

1. Copy the package into the existing cloned repository; include configuration folders and commit it.
2. Run the Windows launcher or manual setup. Run all tests before editing.
3. Verify navigation, session initialization, dataset switching, reset and shared cohort filters.
4. Create/approve the schema contract with Members 2 and 3. Coordinate widget/data interfaces with Members 4 and 5.
5. Review teammates' pull requests. Merge data and scoring changes before dependent UI changes when interfaces change.
6. Use Streamlit Community Cloud with `app.py` and Python 3.12. Verify the final pushed source, not an older branch.
7. Complete the fresh-browser deployment checklist, record the URL and arrange the final demo.

Comes into the picture first, stays involved throughout, and owns the final integration/deployment stage. Output: one working app from the team's repository.

## Member 2 — data engineering

Own `data_io.py`, `scripts/generate_demo_data.py`, `scripts/prepare_uci_data.py`, `demo_data/`, `templates/`, fixtures and source notes.

1. Read `docs/DATA_CONTRACTS.md` and inspect all eight CSV files.
2. Regenerate the synthetic data and confirm 200 students, two periods and no personal identifiers.
3. Check the five core support examples plus provisional and feedback-request cases.
4. Verify blank IDs, invalid percentages/counts, zero denominators and duplicate keys produce the intended reports.
5. Check unmatched IDs are excluded and one period never borrows another period's values.
6. Supply `ImportResult` and the joined dataframe to Member 3. Supply validation summaries to Member 4.
7. Review the UCI attribution and mapping with Member 3. Keep its missing sources unknown.
8. Run `tests/test_data_io.py` and the benchmark script after changes.

Starts immediately after contract agreement. Member 3 can use small fixtures before the full data is ready. Output: clean, traceable inputs with visible quality gaps.

## Member 3 — scoring and decision intelligence

Own `scoring.py`, `config.json`, scoring tests and methodology text with Member 4.

1. Confirm the six components, weights and required constituents with Member 2.
2. Verify the reference result: A80/T90/L70/P40/S60/E50 → 68.0.
3. Verify 75% coverage produces no score and 95% coverage produces a labelled provisional score.
4. Review independent academic and placement flags and incomplete-evidence behavior.
5. Confirm segments overlap and feedback requests never reduce a score.
6. Check every recommendation cites real observed fields; avoid claims about motivation or employability.
7. Verify scenario recalculation cannot overwrite the original and cannot manufacture missing observations.
8. Coordinate evidence output with Member 4 and playbook format with Member 5. Update scoring version and docs together for rule changes.
9. Run `tests/test_scoring.py` and review real-data coverage separately from accuracy claims.

Starts after schemas are agreed; finishes before final dashboard integration. Output: tested, explainable support indicators.

## Member 4 — UI and dashboards

Own the dashboard, import/profile/simulator portions of `views.py`. Coordinate edits with Member 5, who owns the action-board portion of the same file.

1. Run each screen on the synthetic demo and review the navy/teal visual hierarchy.
2. Ensure the sidebar filters update counts, charts, profile choices and exports consistently.
3. Inspect complete, provisional, insufficient, stale and future-date states.
4. Verify a profile shows date, rule version, coverage, component points and source provenance.
5. Test no-match filters and missing categories; no empty plot should appear without an explanation.
6. Review neutral support language, visible status text and chart labels.
7. Coordinate playbook and action-form behavior with Member 5 and main navigation with Member 1.
8. Run the UI integration tests and inspect desktop/mobile behavior before merging visual changes.

Can start after contracts using bundled fixtures. Connects Member 2's quality reports and Member 3's scored output. Output: usable evidence-first dashboards.

## Member 5 — intervention workflow and QA

Own `interventions.py`, workflow tests, action-board/form portions of `views.py`, demo checklist and final QA coordination.

1. Inspect the intervention fields and allowed statuses: Planned, In progress, Reviewed, Closed.
2. Create an action from DEMO001's profile with an owner alias and due date.
3. Edit action and owner, mark it Reviewed with a note, and verify a history snapshot was appended.
4. Reopen the action and verify earlier review notes remain visible in history.
5. Export the visible action list and revision history. Confirm filters apply to both.
6. Verify two independent sessions do not share actions, notes or uploaded datasets.
7. Confirm switching datasets and reset clear actions, with an export reminder visible.
8. Run `tests/test_interventions.py`, `tests/test_app.py` and the deployment checklist with Member 1.
9. Rehearse the demo, keep local startup available as a backup, and prepare answers about current limitations.

Starts after student-ID/action contracts are agreed. Integrates when profiles and scoring recommendations are ready. Output: a tested action workflow and reviewable release checklist.

## Branches and integration order

| Member | Suggested branch | Primary merge gate |
| --- | --- | --- |
| 1 | `feature/app-integration` | All modules integrate and app starts |
| 2 | `feature/data-pipeline` | Data validation and joining tests |
| 3 | `feature/scoring` | Rule arithmetic and evidence tests |
| 4 | `feature/dashboard` | Shared filters and profile UI tests |
| 5 | `feature/interventions` | Action/history and integration tests |

Members 4 and 5 should not edit the same function simultaneously. If both change `views.py`, agree on function ownership and merge one pull request before rebasing the other. For later growth, split the view file into dashboard/profile/action modules while retaining contracts.

## Suggested remaining schedule

- First 30 minutes: all install and run; Member 1 commits; each owner reviews their module.
- Next 60–90 minutes: make essential changes on branches and run relevant tests.
- Next hour: integrate changes, run full suite and deploy the final commit.
- Final 30–60 minutes: fresh-browser demo, export check, source/architecture review and rehearsal.

Add new features only after the existing end-to-end flow passes. Student login, ERP connectors, trained prediction and a persistent database are future work.
