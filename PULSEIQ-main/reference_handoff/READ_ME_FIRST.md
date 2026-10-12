# PULSEIQ PROJECT HANDOFF — READ THIS FIRST

This folder contains **the extracted source project** from the latest PULSEIQ release available in this conversation:
`PULSEIQ_PUBLIC_REGISTRATION_6CHAR_FACULTY_SEARCH.zip`.

## Where everything is

- `PULSE/` — actual React + FastAPI + SQL project; upload the **whole handoff ZIP** in a new ChatGPT conversation.
- `HANDOFF/COPY_PASTE_IN_NEW_CHAT.md` — ready-made request for the next assistant.
- `HANDOFF/REQUIREMENTS_AND_GAPS.md` — original challenge, latest custom page requirements, and known gaps.
- `HANDOFF/DEPLOYMENT_AND_DEBUGGING.md` — technology, environment, local run/deployment checks.
- `HANDOFF/VERIFICATION.md` — what was checked locally in this handoff versus previous unverified claims.
- `HANDOFF/FILE_TREE.txt` — extracted project manifest.
- `HANDOFF/REFERENCE_IMAGES/` — latest screenshots of reported errors and desired visual concepts.

## Important source-of-truth rules

The latest **code** and `PULSE/CHANGELOG_PUBLIC_REGISTRATION_6CHAR_SEARCH.md` supersede older documents. Older `START_HERE.md`, `HOTFIX_OCTOBER_11.md`, `docs/ARCHITECTURE.md`, and `RELEASE_NOTES_ROLE_PAGES.md` contain stale references to **Neon, 12-character passwords, and registration invite codes**. Do not follow those outdated instructions. The latest request uses **Supabase**, **public college registration with no invite code**, **6-character password minimum**, and a **Faculty Student Success Insight search**.

## Never upload or paste secrets

Do not upload real `.env` credentials. The included `.env.example` uses placeholders. Keep Render environment variables, Supabase passwords and session secrets private.

## Honest status

This is a **source-code handoff, not a production-readiness certificate**. Further work is required to independently verify all requirements and the deployment. The user's latest live results were not retested in this environment.
