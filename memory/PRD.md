# MinSU Clearance System — PRD

## Original Problem Statement
Adopt and improve the GitHub repo
<https://github.com/jhamelma2013-coder/minsu_clearance_system>.
User choices:
1. **1b** — Clone, set up, and add new features/fixes.
2. Add an **audit log** + **audit trail**.
3. Use **bcrypt** for password hashing (replacing SHA-256).
4. Make the UI more presentable with best fonts + best MinSU color palette.
5. Check the repo and adapt to our environment.

## Architecture (as deployed to /app)
- **Backend** — FastAPI (`/app/backend/server.py`) on port 8001. MongoDB via Motor.
  All API routes prefixed with `/api`.
- **Frontend** — React CRA shell (`/app/frontend`) loads the original vanilla-JS SPA
  from `/app/frontend/public/js/app.js` + `/app/frontend/public/css/style.css`.
  App.js injects the script/stylesheet once after mount and exposes
  `window.__MINSU_BACKEND_URL__` so vanilla code uses `REACT_APP_BACKEND_URL`.
- **MongoDB** — local daemon, database `minsu_clearance`.

## User Personas
- **Student** — submits clearance requests, tracks approvals, prints slip.
- **Faculty / Clearing Officer** — sees pending clearances for their office,
  signs (draw/type/saved signature), approves or rejects with comments.
  "Registrar" is gated: can only approve once all other 5 offices approved.
- **Administrator** — manages all users, reviews audit trail, deletes users.

## Core Requirements (static)
- Role-based registration (student / faculty / admin).
- bcrypt (`$2b$`) password hashing + automatic migration from legacy SHA-256.
- Clearance workflow across 6 MinSU offices (University Librarian, Guidance
  Counselor, SAS Director/Coordinator, Student Affairs/Finance, College
  Dean/Program Chair, Registrar). Registrar-last approval rule enforced.
- Digital signature (draw / typed / saved-local) stored as data URL.
- Printable official MinSU clearance slip.
- **Audit log** persisted to `db.audit_logs` for every authentication,
  clearance, and admin action. IP + user-agent captured. Visible to admin.
- **Audit trail per clearance** — filtered log view accessible to student owner
  and any faculty/admin.
- Default admin auto-seeded on startup: `admin@minsu.edu.ph` / `Admin@MinSU2025`.

## Design System
- **Palette** — Deep Forest Green `#14532D` + Antique Gold `#C79B2A` on warm
  parchment `#FAF7F0`. Gradient accents under headings (green → gold).
- **Typography** — Fraunces (editorial serif) for headings, Plus Jakarta Sans
  (humanist) for body, JetBrains Mono for audit/code chips.
- Gold hairline under header, pill navigation, gradient-text brand logo,
  radial parchment wash, editorial underline accents on H1s.

## What's Been Implemented (2026-01-23)
- [x] Repository cloned and adapted.
- [x] FastAPI backend rebuilt with bcrypt + comprehensive audit logging.
- [x] MinSU vanilla-JS SPA wired inside React CRA shell.
- [x] New premium MinSU palette + Fraunces / Plus Jakarta Sans typography.
- [x] Admin Users management view.
- [x] Admin Audit Trail view with filters (action / resource / status / email).
- [x] Per-clearance audit-trail modal with timeline.
- [x] SUCCESS/FAILURE pills for audit entries (not APPROVED/REJECTED).
- [x] Default admin idempotent seeding.
- [x] 32/32 backend pytest tests green; frontend flows exercised end-to-end.

## Backlog (P1)
- Replace `?user_id=…` query-param auth with signed JWT/session cookies.
- Rate-limit `/api/auth/login` + brute-force lockout (audit fields already in
  place, just not consumed).
- Password policy at register (min length / complexity).
- Split `server.py` into routers (auth / clearances / admin / audit).

## Backlog (P2)
- CSV / PDF export for audit log.
- Email notifications when clearance approved or rejected.
- Admin user role-editing UI (promote/demote).

## Next Action Items
- Wire brute-force protection consuming the existing audit failures.
- Introduce JWT auth and remove `user_id` query params.
- Create faculty & student seed data for first-run demos.
