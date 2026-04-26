# MinSU Clearance System - PRD

## Original Problem Statement
Clone https://github.com/jhamelma2013-coder/minsu_clearance_system and add features:
- Email verification with code-input UI
- Audit log (admin viewable)
- Centered login with MinSU campus background (reduced opacity)
- Multiple clearance types (Enrollment, Graduation, Transfer, Leave of Absence, etc.)
- Student file uploads for requirements
- JWT authentication
- Email notification when clearance is fully signed (SendGrid)
- More presentable UI

## Architecture
- **Backend**: FastAPI + Motor (MongoDB) on port 8001 — JWT auth (PyJWT + bcrypt), SendGrid for email, file uploads via aiofiles to `/app/backend/uploads/`
- **Frontend**: Vanilla JS SPA served by `node server.js` on port 3000, Manrope + Fraunces fonts, MinSU green/gold palette, FontAwesome icons
- **DB**: `minsu_clearance` (collections: users, clearances, audit_logs)
- **Routing**: Same-origin `/api/*` → backend, `/*` → frontend (Kubernetes ingress)

## User Personas
- **Student** — registers, requests clearances, uploads supporting files, tracks approvals
- **Faculty** — assigned to one office (Librarian, Guidance, SAS, Finance, Dean, Registrar); approves/rejects clearances for their office
- **Admin** — manages users (create faculty/admin), views all clearances, audits the system

## Core Requirements
1. JWT-based auth (24h tokens) with bcrypt password hashing
2. Email verification gate before login (6-digit code, 30-min expiry)
3. Six-office sequential approval flow (Registrar last)
4. Multiple clearance types selectable on creation
5. File uploads up to 10MB (PDF/DOC/Images)
6. Full audit log for all sensitive actions
7. SendGrid notifications on full approval / rejection / verification / password reset

## What's Implemented (Jan 2026)
- ✅ JWT auth + bcrypt + admin seeding
- ✅ Registration → 6-digit OTP screen → verify → login
- ✅ Forgot password / reset flow with code
- ✅ Resend verification code
- ✅ Multiple clearance types (End of Semester, Enrollment, Graduation, Transfer, Leave of Absence, Scholarship, Others)
- ✅ Faculty approve/reject with comments + auto-generated approval codes
- ✅ Registrar-last enforcement
- ✅ Student file uploads (PDF/DOC/images, 10MB cap), download by participants
- ✅ Audit log (all auth events, clearance lifecycle, file uploads, admin actions)
- ✅ Admin: user list, search, delete, create faculty/admin, audit log viewer with filters
- ✅ Email templates (verification, password reset, full approval, rejection) via SendGrid
- ✅ Redesigned UI: centered login over MinSU campus bg @25% opacity, sidebar nav, stats cards, professional green/gold theme, OTP input with paste support

### Iteration 4 (Jan 2026)
- ✅ **Official MinSU Clearance Slip layout** — exact match to the official paper slip:
  - Centered MinSU logo + "Mindoro State University" + "Office of Student Affairs Services" + "STUDENT'S CLEARANCE SLIP" header
  - Semester checkboxes (1st Sem / 2nd Sem / Summer) + AY year on right
  - Campus checkboxes (MMC / MBC / MCC) + College on right
  - Name / Student No. / Course/Yr/Sec underlined fields
  - 4-column table: CLEARING OFFICERS | REMARKS | DATE | APPROVAL CODE
  - "FOR VALIDATION - REGISTRAR'S OFFICE USE ONLY" section with Validated By / Date Validated signature lines
  - Footer with Clearance ID and validation note
  - Identical look on screen and when printed (A4 portrait, 1.5cm margins)
- ✅ **Password show/hide eye toggles** on every password input across the app:
  - Login, Register (password + confirm), Reset password, Change password, Admin Create User, Admin Reset Password modal, SendGrid API key field
  - Single reusable `passwordField()` helper

## Next Action Items / Backlog
- P1: Tighten CORS origins (move from `*` to explicit allowed origins)
- P2: Password complexity policy for admin-created accounts
- P2: Admin email-delivery dashboard (track SendGrid bounces)
- P2: Cursor pagination for audit logs
- P3: Print-friendly clearance slip layout (basic print stylesheet present)
- P3: Bulk approve for faculty
- P3: Refactor server.py into routers (auth, clearances, admin, uploads)

## Key Files
- `/app/backend/server.py` — all backend logic
- `/app/backend/.env` — secrets (JWT_SECRET, SENDGRID_API_KEY, etc.)
- `/app/frontend/js/app.js` — SPA logic
- `/app/frontend/css/style.css` — design system
- `/app/frontend/images/minsu-bg.jpg`, `minsu-logo.jpg` — branding
- `/app/memory/test_credentials.md` — test accounts
