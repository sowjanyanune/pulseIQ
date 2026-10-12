# V3 API endpoints

All endpoints except `/health`, `/api/auth/login`, and `/api/colleges/resolve` require session cookies. POST/PUT/PATCH/DELETE also require `X-CSRF-Token` from `/api/auth/login` or `/api/auth/me`.

| Method | Endpoint | Role | Purpose |
| --- | --- | --- | --- |
| GET | `/api/colleges/resolve?email=...` | Public | Identify registered college domain |
| POST | `/api/auth/login` | Public | Institutional email + password |
| GET / POST | `/api/auth/me`, `/api/auth/logout` | Logged-in | User and session |
| GET | `/api/students`, `/api/students/{id}` | All | Role-scoped roster and own/assigned student detail |
| GET | `/api/analytics` | All | College/assigned/own scoring |
| POST | `/api/students/{id}/scenario` | All | Non-destructive what-if |
| GET | `/api/actions` | All | Scoping enforced |
| POST / PATCH | `/api/actions`, `/api/actions/{id}` | Admin, faculty | Create/update interventions |
| GET / POST | `/api/entries` | Admin, faculty | List/create draft or published class records |
| GET | `/api/assignments` | Admin, faculty | College or own faculty assignments |
| GET / POST | `/api/admin/accounts` | Admin | Manage faculty/student/admin access |
| PATCH | `/api/admin/accounts/{id}/toggle` | Admin | Enable/disable an account |
| POST | `/api/admin/students` | Admin | Create/update one roster entry |
| POST | `/api/admin/students/bulk` | Admin | Atomic JSON bulk import, up to 5,000 students |
| POST | `/api/admin/assignments` | Admin | Assign faculty subject/class |
| GET / POST | `/api/admin/connections` | Admin | List/create encrypted integration |
| GET | `/api/admin/connections/{id}/discover` | Admin | Inspect remote tables |
| GET | `/api/admin/connections/{id}/preview` | Admin | Validate mapped sample before sync |
| PUT | `/api/admin/connections/{id}/mapping` | Admin | Save field mapping |
| POST | `/api/admin/connections/{id}/sync` | Admin | Import a verified institutional snapshot |
| DELETE | `/api/admin/connections/{id}` | Admin | Remove source configuration |
| GET | `/api/admin/audit` | Admin | Last 100 college audit events |

Public API docs can be enabled with `ENABLE_API_DOCS=true` (only on trusted testing deployments). Default production disables docs.
