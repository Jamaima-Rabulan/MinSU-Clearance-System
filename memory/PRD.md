# MinSU Clearance System — PRD

## Original Problem Statement
Adopt and improve the GitHub repo
<https://github.com/jhamelma2013-coder/minsu_clearance_system>.
User choices:
1. **1b** — Clone, set up, and add features/fixes.
2. Add **audit log** + **audit trail**.
3. Use **bcrypt** for password hashing.
4. Make UI more presentable with best fonts + MinSU color palette.
5. Adapt to the environment.
6. **(Iter 2)** Put validation on all important actions.

## Architecture (as deployed to /app)
- **Backend** — FastAPI (`/app/backend/server.py`) on port 8001. MongoDB via Motor.
  All routes prefixed with `/api`.
- **Frontend** — React CRA shell mounts the vanilla-JS SPA at
  `/app/frontend/public/js/app.js` + `/css/style.css`. App.js injects the
  script/stylesheet once after mount and exposes `window.__MINSU_BACKEND_URL__`.
- **MongoDB** — local, database `minsu_clearance`.

## User Personas
- **Student** — creates clearance requests, tracks approvals, prints slip.
- **Faculty / Clearing Officer** — approves/rejects for their office (with
  e-signature); Registrar-last rule enforced.
- **Administrator** — manages users, reviews audit trail.

## Core Requirements
- Role-based registration (student / faculty / admin).
- Bcrypt (`$2b$`) password hashing + legacy SHA-256 migration on login.
- 6-office MinSU clearance workflow with Registrar-last rule.
- E-signature (draw / type / saved local) stored as data-URL.
- Printable official MinSU clearance slip.
- Comprehensive audit log (auth, clearance, admin) + per-clearance audit trail.
- Default admin auto-seeded: `admin@minsu.edu.ph` / `Admin@MinSU2025`.
- Validation on every important action (see next section).

## Design System
- Palette: Deep Forest Green `#14532D` + Antique Gold `#C79B2A` on warm
  parchment `#FAF7F0`. Gradient green→gold accents.
- Typography: Fraunces (editorial serif) headings, Plus Jakarta Sans body,
  JetBrains Mono for code / audit chips.

## What's Been Implemented

### Iteration 1 (2026-01-23)
- [x] Repo cloned and adapted; supervisor-managed backend + frontend.
- [x] FastAPI backend rebuilt with bcrypt + comprehensive audit log.
- [x] MinSU vanilla-JS SPA wired inside React CRA shell.
- [x] Premium MinSU palette + Fraunces / Plus Jakarta Sans typography.
- [x] Admin Users view + Admin Audit Trail view with filters.
- [x] Per-clearance audit-trail modal.
- [x] Default admin idempotent seeding.
- [x] Testing agent: **32/32 backend + all frontend flows green**.

### Iteration 2 — Validation (2026-01-23)
- [x] **Server-side (Pydantic + global RequestValidationError handler)**
  - Password policy: min 8 chars, ≥ 1 letter + ≥ 1 number.
  - Full name: 3–120 chars, letters/spaces/`.,'-` only.
  - Role enum (student/faculty/admin) + role-specific required fields.
  - Student ID pattern `^[A-Za-z0-9-]{4,20}$`; enum validation on
    course / year / section / campus / college.
  - Semester enum + academic-year `YYYY-YYYY` with `end == start + 1` rule.
  - Clearance action enum; comments ≤ 500 chars.
  - **Approve requires a valid `data:image/…` signature (≤ 2 MB).**
  - **Reject requires non-empty comments.**
  - Uniform error responses: `422 {"detail": "<single message>"}`.
- [x] **Admin safeguards** — cannot delete self, cannot delete last admin,
  cannot delete student/faculty with pending clearances (400 with reason).
- [x] **Client-side** — inline red field errors + `.input-error` borders,
  live password-strength meter, blur/input re-validation, duplicate-clearance
  guard, `novalidate` forms so custom UI wins over native browser bubbles.
- [x] Testing agent: **45/45 backend tests green**, all frontend flows green.

### Iteration 3 — Brute-force protection (2026-01-23)
- [x] **Login lockout** — 5 failed attempts within a 15-min rolling window
  locks the account for 15 min. Correct password is rejected with 429 while
  locked. Failure counts are derived from `audit_logs` (no new schema); the
  lockout timestamp lives on `users.lockout_until`.
- [x] **Per-IP secondary shield** — 20 failures/15 min from the same IP
  returns 429 (protects against user enumeration).
- [x] **Audit trail** — new `user.locked` entry on threshold, `admin.unlock_user`
  entry on manual unlock.
- [x] **Admin unlock endpoint** — `POST /api/admin/users/{id}/unlock` clears
  `lockout_until` **and** purges recent failure audit entries so the user isn't
  immediately re-locked.
- [x] **Admin UI** — Users table now shows a Status column (`Active` / `🔒 Locked`)
  and an `Unlock` button on locked rows.
- [x] Testing agent: **54/55 backend tests pass** (1 pre-existing skip), all
  frontend flows green.

## Backlog (P1)
- Replace `?user_id=…` query-param auth with JWT/session cookies.
- Rate-limit `/api/auth/login` + brute-force lockout (audit failures already
  captured — just not consumed).
- Split `server.py` into routers (auth / clearances / admin / audit).

## Backlog (P2)
- CSV / PDF export for the audit log.
- Email notifications on approval / rejection.
- Admin role-editing UI (promote / demote).

## Next Action Items
- Wire brute-force lockout using existing audit failure records.
- Introduce JWT auth and remove `user_id` query params.
- Seed demo data (students + 6 faculty offices) for a one-click preview.
