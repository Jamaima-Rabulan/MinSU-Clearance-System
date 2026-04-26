# MinSU Clearance System

A complete digital clearance system for **Mindoro State University (MinSU)** — Office of Student Affairs Services. Students request clearances; faculty from 6 different offices approve them; admins manage everything; and superadmins have full system control.

![Tech](https://img.shields.io/badge/backend-FastAPI-009688) ![Tech](https://img.shields.io/badge/frontend-Vanilla_JS-yellow) ![Tech](https://img.shields.io/badge/db-MongoDB-green) ![Tech](https://img.shields.io/badge/auth-JWT-blue)

---

## ✨ Features

### Authentication & Security
- 🔐 **JWT-based authentication** (PyJWT + bcrypt password hashing)
- ✉️ **Email verification** with 6-digit OTP code (auto-expiring after 30 minutes)
- 🔑 **Forgot/reset password** flow with email code
- 👁️ **Show/hide password toggle** on every password field
- 🛡️ **Password complexity enforcement** (8+ chars, uppercase, lowercase, digit)

### 4-Tier Role System
| Role | Capabilities |
|---|---|
| **Student** | Register, verify email, request clearances of various types, upload supporting files, track approvals |
| **Faculty** | Approve/reject clearances for their assigned office (6 offices supported), bulk-approve by program/year/section |
| **Admin** | Manage faculty + students, view audit log, configure SendGrid, reset faculty/student passwords |
| **Superadmin** | Full control: create/delete admins + superadmins, reset any password (cannot be locked out) |

### Clearance Workflow
- 📝 **Multiple clearance types**: End of Semester, Enrollment, Graduation, Transfer, Leave of Absence, Scholarship, Others
- 👥 **6 office approvals required**: University Librarian, Guidance Counselor, SAS Director/Coordinator, Student Affairs/Finance, College Dean/Program Chair, Registrar
- 📌 **Registrar-last enforcement** — Registrar can only sign after all other offices have approved
- 📎 **File uploads** (PDF, DOC, images up to 10MB) for supporting requirements
- 🔢 **Auto-generated approval codes** (CLR-YYMMDD-XXXXXX) per office signature
- ⚡ **Bulk approval** with smart filters (program, year level, section)

### Admin Tools
- 📊 **Stats dashboard** (total / pending / approved / rejected per role)
- 📜 **Full audit log** — every login, registration, signature, file upload, and admin action is logged with IP and timestamp; cursor pagination supported
- ✉️ **Email Settings UI** — DB-backed override of SendGrid API key, sender email, and sender name (no restart needed); built-in "Send test email" button
- 🔧 **User management** — search, role badges (Superadmin/Admin/Faculty/Student), one-click password reset with auto-suggested strong password generator

### Slip & Print
- 🖨️ **Official MinSU Clearance Slip** layout matching the paper template
- 📄 Same format on screen and when printed (A4 portrait)
- ✅ Auto-checked semester, campus, and college boxes
- 🖋️ "FOR VALIDATION - REGISTRAR'S OFFICE USE ONLY" signature block

### Notifications (via SendGrid)
- ✉️ Email verification code on registration
- 🔑 Password reset code
- 🎉 Clearance fully approved (with all signatures table)
- ⚠️ Clearance rejected (with reason)

---

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | **FastAPI** (Python 3.11+) on port 8001 |
| Frontend | **Vanilla JS SPA** + custom CSS, served by Node Express on port 3000 |
| Database | **MongoDB** (collections: `users`, `clearances`, `audit_logs`, `app_settings`) |
| Auth | **JWT** (PyJWT) + **bcrypt** password hashing |
| Email | **SendGrid** (`sendgrid` Python SDK) |
| File Storage | Local filesystem (`/app/backend/uploads/`) via `aiofiles` |
| Fonts | Manrope (UI) + Fraunces (headings) via Google Fonts |
| Icons | Font Awesome 6.5 (CDN) |

---

## 📁 Full System Structure

```
/app/
├── README.md                          # This file
├── yarn.lock
│
├── backend/                           # FastAPI backend (port 8001)
│   ├── server.py                      # All API routes (~1130 lines)
│   ├── requirements.txt               # Python dependencies
│   ├── .env                           # Secrets & config (DO NOT COMMIT)
│   ├── tests/
│   │   ├── backend_test.py            # Iter-1 baseline tests (38)
│   │   ├── test_iteration2.py         # CORS, password, faculty seed, bulk (32)
│   │   ├── test_iteration3.py         # Settings, password reset, change pw (28)
│   │   └── test_iteration5.py         # Superadmin role tests (30)
│   └── uploads/                       # Uploaded clearance attachments
│
├── frontend/                          # Vanilla JS SPA (port 3000)
│   ├── index.html                     # Single HTML entry point
│   ├── server.js                      # Express static server
│   ├── package.json                   # Node deps (express only)
│   ├── yarn.lock
│   ├── css/
│   │   └── style.css                  # Full design system + print styles
│   ├── js/
│   │   ├── app.js                     # Main SPA logic (~1370 lines)
│   │   └── dom-helpers.js             # Safe DOM construction helpers
│   ├── images/
│   │   ├── minsu-logo.jpg             # University logo
│   │   └── minsu-bg.jpg               # Login page background
│   └── node_modules/                  # (git-ignored)
│
├── memory/                            # Project documentation
│   ├── PRD.md                         # Product Requirements Document
│   └── test_credentials.md            # All test accounts & permissions matrix
│
└── test_reports/                      # Per-iteration test results
    ├── iteration_1.json               # 38/38 baseline tests
    ├── iteration_2.json               # 70/70 cumulative
    ├── iteration_3.json               # 98/98 cumulative
    └── iteration_4.json               # 128/128 cumulative (superadmin)
```

---

## 🚀 Quickstart (Local Setup)

### 1. Prerequisites
- Python 3.11+
- Node.js 18+ and Yarn
- MongoDB 4.4+ running on `localhost:27017`

### 2. Clone
```bash
git clone https://github.com/<your-user>/minsufinal.git
cd minsufinal
```

### 3. Backend Setup
```bash
cd backend
pip install -r requirements.txt
```

Create `backend/.env`:
```env
MONGO_URL="mongodb://localhost:27017"
DB_NAME="minsu_clearance"
CORS_ORIGINS="http://localhost:3000,http://localhost:8001"
JWT_SECRET="<generate with: python -c 'import secrets; print(secrets.token_hex(32))'>"
ADMIN_EMAIL="admin@minsu.edu.ph"
ADMIN_PASSWORD="Admin@123"
SUPERADMIN_EMAIL="superadmin@minsu.edu.ph"
SUPERADMIN_PASSWORD="Sup3rAdmin#2026"
SENDGRID_API_KEY=""              # Optional - leave blank to print codes to console
SENDER_EMAIL="noreply@minsu.edu.ph"
SENDER_NAME="MinSU Clearance System"
UPLOAD_DIR="./uploads"
```

Run backend:
```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

### 4. Frontend Setup
```bash
cd frontend
yarn install
yarn start    # serves on port 3000
```

### 5. First Login
Open http://localhost:3000 and log in:
- **Superadmin** → `superadmin@minsu.edu.ph` / `Sup3rAdmin#2026`
- **Admin** → `admin@minsu.edu.ph` / `Admin@123`
- **Faculty (6 offices auto-seeded)** → `<office>@minsu.edu.ph` / `Faculty@2026`
  - `universitylibrarian@minsu.edu.ph`
  - `guidancecounselor@minsu.edu.ph`
  - `sasdirector_coordinator@minsu.edu.ph`
  - `studentaffairs_finance@minsu.edu.ph`
  - `collegedean_programchair@minsu.edu.ph`
  - `registrar@minsu.edu.ph`

> **⚠️ Change all default passwords immediately after first login** via *My Account → Change Password* and *Users → Reset Password*.

---

## 🔌 API Reference

All endpoints are prefixed with `/api`. Authenticated endpoints require `Authorization: Bearer <token>` header.

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Student self-registration |
| POST | `/auth/verify-email` | Submit 6-digit OTP code |
| POST | `/auth/resend-verification` | Request a new OTP |
| POST | `/auth/login` | Returns `access_token` (24h JWT) |
| GET  | `/auth/me` | Current user profile |
| POST | `/auth/logout` | Sign out (logged in audit) |
| POST | `/auth/forgot-password` | Request reset code |
| POST | `/auth/reset-password` | Submit reset code + new password |
| POST | `/auth/change-password` | Self-service password change |

### Clearances
| Method | Endpoint | Description |
|---|---|---|
| POST | `/clearances/create` | Student creates new clearance |
| GET  | `/clearances/list` | Filterable list (status, course, year_level, section) |
| GET  | `/clearances/{id}` | Detail view |
| POST | `/clearances/{id}/process` | Faculty approve/reject |
| POST | `/clearances/bulk-process` | Faculty batch approve/reject |
| POST | `/clearances/{id}/upload` | Multipart file upload |
| GET  | `/clearances/{id}/attachments/{attachment_id}/download` | Stream attached file |

### Admin (admin or superadmin role)
| Method | Endpoint | Description |
|---|---|---|
| GET  | `/admin/users` | List with search & pagination |
| POST | `/admin/create-user` | Create faculty (admin/superadmin needed for higher roles) |
| DELETE | `/admin/users/{id}` | Delete user (with role-based protections) |
| GET  | `/admin/users/{id}/suggest-password` | Auto-generate a strong password |
| POST | `/admin/users/{id}/reset-password` | Admin-triggered password reset |
| GET  | `/admin/audit-logs` | Logs (supports `?cursor=<timestamp>` for cursor pagination) |
| GET  | `/admin/settings` | Current SendGrid config (key always masked) |
| POST | `/admin/settings` | Update SendGrid key/sender |
| POST | `/admin/settings/test-email` | Verify config via real send |

### Utility
| Method | Endpoint | Description |
|---|---|---|
| GET  | `/` | Health check |
| GET  | `/constants` | Returns offices, courses, year levels, sections, campuses, colleges, clearance types |
| GET  | `/stats` | Role-aware counts (total/pending/approved/rejected) |

---

## 🧪 Tests

The project ships with **128 backend pytest cases** across 4 test files in `/app/backend/tests/`.

```bash
cd backend
pytest tests/ -v
```

Test reports are written to `/app/test_reports/iteration_*.json`.

---

## 🌐 Deployment Notes

### Environment-aware routing
- The frontend uses **same-origin** requests (`/api/*`). When deployed behind a reverse proxy (e.g. Kubernetes ingress, Nginx, Cloudflare), make sure `/api/*` is routed to backend port 8001 and everything else to frontend port 3000.
- For Vercel/Railway/Render, you can either:
  - Deploy backend and frontend as separate services and set `REACT_APP_BACKEND_URL` (currently uses same-origin)
  - Or use a reverse-proxy service (e.g. Nginx) to combine them under one domain

### SendGrid Setup
1. Sign up at https://sendgrid.com (free tier: 100 emails/day)
2. Create API key with **Mail Send** permission
3. Verify your sender email in **Settings → Sender Authentication → Single Sender Verification**
4. Either:
   - Set in `backend/.env`: `SENDGRID_API_KEY=<key>` and `SENDER_EMAIL=<verified-email>`
   - **OR** log in as admin/superadmin and configure via **Email Settings** page (DB-backed, no restart)

### Security Hardening (before going live)
- [ ] Rotate `JWT_SECRET` in `.env`
- [ ] Change all default seeded passwords (admin + superadmin + 6 faculty)
- [ ] Tighten `CORS_ORIGINS` to your production domain only
- [ ] Use **MongoDB Atlas** with TLS instead of localhost
- [ ] Enable **SendGrid Domain Authentication** (better deliverability than single-sender)
- [ ] Add rate limiting (e.g. SlowAPI middleware) on `/auth/login` and `/auth/register`
- [ ] Use a real reverse proxy with HTTPS (Caddy, Nginx, Cloudflare)

---

## 📦 Database Collections

### `users`
```json
{
  "id": "uuid",
  "email": "lowercased@minsu.edu.ph",
  "password_hash": "bcrypt-hash",
  "full_name": "string",
  "role": "student | faculty | admin | superadmin",
  "office": "string (faculty only)",
  "student_id": "string (student only)",
  "course": "BSIT, BSCS, ...",
  "year_level": "1st Year | 2nd Year | 3rd Year | 4th Year",
  "section": "F1 | F2 | F3",
  "campus": "MMC | MBC | MCC",
  "college": "CCS | CTE | ...",
  "email_verified": true,
  "verification_code": "string (transient)",
  "verification_expires": "ISO datetime",
  "reset_code": "string (transient)",
  "created_at": "ISO datetime"
}
```

### `clearances`
```json
{
  "id": "uuid",
  "student_id": "uuid",
  "student_name": "string",
  "student_email": "string",
  "student_number": "string",
  "course": "string",
  "year_level": "string",
  "section": "string",
  "campus": "string",
  "college": "string",
  "semester": "1st Semester | 2nd Semester | Summer",
  "academic_year": "2025-2026",
  "clearance_type": "End of Semester | Graduation | ...",
  "purpose": "optional string",
  "overall_status": "pending | approved | rejected",
  "approvals": [
    {
      "office": "Registrar",
      "status": "pending | approved | rejected",
      "approved_by": "uuid",
      "approved_by_name": "string",
      "approved_at": "ISO datetime",
      "comments": "string",
      "approval_code": "CLR-YYMMDD-XXXXXX"
    }
  ],
  "attachments": [
    {
      "id": "uuid",
      "original_name": "scan.pdf",
      "stored_name": "uuid.pdf",
      "size": 12345,
      "content_type": "application/pdf",
      "description": "string",
      "office": "string",
      "uploaded_by": "uuid",
      "uploaded_by_name": "string",
      "uploaded_at": "ISO datetime"
    }
  ],
  "created_at": "ISO datetime",
  "updated_at": "ISO datetime",
  "completed_at": "ISO datetime"
}
```

### `audit_logs`
```json
{
  "id": "uuid",
  "actor_id": "uuid",
  "actor_email": "string",
  "actor_role": "string",
  "action": "LOGIN_SUCCESS | CLEARANCE_CREATED | ...",
  "target_type": "user | clearance | settings",
  "target_id": "uuid",
  "details": { "...": "..." },
  "ip": "string",
  "timestamp": "ISO datetime"
}
```

### `app_settings`
```json
{
  "key": "sendgrid_api_key | sender_email | sender_name",
  "value": "string",
  "updated_at": "ISO datetime",
  "updated_by": "email"
}
```

---

## 👥 Default Seeded Accounts

| Email | Role | Default Password |
|---|---|---|
| `superadmin@minsu.edu.ph` | superadmin | `Sup3rAdmin#2026` |
| `admin@minsu.edu.ph` | admin | `Admin@123` |
| `universitylibrarian@minsu.edu.ph` | faculty (Librarian) | `Faculty@2026` |
| `guidancecounselor@minsu.edu.ph` | faculty (Guidance) | `Faculty@2026` |
| `sasdirector_coordinator@minsu.edu.ph` | faculty (SAS) | `Faculty@2026` |
| `studentaffairs_finance@minsu.edu.ph` | faculty (Finance) | `Faculty@2026` |
| `collegedean_programchair@minsu.edu.ph` | faculty (Dean) | `Faculty@2026` |
| `registrar@minsu.edu.ph` | faculty (Registrar) | `Faculty@2026` |

> **Change all defaults immediately in production.**

---

## 📜 License

Built for **Mindoro State University** internal use.

---

## 🙏 Credits

- Original concept: [@jhamelma2013-coder](https://github.com/jhamelma2013-coder/minsu_clearance_system)
- Enhanced & rebuilt on the **Emergent platform** with JWT auth, audit log, file uploads, multiple clearance types, official slip layout, superadmin role, and admin Email Settings UI
