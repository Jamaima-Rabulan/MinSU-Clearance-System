# MinSU Clearance System — PRD

## Original Problem Statement
Adopt & improve <https://github.com/jhamelma2013-coder/minsu_clearance_system>.
User choices over subsequent iterations:

1. **Iter 1** — Clone/setup, add audit log + audit trail, replace SHA-256 with bcrypt, upgrade design (fonts, MinSU palette).
2. **Iter 2** — Add brute-force lockout on login, enforce password policy at register, **convert the whole app to pure PHP for Hostinger** (MySQL/MariaDB, native `$_SESSION`, standard password policy 8+ / letter+digit, 5 failed attempts → 15-minute lockout).

## Architecture
Two parallel builds live in `/app`:

### `/app/backend` + `/app/frontend` (Iter 1 stack — FastAPI + MongoDB + React shell)
- Kept for reference; still running on ports 8001 (backend) and 3000 (frontend).
- Backend uses bcrypt, audit log, and the MinSU-branded SPA.

### `/app/php/` (Iter 2 stack — pure PHP + MySQL — production for Hostinger)
- `schema.sql` — MySQL schema (5 tables including `login_attempts`).
- `public/index.html` + `public/js/app.js` + `public/css/style.css` + `public/images/` — the same MinSU-branded SPA, refactored to use session cookies (`credentials: 'include'`) instead of `?user_id=`.
- `public/api/index.php` — front-controller with every route.
- `public/api/lib/` — `bootstrap.php` (session + PDO + admin seed), `util.php` (validation + constants), `auth.php` (session helpers + brute-force lockout), `audit.php` (log writer).
- `public/.htaccess` — Apache rewrite `/api/*` → `api/index.php`, SPA fallback, security headers, file protection.
- `README-HOSTINGER.md` — 5-step deployment guide.
- Zipped bundle: `/app/minsu_php_hostinger.zip` (686 KB).

## User Personas
- **Student** — submits clearance requests, tracks approvals, prints slip, views per-clearance audit trail.
- **Faculty / Clearing Officer** — sees pending clearances for their office, signs (draw/type/saved), approves or rejects. Registrar can only approve last.
- **Administrator** — manages users, filters full audit trail, deletes users.

## Security (PHP build)
- **Bcrypt** password hashing (`password_hash(PASSWORD_BCRYPT)`).
- **Password policy** at register: `min 8 chars, ≥1 letter, ≥1 digit, ≤128 chars`.
- **Brute-force lockout** on login: keyed by `IP:email`, 5 failures within 15 minutes = 15-minute lockout, returns HTTP 429.
- **Native PHP sessions** with `HttpOnly`, `SameSite=Lax`, `Secure` when HTTPS.
- **`session_regenerate_id(true)`** on login and register.
- **Server-side validation** on every payload: email format, role enum, office/campus/college/course/year/section enums, semester enum, AY regex `YYYY-YYYY`, UUID regex on IDs, size caps on signature and comments.
- **Audit log** persisted to `audit_logs` for register / login (success + failure + lockout) / logout / clearance.create / clearance.approve / clearance.reject / admin.delete_user with IP + UA.
- **Static-file protection** via `.htaccess` (denies config.php, schema.sql, .env, api/lib/).

## Design System (unchanged from Iter 1)
- Deep Forest Green `#14532D` + Antique Gold `#C79B2A` on warm parchment.
- Fraunces (editorial serif) headings + Plus Jakarta Sans body + JetBrains Mono code chips.

## What's Been Implemented (2026-01-23)
### Iter 1 (previous)
- [x] Repo cloned; FastAPI + React shell working.
- [x] Bcrypt hashing (with SHA-256 legacy migration).
- [x] Audit log + trail (backend + admin UI + per-clearance modal).
- [x] Premium MinSU palette + typography.
- [x] Testing agent: 32/32 backend, all frontend flows green.

### Iter 2 (this session)
- [x] Pure PHP + MySQL rewrite in `/app/php/`.
- [x] MySQL schema with `login_attempts` table for lockout.
- [x] Front-controller router (`api/index.php`) mirroring every FastAPI route.
- [x] Native PHP sessions replacing `?user_id=` query params.
- [x] SPA refactored to use `credentials: 'include'` + `/auth/me` boot.
- [x] Brute-force lockout (5 failures / 15-min window / 15-min lock).
- [x] Password policy (8+, letter, digit) enforced at register.
- [x] Server-side validation on every endpoint.
- [x] `.htaccess` with pretty URLs, SPA fallback, security headers, file protection.
- [x] Deployment guide + zipped bundle ready for Hostinger upload.
- [x] End-to-end curl tests: register → login → lockout → clearance create → Registrar-last block → office approve → audit trail. All green.

## Backlog (P1)
- Email notifications (SendGrid/Resend) on approval/rejection.
- CSV / PDF export of the audit trail.
- Admin UI to reset a user's password / manually clear a lockout.
- Password reset flow (email verification).

## Backlog (P2)
- Sortable columns on the users & audit-log tables.
- Bulk approve for a single office.
- 2FA via TOTP for faculty and admin.

## Next Action Items
- Copy `php/public/api/config.example.php` → `config.php` and fill Hostinger DB creds.
- Import `php/schema.sql` in phpMyAdmin.
- Upload contents of `php/public/` to `public_html/`.
- Change the default admin password immediately after first login.
