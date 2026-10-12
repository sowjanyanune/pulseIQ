# Deploying PULSEIQ from GitHub

The source package is ready for hosting, but no public deployment is created by this ZIP. GitHub stores code and runs CI; Streamlit Community Cloud or another Python host runs the app. GitHub Pages serves static files and cannot run this Streamlit Python server.

## Streamlit Community Cloud

1. Push the project contents to your existing public PULSEIQ repository. `app.py` and `requirements.txt` should be at the root.
2. Open https://share.streamlit.io/ and sign in with the account that can access the repository.
3. Create an app; select the repository, your source branch and `app.py` as the entrypoint.
4. Select Python 3.12 in advanced settings to match the documented local setup. No secrets are needed.
5. Deploy. If dependency installation fails, inspect the log and check that the requirements file and Python version match.
6. Copy the HTTPS application URL after it starts and perform the full checklist below from a fresh/private browser.

Official guides checked for this package:

- https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy
- https://docs.streamlit.io/deploy/concepts/dependencies

Available accounts, quotas and hosting access remain external dependencies. Dependency versions are pinned to the tested environment rather than automatically using the newest release.

## Fresh-browser release checklist

- [ ] HTTPS URL opens without a server exception.
- [ ] Synthetic demo shows 200 students at the September period and visible reference analysis date.
- [ ] Department, semester and segment filters update cohort count and profile choices.
- [ ] DEMO001 shows score 68.0, complete coverage and placement support despite strong marks.
- [ ] DEMO005 shows insufficient data rather than a green/on-track result.
- [ ] A support action can be created, assigned, edited and reviewed with a note.
- [ ] The action can be reopened and the earlier note remains in revision history.
- [ ] Cohort, action, history and scenario downloads work.
- [ ] An invalid import shows actionable errors and does not replace the active dataset.
- [ ] A valid import with a leading-zero ID preserves the ID and source provenance.
- [ ] Another private browser session does not see the first session's uploads or actions.
- [ ] Reset clears uploaded data/actions and restores the synthetic demo.
- [ ] Real academic sample has no overall scores or fabricated placement assessments.
- [ ] Check after the final pushed commit; record the tested URL, commit and date.

Local tests and server health checks do not substitute for this hosted HTTPS check. Do not mark the public release complete until this checklist is done.

## Operational scope

The app writes no user uploads or notes to disk, uses no global data cache and has no persistent database. Server disk is not a durability mechanism. Session state and exports provide the current hackathon behavior. Dataset switches and resets clear interventions by design.

Public deployment is for the supplied fictional demo or appropriately de-identified examples. Institution-specific production use requires authentication, per-department authorization, data-retention rules, persistent audit records and approved handling of source corrections.
