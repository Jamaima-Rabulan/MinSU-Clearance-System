# MinSU Clearance System — PHP Edition (Hostinger-Ready)

A pure PHP + MySQL rewrite of the MinSU Clearance System that keeps 100% of the
original functionality (student clearances, 6-office approval workflow with
Registrar-last rule, digital signatures, printable slip, admin panel) and
**adds these security hardenings**:

- **Bcrypt** password hashing via `password_hash(PASSWORD_BCRYPT)`
- **Password policy** enforced at register: min 8 chars, at least 1 letter + 1 number
- **Brute-force lockout** on `/api/auth/login`: 5 failed attempts → 15-min lock (per IP+email)
- **Session-based auth** via native `$_SESSION` with HTTP-only, SameSite=Lax cookies
- **Server-side validation** for every request (roles, offices, campuses, courses, year levels, sections, semesters, UUID formats, sizes)
- **Full audit log** written for every meaningful action (register, login success/failure, logout, clearance create/approve/reject, admin delete_user, brute-force lockout)

Zero build step. Uses PHP 8.x + MySQL/MariaDB 10.x — the exact stack included
free with every Hostinger shared-hosting plan.

## Directory Layout
```
php/
├── schema.sql                       ← Run once in phpMyAdmin
└── public/                          ← Upload contents of this folder to `public_html/`
    ├── .htaccess                    ← Pretty-URL routing + security headers
    ├── index.html                   ← SPA shell
    ├── css/style.css                ← MinSU palette + typography
    ├── js/app.js                    ← SPA client
    ├── images/*                     ← MinSU logo, background
    └── api/
        ├── index.php                ← Front controller (all routes)
        ├── config.php               ← Your DB creds live here (git-ignored)
        ├── config.example.php       ← Copy → config.php, then edit
        └── lib/
            ├── bootstrap.php        ← Session, PDO, CORS, admin seed
            ├── util.php             ← Validation + constants + helpers
            ├── auth.php             ← Session + brute-force lockout
            └── audit.php            ← Audit log writer
```

## Deploy to Hostinger — 5 Steps

### 1. Create the database
1. Log in to **hPanel → Databases → MySQL Databases**.
2. Click **Create database**. Note down: database name, username, password, host (usually `localhost`).

### 2. Import the schema
1. Open **phpMyAdmin** for the new database (from hPanel).
2. Click the **Import** tab → choose `schema.sql` → **Go**.
3. You should see 5 tables: `users`, `clearances`, `clearance_approvals`, `audit_logs`, `login_attempts`.

### 3. Configure the app
1. On your machine, open `public/api/config.example.php`, copy to `config.php`.
2. Edit `config.php` with the DB creds from Step 1.
3. (Optional) Change `admin.email` / `admin.password` — this account is auto-seeded on first request.

### 4. Upload the files
Two options:

**a) File Manager (easiest)** — hPanel → **File Manager** → open `public_html` → **Upload files** → drag the entire contents of `public/` (not the `public/` folder itself, its **contents**).

**b) FTP** — Use FileZilla with the FTP account from **hPanel → FTP Accounts**.
Upload contents of `public/` into `public_html/`.

Final structure on server should be:
```
public_html/
├── .htaccess
├── index.html
├── css/
├── js/
├── images/
└── api/
    ├── index.php
    ├── config.php
    └── lib/…
```

### 5. Test it
1. Visit `https://your-domain.com/` — you should see the MinSU login page.
2. Sign in with the default admin (`admin@minsu.edu.ph` / `Admin@MinSU2025`).
3. Immediately after logging in, go to **Users → your admin → change password**
   (or edit `config.php` and refresh — the seed will resync the hash).
4. Register a **faculty** account for each of the 6 offices and a **student** to try the full flow.

That's it — you're live.

## Local Testing (Optional)
```bash
# 1. Start MySQL
mariadbd --user=mysql --datadir=/var/lib/mysql --socket=/tmp/mysqld.sock &

# 2. Create DB + schema
mysql -u root -e "CREATE DATABASE minsu_clearance CHARACTER SET utf8mb4;"
mysql -u root minsu_clearance < php/schema.sql
mysql -u root -e "CREATE USER 'minsu'@'localhost' IDENTIFIED BY 'MinSU2025';
                  GRANT ALL ON minsu_clearance.* TO 'minsu'@'localhost';"

# 3. Serve
cd php/public
php -S localhost:8080 -t .

# 4. Open http://localhost:8080/
```

## Endpoint Reference (session-authenticated except `/auth/*` and `/constants`)

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/`                                    | health check |
| GET  | `/api/constants`                           | offices, courses, campuses, colleges, year levels, sections |
| POST | `/api/auth/register`                       | validated register (any role) |
| POST | `/api/auth/login`                          | bcrypt verify + brute-force lockout |
| POST | `/api/auth/logout`                         | destroy session |
| GET  | `/api/auth/me`                             | current user (or 401) |
| POST | `/api/clearances/create`                   | student only |
| GET  | `/api/clearances/list`                     | role-scoped |
| GET  | `/api/clearances/{id}`                     | student sees own, others see any |
| POST | `/api/clearances/{id}/process`             | faculty approve/reject |
| GET  | `/api/clearances/{id}/audit-trail`         | timeline for a clearance |
| GET  | `/api/stats`                               | role-scoped counts |
| GET  | `/api/admin/users`                         | admin only |
| DELETE | `/api/admin/users/{id}`                  | admin only |
| GET  | `/api/admin/audit-logs`                    | admin only (filterable) |
| GET  | `/api/admin/audit-logs/actions`            | distinct actions/resources for filters |

## Security Notes
- Passwords are hashed with **bcrypt** — hashes stored are `$2y$...` on Hostinger's PHP 8.x.
- Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` when HTTPS is detected.
- Every failure and success writes an entry to `audit_logs` with client IP + user agent.
- Direct access to `/api/lib/*` is blocked via `.htaccess` rules.
- Direct download of `config.php`, `schema.sql`, `.env` etc. is denied.
- `session_regenerate_id(true)` is called after login/register to prevent fixation.
- Validation is enforced server-side on every request (role, office, campus, college,
  course, year level, section, semester, UUID format, size caps).

## Default Credentials (change immediately after first login!)
- Admin: `admin@minsu.edu.ph` / `Admin@MinSU2025` (change in `config.php`)
