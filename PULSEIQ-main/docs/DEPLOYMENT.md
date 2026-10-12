# Render + Neon redeployment checklist

- Set `DATABASE_URL` to your Neon **pooled** PostgreSQL connection string.
- Set and save `APP_SECRET`; rotating it invalidates sessions and integration secrets.
- Set `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_COLLEGE_NAME`, `BOOTSTRAP_COLLEGE_DOMAIN`, `BOOTSTRAP_ADMIN_EMAIL` before first deploy.
- Deploy `render.yaml`; Docker builds React (`npm ci && npm run build`) and then FastAPI.
- Render public URL → `/health` returns `{"status":"ok","version":"3.0.0"}`.
- Check the login with `admin@your-domain` (not legacy username `admin`).
- Student and faculty logins must be **created by the college admin**, using institutional emails.
- For old v2 database snapshots, back up Neon, use `IMPORT_LEGACY_V2=true` once **before creating a v3 roster**, verify content, and disable afterward.
- Set `SEED_DEMO=false` for real data; it must not mix fictional demo students with an institutional roster.
- Use a private repo and production HTTPS; protect admin credentials and school data.
- Verify domain control, formal institutional access permission, retention, audit/monitoring, backups and compliance before real-world use.
- On Render free tier, services may sleep and cannot guarantee institutional availability; choose an appropriate plan for production.

### What happens after the first deployment?

Database table creation is additive (`pi3_*`). v2 tables are not deleted. To add more institutions, use the server-side provisioning script. College-by-college mappings are maintained in `pi3_connections`, rather than global environment variables.
