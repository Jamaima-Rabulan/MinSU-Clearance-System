// MinSU Clearance System - Main App (vanilla JS loaded by React shell)

const API_URL =
    (typeof window !== "undefined" && window.__MINSU_BACKEND_URL__) ||
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1"
        ? "http://localhost:8001"
        : "");

// State
let currentUser = null;
let constants = {
    offices: [],
    courses: [],
    year_levels: [],
    sections: [],
    campuses: [],
    colleges: [],
};

// ============= VALIDATION =============
const Validate = {
    email(v) {
        if (!v) return "Email is required";
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return "Enter a valid email address";
        return null;
    },
    password(v, { strict = false } = {}) {
        if (!v) return "Password is required";
        if (!strict) return null;
        if (v.length < 8) return "Password must be at least 8 characters";
        if (!/[A-Za-z]/.test(v)) return "Password must contain at least one letter";
        if (!/\d/.test(v)) return "Password must contain at least one number";
        return null;
    },
    fullName(v) {
        v = (v || "").trim();
        if (v.length < 3) return "Full name must be at least 3 characters";
        if (v.length > 120) return "Full name is too long";
        if (!/^[A-Za-zÀ-ÿ .,'\-]+$/.test(v)) return "Full name contains invalid characters";
        return null;
    },
    studentId(v) {
        v = (v || "").trim();
        if (!v) return "Student ID is required";
        if (!/^[A-Za-z0-9\-]{4,20}$/.test(v)) return "Student ID must be 4–20 chars (letters, digits, dashes)";
        return null;
    },
    required(v, label) {
        if (!v || (typeof v === "string" && !v.trim())) return `${label} is required`;
        return null;
    },
    academicYear(v) {
        if (!v) return "Academic Year is required";
        if (!/^\d{4}-\d{4}$/.test(v)) return "Academic year must be like 2025-2026";
        const [a, b] = v.split("-").map(Number);
        if (b !== a + 1) return "Academic year end must be one year after start";
        return null;
    },
    comments(v, { requiredMsg = null, max = 500 } = {}) {
        if (requiredMsg && (!v || !v.trim())) return requiredMsg;
        if (v && v.length > max) return `Comments must be at most ${max} characters`;
        return null;
    },
};

function setFieldError(inputId, message) {
    const el = document.getElementById(inputId);
    if (!el) return;
    // Remove existing error message
    let errEl = el.parentElement.querySelector(".field-error");
    if (errEl) errEl.remove();
    el.classList.remove("input-error");
    if (message) {
        el.classList.add("input-error");
        errEl = document.createElement("div");
        errEl.className = "field-error";
        errEl.textContent = message;
        el.parentElement.appendChild(errEl);
    }
}

function clearAllFieldErrors(formEl) {
    (formEl || document).querySelectorAll(".field-error").forEach((n) => n.remove());
    (formEl || document).querySelectorAll(".input-error").forEach((n) => n.classList.remove("input-error"));
}

// ============= API HELPER =============
const API = {
    async call(endpoint, options = {}) {
        try {
            const response = await fetch(`${API_URL}/api${endpoint}`, {
                ...options,
                headers: {
                    "Content-Type": "application/json",
                    ...options.headers,
                },
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                const msg =
                    typeof data.detail === "string"
                        ? data.detail
                        : Array.isArray(data.detail)
                        ? data.detail.map((d) => d.msg || JSON.stringify(d)).join(" ")
                        : "Request failed";
                throw new Error(msg);
            }
            return data;
        } catch (error) {
            showToast(error.message, "error");
            throw error;
        }
    },
    register: (u) => API.call("/auth/register", { method: "POST", body: JSON.stringify(u) }),
    login: (c) => API.call("/auth/login", { method: "POST", body: JSON.stringify(c) }),
    logout: (id) => API.call(`/auth/logout?user_id=${id}`, { method: "POST" }),
    createClearance: (d, id) =>
        API.call(`/clearances/create?user_id=${id}`, { method: "POST", body: JSON.stringify(d) }),
    getClearances: (id, filters = {}) => {
        let url = `/clearances/list?user_id=${id}`;
        Object.keys(filters).forEach((k) => {
            if (filters[k]) url += `&${k}=${encodeURIComponent(filters[k])}`;
        });
        return API.call(url);
    },
    getClearance: (cid, uid) => API.call(`/clearances/${cid}?user_id=${uid}`),
    processClearance: (cid, d, uid) =>
        API.call(`/clearances/${cid}/process?user_id=${uid}`, { method: "POST", body: JSON.stringify(d) }),
    getStats: (id) => API.call(`/stats?user_id=${id}`),
    getConstants: () => API.call("/constants"),
    getUsers: (id) => API.call(`/admin/users?user_id=${id}`),
    deleteUser: (target, id) => API.call(`/admin/users/${target}?user_id=${id}`, { method: "DELETE" }),
    unlockUser: (target, id) => API.call(`/admin/users/${target}/unlock?user_id=${id}`, { method: "POST" }),
    getAuditLogs: (id, filters = {}) => {
        let url = `/admin/audit-logs?user_id=${id}`;
        Object.keys(filters).forEach((k) => {
            if (filters[k]) url += `&${k}=${encodeURIComponent(filters[k])}`;
        });
        return API.call(url);
    },
    getAuditLogActions: (id) => API.call(`/admin/audit-logs/actions?user_id=${id}`),
    getClearanceAuditTrail: (cid, uid) => API.call(`/clearances/${cid}/audit-trail?user_id=${uid}`),
};

// ============= UTILITIES =============
function showToast(message, type = "success") {
    const existing = document.querySelector(".toast");
    if (existing) existing.remove();
    const icons = {
        success:
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
        error:
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
        warning:
            '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    };
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.setAttribute("data-testid", `toast-${type}`);
    toast.innerHTML = `${icons[type] || ""}<span>${message}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

function formatDate(dateString) {
    if (!dateString) return "";
    return new Date(dateString).toLocaleDateString("en-PH", {
        year: "numeric",
        month: "short",
        day: "numeric",
    });
}
function formatDateTime(dateString) {
    if (!dateString) return "";
    return new Date(dateString).toLocaleString("en-PH", {
        year: "numeric", month: "short", day: "numeric",
        hour: "2-digit", minute: "2-digit",
    });
}
function escapeHtml(s) {
    if (s === undefined || s === null) return "";
    return String(s)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
function getStatusBadge(status) {
    return `<span class="badge badge-${status}">${escapeHtml(status)}</span>`;
}
function saveUser(user) {
    if (!user) { currentUser = null; localStorage.removeItem("minsu_user"); return; }
    currentUser = user;
    localStorage.setItem("minsu_user", JSON.stringify(user));
}
function loadUser() {
    const saved = localStorage.getItem("minsu_user");
    if (!saved) return null;
    try {
        const parsed = JSON.parse(saved);
        if (!parsed || typeof parsed !== "object") throw new Error("invalid stored user");
        currentUser = parsed;
        return currentUser;
    } catch (e) {
        // Corrupted/invalid value (e.g. "undefined") — clear it instead of crashing the app.
        localStorage.removeItem("minsu_user");
        currentUser = null;
        return null;
    }
}
async function logout() {
    try { if (currentUser) await API.logout(currentUser.id); } catch (e) {}
    currentUser = null;
    localStorage.removeItem("minsu_user");
    renderApp();
}
function getSavedSignature() { return localStorage.getItem(`minsu_signature_${currentUser?.id}`); }
function saveSignature(data) {
    localStorage.setItem(`minsu_signature_${currentUser?.id}`, data);
    showToast("Signature saved!", "success");
}

// ============= SIGNATURE PAD =============
class SignaturePad {
    constructor(canvas) {
        this.canvas = canvas;
        this.ctx = canvas.getContext("2d");
        this.isDrawing = false; this.lastX = 0; this.lastY = 0;
        this.setupCanvas(); this.bindEvents();
    }
    setupCanvas() {
        const rect = this.canvas.getBoundingClientRect();
        this.canvas.width = rect.width * 2;
        this.canvas.height = rect.height * 2;
        this.ctx.scale(2, 2);
        this.ctx.lineCap = "round"; this.ctx.lineJoin = "round";
        this.ctx.lineWidth = 2.5; this.ctx.strokeStyle = "#14532D";
        this.clear();
    }
    bindEvents() {
        this.canvas.addEventListener("mousedown", (e) => this.startDrawing(e));
        this.canvas.addEventListener("mousemove", (e) => this.draw(e));
        this.canvas.addEventListener("mouseup", () => this.stopDrawing());
        this.canvas.addEventListener("mouseout", () => this.stopDrawing());
        this.canvas.addEventListener("touchstart", (e) => { e.preventDefault(); this.startDrawing(e.touches[0]); });
        this.canvas.addEventListener("touchmove", (e) => { e.preventDefault(); this.draw(e.touches[0]); });
        this.canvas.addEventListener("touchend", () => this.stopDrawing());
    }
    getPos(e) { const r = this.canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
    startDrawing(e) { this.isDrawing = true; const p = this.getPos(e); this.lastX = p.x; this.lastY = p.y; }
    draw(e) {
        if (!this.isDrawing) return;
        const p = this.getPos(e);
        this.ctx.beginPath(); this.ctx.moveTo(this.lastX, this.lastY);
        this.ctx.lineTo(p.x, p.y); this.ctx.stroke();
        this.lastX = p.x; this.lastY = p.y;
    }
    stopDrawing() { this.isDrawing = false; }
    clear() { this.ctx.fillStyle = "#fff"; this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height); }
    isEmpty() {
        const d = this.ctx.getImageData(0, 0, this.canvas.width, this.canvas.height);
        for (let i = 0; i < d.data.length; i += 4) {
            if (d.data[i] !== 255 || d.data[i + 1] !== 255 || d.data[i + 2] !== 255) return false;
        }
        return true;
    }
    toDataURL() { return this.canvas.toDataURL("image/png"); }
}

// ============= LOGIN =============
function renderLoginPage() {
    const app = document.getElementById("app");
    app.innerHTML = `
    <div class="login-wrapper">
      <div class="login-left">
        <div class="login-box">
          <div class="login-header">
            <div class="login-logo">
              <img src="/images/minsu-logo.jpg" alt="MinSU Logo">
            </div>
            <h1>MinSU Clearance</h1>
            <p>Mindoro State University</p>
            <p class="subtitle">Office of Student Affairs Services</p>
          </div>

          <div class="tabs">
            <button class="tab active" data-tab="login-tab" data-testid="tab-login">Sign In</button>
            <button class="tab" data-tab="register-tab" data-testid="tab-register">Register</button>
          </div>

          <div id="login-tab" class="tab-content active">
            <form id="loginForm" novalidate data-testid="login-form">
              <div class="form-group">
                <label>Email Address</label>
                <input type="email" id="login-email" placeholder="you@minsu.edu.ph" data-testid="login-email-input" required>
              </div>
              <div class="form-group">
                <label>Password</label>
                <input type="password" id="login-password" placeholder="Enter your password" data-testid="login-password-input" required>
              </div>
              <button type="submit" class="btn btn-primary btn-block btn-lg" data-testid="login-submit-button">Sign In</button>
              <p class="text-muted text-center" style="margin-top:1rem;font-size:0.85rem;">
                Default admin: <strong>admin@minsu.edu.ph</strong> / <strong>Admin@MinSU2025</strong>
              </p>
            </form>
          </div>

          <div id="register-tab" class="tab-content">
            <form id="registerForm" novalidate data-testid="register-form">
              <div class="form-group">
                <label>Full Name (Last, First, MI)</label>
                <input type="text" id="register-name" placeholder="Dela Cruz, Juan A." data-testid="register-name-input" required>
              </div>
              <div class="form-group">
                <label>Email Address</label>
                <input type="email" id="register-email" placeholder="you@minsu.edu.ph" data-testid="register-email-input" required>
              </div>
              <div class="form-group">
                <label>Password</label>
                <input type="password" id="register-password" placeholder="Create a password" data-testid="register-password-input" required>
              </div>
              <div class="form-group">
                <label>I am a</label>
                <select id="register-role" data-testid="register-role-select" required>
                  <option value="student">Student</option>
                  <option value="faculty">Faculty / Clearing Officer</option>
                  <option value="admin">Administrator</option>
                </select>
              </div>

              <div id="student-fields">
                <div class="form-group">
                  <label>Student Number</label>
                  <input type="text" id="register-student-id" placeholder="MBC2024-00749" data-testid="register-student-id-input">
                </div>
                <div class="form-row">
                  <div class="form-group">
                    <label>Campus</label>
                    <select id="register-campus" data-testid="register-campus-select">
                      <option value="">Select</option>
                      ${(constants.campuses || []).map((c) => `<option value="${c}">${c}</option>`).join("")}
                    </select>
                  </div>
                  <div class="form-group">
                    <label>College</label>
                    <select id="register-college" data-testid="register-college-select">
                      <option value="">Select</option>
                      ${(constants.colleges || []).map((c) => `<option value="${c}">${c}</option>`).join("")}
                    </select>
                  </div>
                </div>
                <div class="form-group">
                  <label>Course/Program</label>
                  <select id="register-course" data-testid="register-course-select">
                    <option value="">Select Course</option>
                    ${(constants.courses || []).map((c) => `<option value="${c}">${c}</option>`).join("")}
                  </select>
                </div>
                <div class="form-row">
                  <div class="form-group">
                    <label>Year Level</label>
                    <select id="register-year" data-testid="register-year-select">
                      <option value="">Select</option>
                      ${(constants.year_levels || []).map((y) => `<option value="${y}">${y}</option>`).join("")}
                    </select>
                  </div>
                  <div class="form-group">
                    <label>Section</label>
                    <select id="register-section" data-testid="register-section-select">
                      <option value="">Select</option>
                      ${(constants.sections || []).map((s) => `<option value="${s}">${s}</option>`).join("")}
                    </select>
                  </div>
                </div>
              </div>

              <div id="faculty-fields" class="hidden">
                <div class="form-group">
                  <label>Office / Position</label>
                  <select id="register-office" data-testid="register-office-select">
                    <option value="">Select Office</option>
                    ${(constants.offices || []).map((o) => `<option value="${o}">${o}</option>`).join("")}
                  </select>
                </div>
              </div>

              <button type="submit" class="btn btn-primary btn-block btn-lg" data-testid="register-submit-button">Create Account</button>
            </form>
          </div>
        </div>
      </div>

      <div class="login-right">
        <div class="login-right-content">
          <h2>Welcome to MinSU</h2>
          <p>Your paperless student clearance.</p>
        </div>
      </div>
    </div>
  `;
    setupLoginEvents();
}

function setupLoginEvents() {
    document.querySelectorAll(".tab").forEach((tab) => {
        tab.addEventListener("click", () => {
            document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
            document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
            tab.classList.add("active");
            document.getElementById(tab.dataset.tab).classList.add("active");
        });
    });

    document.getElementById("register-role").addEventListener("change", (e) => {
        document.getElementById("student-fields").classList.toggle("hidden", e.target.value !== "student");
        document.getElementById("faculty-fields").classList.toggle("hidden", e.target.value !== "faculty");
    });

    // Real-time validation on blur for register fields
    const wire = (id, fn) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener("blur", () => setFieldError(id, fn(el.value)));
        el.addEventListener("input", () => {
            if (el.classList.contains("input-error")) setFieldError(id, fn(el.value));
        });
    };
    wire("register-name", (v) => Validate.fullName(v));
    wire("register-email", (v) => Validate.email(v.trim()));
    wire("register-password", (v) => Validate.password(v, { strict: true }));
    wire("register-student-id", (v) => Validate.studentId(v));
    wire("login-email", (v) => Validate.email(v.trim()));
    wire("login-password", (v) => Validate.password(v));

    // Live password strength meter for register
    const pwEl = document.getElementById("register-password");
    if (pwEl) {
        const meter = document.createElement("div");
        meter.className = "password-strength";
        meter.innerHTML = '<div class="strength-bar"><span></span></div><div class="strength-hint">Password must be 8+ chars with a letter and a number.</div>';
        pwEl.parentElement.appendChild(meter);
        pwEl.addEventListener("input", () => {
            const v = pwEl.value || "";
            let s = 0;
            if (v.length >= 8) s++;
            if (/[A-Za-z]/.test(v) && /\d/.test(v)) s++;
            if (/[^A-Za-z0-9]/.test(v)) s++;
            if (v.length >= 12) s++;
            const bar = meter.querySelector(".strength-bar span");
            bar.style.width = `${(s / 4) * 100}%`;
            bar.dataset.level = s;
        });
    }

    document.getElementById("loginForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.target;
        clearAllFieldErrors(form);

        const email = document.getElementById("login-email").value.trim();
        const password = document.getElementById("login-password").value;
        let hasErr = false;
        const emailErr = Validate.email(email);
        const pwErr = Validate.password(password);
        if (emailErr) { setFieldError("login-email", emailErr); hasErr = true; }
        if (pwErr)    { setFieldError("login-password", pwErr);  hasErr = true; }
        if (hasErr) { showToast("Please fix the highlighted fields", "warning"); return; }

        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true; btn.textContent = "Signing in...";
        try {
            const result = await API.login({ email, password });
            saveUser(result.user);
            showToast("Welcome back!");
            renderApp();
        } catch {
            btn.disabled = false; btn.textContent = "Sign In";
        }
    });

    document.getElementById("registerForm").addEventListener("submit", async (e) => {
        e.preventDefault();
        const form = e.target;
        clearAllFieldErrors(form);
        const role = document.getElementById("register-role").value;

        const fullName = document.getElementById("register-name").value;
        const email    = document.getElementById("register-email").value.trim();
        const password = document.getElementById("register-password").value;

        const errors = {
            "register-name":     Validate.fullName(fullName),
            "register-email":    Validate.email(email),
            "register-password": Validate.password(password, { strict: true }),
        };

        const userData = { email, password, full_name: fullName.trim(), role };

        if (role === "student") {
            const sid    = document.getElementById("register-student-id").value.trim();
            const campus = document.getElementById("register-campus").value;
            const college = document.getElementById("register-college").value;
            const course = document.getElementById("register-course").value;
            const year   = document.getElementById("register-year").value;
            const section = document.getElementById("register-section").value;
            errors["register-student-id"] = Validate.studentId(sid);
            errors["register-campus"]  = Validate.required(campus,  "Campus");
            errors["register-college"] = Validate.required(college, "College");
            errors["register-course"]  = Validate.required(course,  "Course");
            errors["register-year"]    = Validate.required(year,    "Year Level");
            errors["register-section"] = Validate.required(section, "Section");
            Object.assign(userData, { student_id: sid, campus, college, course, year_level: year, section });
        } else if (role === "faculty") {
            const office = document.getElementById("register-office").value;
            errors["register-office"] = Validate.required(office, "Office");
            userData.office = office;
        }

        let hasErr = false;
        Object.entries(errors).forEach(([id, msg]) => {
            if (msg) { setFieldError(id, msg); hasErr = true; }
        });
        if (hasErr) { showToast("Please fix the highlighted fields", "warning"); return; }

        const btn = form.querySelector('button[type="submit"]');
        btn.disabled = true; btn.textContent = "Creating account...";
        try {
            const result = await API.register(userData);
            saveUser(result.user);
            showToast("Account created successfully!");
            renderApp();
        } catch {
            btn.disabled = false; btn.textContent = "Create Account";
        }
    });
}

// ============= DASHBOARD =============
let currentView = "dashboard"; // dashboard | users | audit

function renderDashboard() {
    const app = document.getElementById("app");
    const isAdmin = currentUser.role === "admin";
    app.innerHTML = `
    <header class="header">
      <div class="header-container">
        <a href="#" class="logo" onclick="switchView('dashboard'); return false;" data-testid="header-logo">
          <img src="/images/minsu-logo.jpg" alt="MinSU" class="logo-img">
          <div class="logo-text">
            <h1>MinSU Clearance</h1>
            <p>Office of Student Affairs Services</p>
          </div>
        </a>
        <nav class="header-nav">
          <button class="nav-link ${currentView === "dashboard" ? "active" : ""}" onclick="switchView('dashboard')" data-testid="nav-dashboard">Dashboard</button>
          ${isAdmin ? `
            <button class="nav-link ${currentView === "users" ? "active" : ""}" onclick="switchView('users')" data-testid="nav-users">Users</button>
            <button class="nav-link ${currentView === "audit" ? "active" : ""}" onclick="switchView('audit')" data-testid="nav-audit">Audit Trail</button>
          ` : ""}
        </nav>
        <div class="user-info">
          <div class="user-details">
            <div class="user-name">${escapeHtml(currentUser.full_name)}</div>
            <div class="user-role">${currentUser.role}${currentUser.office ? ` • ${escapeHtml(currentUser.office)}` : ""}</div>
          </div>
          <button class="btn btn-ghost btn-sm" onclick="logout()" data-testid="logout-button">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Logout
          </button>
        </div>
      </div>
    </header>
    <div class="container">
      <div id="dashboard-content"><div class="loading"><div class="spinner"></div></div></div>
    </div>
  `;
    if (currentView === "users") loadUsersContent();
    else if (currentView === "audit") loadAuditContent();
    else loadDashboardContent();
}

function switchView(view) {
    currentView = view;
    renderDashboard();
}

let allClearances = [];

async function loadDashboardContent() {
    try {
        const [statsData, clearancesData] = await Promise.all([
            API.getStats(currentUser.id),
            API.getClearances(currentUser.id),
        ]);
        allClearances = clearancesData.clearances || [];
        renderDashboardContent(statsData, allClearances);
    } catch {
        document.getElementById("dashboard-content").innerHTML = `
      <div class="card card-body text-center">
        <p class="text-danger">Failed to load dashboard</p>
        <button class="btn btn-secondary mt-2" onclick="loadDashboardContent()">Retry</button>
      </div>`;
    }
}

function renderDashboardContent(stats, clearances) {
    const container = document.getElementById("dashboard-content");
    const isStudent = currentUser.role === "student";
    const isFaculty = currentUser.role === "faculty";
    const isAdmin = currentUser.role === "admin";

    container.innerHTML = `
    <div class="flex-between dashboard-header">
      <div>
        <h1 data-testid="dashboard-welcome">Welcome, ${escapeHtml((currentUser.full_name || "").split(",")[0] || currentUser.full_name)}!</h1>
        <p class="text-secondary">${isStudent ? `${escapeHtml(currentUser.campus || "")} • ${escapeHtml(currentUser.college || "")} • ${escapeHtml(currentUser.course || "")} • ${escapeHtml(currentUser.year_level || "")} - ${escapeHtml(currentUser.section || "")}` : escapeHtml(currentUser.office || "System Administrator")}</p>
      </div>
      <div class="dashboard-actions">
        ${isStudent ? `<button class="btn btn-primary" onclick="openCreateClearanceModal()" data-testid="new-clearance-button">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          New Clearance
        </button>` : ""}
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card" onclick="filterClearances('')" data-testid="stat-total">
        <div class="stat-info"><p>Total</p><div class="stat-value">${stats.total}</div></div>
        <div class="stat-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
      </div>
      <div class="stat-card" onclick="filterClearances('pending')" data-testid="stat-pending">
        <div class="stat-info"><p>Pending</p><div class="stat-value">${stats.pending}</div></div>
        <div class="stat-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg></div>
      </div>
      <div class="stat-card" onclick="filterClearances('approved')" data-testid="stat-approved">
        <div class="stat-info"><p>Approved</p><div class="stat-value">${stats.approved}</div></div>
        <div class="stat-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg></div>
      </div>
      <div class="stat-card" onclick="filterClearances('rejected')" data-testid="stat-rejected">
        <div class="stat-info"><p>Rejected</p><div class="stat-value">${stats.rejected}</div></div>
        <div class="stat-icon"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg></div>
      </div>
    </div>

    ${(isFaculty || isAdmin) ? `
      <div class="search-container">
        <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="search" id="search-input" placeholder="Search by student name, ID, or email..." onkeyup="searchClearances()" data-testid="search-input">
      </div>
      <div class="filters">
        <div class="filter-group"><label>Campus</label>
          <select id="filter-campus" onchange="applyFilters()">
            <option value="">All</option>
            ${(constants.campuses || []).map((c) => `<option value="${c}">${c}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>College</label>
          <select id="filter-college" onchange="applyFilters()">
            <option value="">All</option>
            ${(constants.colleges || []).map((c) => `<option value="${c}">${c}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>Course</label>
          <select id="filter-course" onchange="applyFilters()">
            <option value="">All</option>
            ${(constants.courses || []).map((c) => `<option value="${c}">${c}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>Year</label>
          <select id="filter-year" onchange="applyFilters()">
            <option value="">All</option>
            ${(constants.year_levels || []).map((y) => `<option value="${y}">${y}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>Section</label>
          <select id="filter-section" onchange="applyFilters()">
            <option value="">All</option>
            ${(constants.sections || []).map((s) => `<option value="${s}">${s}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>Status</label>
          <select id="filter-status" onchange="applyFilters()">
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
          </select></div>
      </div>
    ` : ""}

    ${isStudent ? renderStudentClearanceSlips(clearances) : renderFacultyClearanceList(clearances)}
  `;

    container.innerHTML += renderModals();
}

// ============= STUDENT SLIPS =============
function renderStudentClearanceSlips(clearances) {
    if (!clearances || clearances.length === 0) {
        return `
      <div class="empty-state" data-testid="empty-clearances">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        <h3>No clearances yet</h3>
        <p>Click "New Clearance" to request your clearance slip.</p>
      </div>`;
    }
    return `<div class="clearance-slips">${clearances.map((c) => renderClearanceSlip(c)).join("")}</div>`;
}

function renderClearanceSlip(c) {
    const ayParts = c.academic_year ? c.academic_year.split("-") : ["20__", "20__"];
    return `
    <div class="clearance-slip" onclick="viewClearance('${c.id}')" data-testid="clearance-slip-${c.id}">
      <div class="slip-header">
        <div class="slip-header-text">
          <h2>Mindoro State University</h2>
          <p class="slip-office">Office of Student Affairs Services</p>
          <h3>STUDENT'S CLEARANCE SLIP</h3>
        </div>
      </div>

      <div class="slip-semester-row">
        <div class="slip-semester">
          <span class="checkbox ${c.semester === "1st Semester" ? "checked" : ""}"></span> 1st Semester
          <span class="checkbox ${c.semester === "2nd Semester" ? "checked" : ""}"></span> 2nd Semester
          <span class="checkbox ${c.semester === "Summer" ? "checked" : ""}"></span> Summer
        </div>
        <div class="slip-ay">AY <span class="underline">${escapeHtml(ayParts[0])}</span> - <span class="underline">${escapeHtml(ayParts[1])}</span></div>
      </div>

      <div class="slip-campus-row">
        <span class="checkbox ${c.campus === "MMC" ? "checked" : ""}"></span> MMC
        <span class="checkbox ${c.campus === "MBC" ? "checked" : ""}"></span> MBC
        <span class="checkbox ${c.campus === "MCC" ? "checked" : ""}"></span> MCC
        <span style="margin-left: auto;">College:
          ${(constants.colleges || []).map((col) => `<span class="checkbox ${c.college === col ? "checked" : ""}"></span> ${col}`).join(" ")}
        </span>
      </div>

      <div class="slip-student-info">
        <div class="slip-field"><label>Name:</label><span class="underline">${escapeHtml(c.student_name)}</span></div>
        <div class="slip-field"><label>Student No.:</label><span class="underline">${escapeHtml(c.student_number)}</span></div>
        <div class="slip-field"><label>Course/Maj/Yr/Section:</label><span class="underline">${escapeHtml(c.course)} / ${escapeHtml(c.year_level)} / ${escapeHtml(c.section)}</span></div>
      </div>

      <table class="slip-table">
        <thead><tr><th>CLEARING OFFICERS</th><th>REMARKS/COMMENTS</th><th>DATE</th><th>APPROVAL CODE</th></tr></thead>
        <tbody>
          ${c.approvals.map((a) => `
            <tr class="${a.status}">
              <td class="officer-name">${escapeHtml(a.office)}</td>
              <td class="remarks">${escapeHtml(a.status === "approved" ? (a.comments || "Cleared") : (a.status === "rejected" ? (a.comments || "Not cleared") : ""))}</td>
              <td class="date">${a.approved_at ? formatDate(a.approved_at) : ""}</td>
              <td class="approval-code">${a.approval_code ? `<div class="code-box"><span class="code">${escapeHtml(a.approval_code)}</span><br><small>${escapeHtml(a.approved_by_name || "")}</small></div>` : ""}</td>
            </tr>`).join("")}
        </tbody>
      </table>

      <div class="slip-footer">
        <div class="slip-status ${c.overall_status}">${c.overall_status.toUpperCase()}</div>
        <div style="display:flex;gap:0.5rem;">
          <button class="btn btn-outline btn-sm" onclick="event.stopPropagation(); viewAuditTrail('${c.id}')" data-testid="view-audit-trail-${c.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8v4l3 3"/><circle cx="12" cy="12" r="10"/></svg>
            Audit Trail
          </button>
          <button class="btn ${c.overall_status === "approved" ? "btn-primary" : "btn-secondary"} btn-sm" onclick="event.stopPropagation(); printClearance('${c.id}')" data-testid="print-clearance-${c.id}">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            Print Clearance
          </button>
        </div>
      </div>
    </div>`;
}

// ============= FACULTY LIST =============
function renderFacultyClearanceList(clearances) {
    if (!clearances || clearances.length === 0) {
        return `
      <div class="card">
        <div class="card-header"><h2 class="card-title">Clearance Requests</h2><span class="text-muted">0 records</span></div>
        <div class="card-body">
          <div class="empty-state">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
            <h3>No clearances found</h3>
            <p>When students submit clearance requests, they will appear here.</p>
          </div>
        </div>
      </div>`;
    }
    return `
    <div class="card">
      <div class="card-header"><h2 class="card-title">Clearance Requests</h2><span class="text-muted" id="clearance-count">${clearances.length} records</span></div>
      <div class="card-body">
        <div class="clearance-table-container">
          <table class="clearance-table" data-testid="clearance-table">
            <thead><tr>
              <th>Student Name</th><th>Student No.</th><th>Campus</th>
              <th>Course</th><th>Year/Sec</th><th>Semester</th><th>Status</th><th>Action</th>
            </tr></thead>
            <tbody id="clearance-list">
              ${clearances.map((c) => clearanceRowHtml(c)).join("")}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;
}

function clearanceRowHtml(c) {
    return `<tr>
    <td class="student-name">${escapeHtml(c.student_name)}</td>
    <td>${escapeHtml(c.student_number)}</td>
    <td>${escapeHtml(c.campus || "-")}</td>
    <td>${escapeHtml(c.course)}</td>
    <td>${escapeHtml(c.year_level)} - ${escapeHtml(c.section)}</td>
    <td>${escapeHtml(c.semester)}</td>
    <td>${getStatusBadge(c.overall_status)}</td>
    <td>
      <button class="btn btn-sm btn-secondary" onclick="viewClearance('${c.id}')" data-testid="view-clearance-${c.id}">View</button>
      ${canApprove(c) ? `<button class="btn btn-sm btn-success" onclick="openSignatureModal('${c.id}')" data-testid="sign-clearance-${c.id}">Sign</button>` : ""}
    </td></tr>`;
}

function canApprove(clearance) {
    if (currentUser.role !== "faculty") return false;
    const approval = clearance.approvals.find((a) => a.office === currentUser.office);
    if (!approval || approval.status !== "pending") return false;
    if (currentUser.office === "Registrar") {
        const otherPending = clearance.approvals.filter((a) => a.office !== "Registrar" && a.status === "pending");
        return otherPending.length === 0;
    }
    return true;
}

// ============= SEARCH/FILTER =============
function searchClearances() {
    const term = (document.getElementById("search-input").value || "").toLowerCase().trim();
    const filtered = allClearances.filter((c) =>
        c.student_name.toLowerCase().includes(term) ||
        (c.student_number || "").toLowerCase().includes(term) ||
        (c.student_email || "").toLowerCase().includes(term)
    );
    updateClearanceList(filtered);
}
function filterClearances(status) {
    const el = document.getElementById("filter-status");
    if (el && status) el.value = status;
    applyFilters();
}
async function applyFilters() {
    const filters = {};
    ["campus", "college", "course", "section", "status"].forEach((key) => {
        const el = document.getElementById(`filter-${key}`);
        if (el && el.value) filters[key] = el.value;
    });
    const yearEl = document.getElementById("filter-year");
    if (yearEl && yearEl.value) filters.year_level = yearEl.value;
    try {
        const result = await API.getClearances(currentUser.id, filters);
        allClearances = result.clearances;
        updateClearanceList(allClearances);
    } catch {}
}
function updateClearanceList(clearances) {
    const tbody = document.getElementById("clearance-list");
    const count = document.getElementById("clearance-count");
    if (count) count.textContent = `${clearances.length} records`;
    if (tbody) tbody.innerHTML = clearances.map(clearanceRowHtml).join("");
}

// ============= MODALS =============
function renderModals() {
    const savedSig = getSavedSignature();
    return `
    <div id="createClearanceModal" class="modal">
      <div class="modal-content">
        <div class="modal-header"><h2>Request New Clearance</h2><button class="modal-close" onclick="closeModal('createClearanceModal')">&times;</button></div>
        <form id="createClearanceForm" novalidate data-testid="create-clearance-form">
          <div class="modal-body">
            <div class="form-group"><label>Semester</label>
              <select id="clearance-semester" data-testid="clearance-semester-select" required>
                <option value="">Select</option>
                <option value="1st Semester">1st Semester</option>
                <option value="2nd Semester">2nd Semester</option>
                <option value="Summer">Summer</option>
              </select></div>
            <div class="form-group"><label>Academic Year</label>
              <select id="clearance-year" data-testid="clearance-year-select" required>
                <option value="">Select</option>
                <option value="2024-2025">2024-2025</option>
                <option value="2025-2026">2025-2026</option>
                <option value="2026-2027">2026-2027</option>
              </select></div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" onclick="closeModal('createClearanceModal')">Cancel</button>
            <button type="submit" class="btn btn-primary" data-testid="submit-clearance-button">Submit Request</button>
          </div>
        </form>
      </div>
    </div>

    <div id="clearanceDetailsModal" class="modal">
      <div class="modal-content" style="max-width: 900px;">
        <div class="modal-header"><h2>Clearance Details</h2><button class="modal-close" onclick="closeModal('clearanceDetailsModal')">&times;</button></div>
        <div id="clearance-details-content" class="modal-body"></div>
      </div>
    </div>

    <div id="auditTrailModal" class="modal">
      <div class="modal-content" style="max-width: 800px;">
        <div class="modal-header"><h2>Audit Trail</h2><button class="modal-close" onclick="closeModal('auditTrailModal')">&times;</button></div>
        <div id="audit-trail-content" class="modal-body"></div>
      </div>
    </div>

    <div id="signatureModal" class="modal">
      <div class="modal-content">
        <div class="modal-header"><h2>Sign Clearance</h2><button class="modal-close" onclick="closeModal('signatureModal')">&times;</button></div>
        <form id="signatureForm">
          <div class="modal-body">
            <div class="form-group"><label>Remarks/Comments</label>
              <textarea id="signature-comments" placeholder="Optional remarks..." rows="2" data-testid="signature-comments"></textarea></div>
            ${savedSig ? `
              <div class="saved-signature" id="saved-sig-section">
                <div class="saved-sig-label">Saved Signature (click to use)</div>
                <img src="${savedSig}" alt="Saved" onclick="useSavedSignature()" id="saved-sig-img">
                <button type="button" class="btn btn-ghost btn-sm" onclick="deleteSavedSignature()">Remove</button>
              </div>` : ""}
            <div class="signature-container">
              <label>E-Signature</label>
              <div class="signature-tabs">
                <button type="button" class="signature-tab active" onclick="switchSignatureTab('draw')">Draw</button>
                <button type="button" class="signature-tab" onclick="switchSignatureTab('type')">Type</button>
              </div>
              <div id="draw-signature">
                <div class="signature-canvas-container"><canvas id="signatureCanvas"></canvas></div>
                <div class="signature-actions">
                  <button type="button" class="btn btn-secondary btn-sm" onclick="clearSignature()">Clear</button>
                  <button type="button" class="btn btn-outline btn-sm" onclick="saveCurrentSignature()">Save Signature</button>
                </div>
              </div>
              <div id="type-signature" class="hidden">
                <input type="text" id="typed-signature" class="typed-signature-input" placeholder="Type your name">
              </div>
            </div>
            <input type="hidden" id="current-clearance-id">
            <input type="hidden" id="using-saved-sig" value="false">
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" onclick="closeModal('signatureModal')">Cancel</button>
            <button type="button" class="btn btn-danger" onclick="rejectClearance()" data-testid="reject-clearance-button">Reject</button>
            <button type="submit" class="btn btn-success" data-testid="approve-clearance-button">Approve & Sign</button>
          </div>
        </form>
      </div>
    </div>`;
}

function openModal(id) { document.getElementById(id).classList.add("active"); }
function closeModal(id) { document.getElementById(id).classList.remove("active"); }

function openCreateClearanceModal() {
    openModal("createClearanceModal");
    document.getElementById("createClearanceForm").onsubmit = async (e) => {
        e.preventDefault();
        const form = e.target;
        clearAllFieldErrors(form);
        const semester = document.getElementById("clearance-semester").value;
        const year = document.getElementById("clearance-year").value;
        let hasErr = false;
        const semErr = Validate.required(semester, "Semester");
        const yrErr = Validate.academicYear(year);
        if (semErr) { setFieldError("clearance-semester", semErr); hasErr = true; }
        if (yrErr)  { setFieldError("clearance-year", yrErr);      hasErr = true; }
        if (hasErr) { showToast("Please select a semester and academic year", "warning"); return; }

        // Prevent duplicate active clearances for the same semester + AY
        const dup = (allClearances || []).find(
            (c) => c.semester === semester && c.academic_year === year && c.overall_status === "pending"
        );
        if (dup) {
            showToast("You already have a pending clearance for this semester", "warning");
            return;
        }

        try {
            await API.createClearance({ semester, academic_year: year }, currentUser.id);
            showToast("Clearance request submitted!");
            closeModal("createClearanceModal");
            loadDashboardContent();
        } catch {}
    };
}

async function viewClearance(id) {
    openModal("clearanceDetailsModal");
    const c = document.getElementById("clearance-details-content");
    c.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const result = await API.getClearance(id, currentUser.id);
        c.innerHTML = renderClearanceSlip(result.clearance);
    } catch {
        c.innerHTML = '<p class="text-danger text-center">Failed to load details</p>';
    }
}

async function viewAuditTrail(clearanceId) {
    openModal("auditTrailModal");
    const box = document.getElementById("audit-trail-content");
    box.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const { trail } = await API.getClearanceAuditTrail(clearanceId, currentUser.id);
        if (!trail || trail.length === 0) {
            box.innerHTML = '<p class="text-secondary text-center">No audit entries yet.</p>';
            return;
        }
        box.innerHTML = `
      <div class="audit-trail-list">
        ${trail.map((e) => `
          <div class="audit-entry">
            <div class="audit-entry-header">
              <span class="badge badge-${e.status === "success" ? "success" : "failure"}">${escapeHtml(e.action)}</span>
              <span class="audit-time">${formatDateTime(e.timestamp)}</span>
            </div>
            <div class="audit-entry-meta">
              <strong>${escapeHtml(e.actor_email || "system")}</strong>
              <span class="text-muted"> (${escapeHtml(e.actor_role || "-")})</span>
              <span class="text-muted"> • ${escapeHtml(e.ip_address || "-")}</span>
            </div>
            ${e.details && Object.keys(e.details).length ? `<pre class="audit-details">${escapeHtml(JSON.stringify(e.details, null, 2))}</pre>` : ""}
          </div>`).join("")}
      </div>`;
    } catch {
        box.innerHTML = '<p class="text-danger text-center">Failed to load audit trail</p>';
    }
}

// ============= SIGNATURE =============
let signaturePad = null;
function openSignatureModal(clearanceId) {
    closeModal("clearanceDetailsModal");
    loadDashboardContent().then(() => {
        openModal("signatureModal");
        document.getElementById("current-clearance-id").value = clearanceId;
        document.getElementById("using-saved-sig").value = "false";
        setTimeout(() => {
            const canvas = document.getElementById("signatureCanvas");
            if (canvas) signaturePad = new SignaturePad(canvas);
        }, 100);
        document.getElementById("signatureForm").onsubmit = async (e) => {
            e.preventDefault();
            await submitSignature("approve");
        };
    });
}
function switchSignatureTab(tab) {
    document.querySelectorAll(".signature-tab").forEach((t) => t.classList.remove("active"));
    event.target.classList.add("active");
    document.getElementById("draw-signature").classList.toggle("hidden", tab !== "draw");
    document.getElementById("type-signature").classList.toggle("hidden", tab !== "type");
}
function clearSignature() { if (signaturePad) signaturePad.clear(); }
function saveCurrentSignature() {
    if (signaturePad && !signaturePad.isEmpty()) saveSignature(signaturePad.toDataURL());
    else showToast("Please draw a signature first", "warning");
}
function useSavedSignature() {
    document.getElementById("using-saved-sig").value = "true";
    document.getElementById("saved-sig-img").style.border = "2px solid var(--success)";
    showToast("Using saved signature");
}
function deleteSavedSignature() {
    localStorage.removeItem(`minsu_signature_${currentUser?.id}`);
    document.getElementById("saved-sig-section")?.remove();
    showToast("Signature removed", "warning");
}
async function rejectClearance() { await submitSignature("reject"); }
async function submitSignature(action) {
    const clearanceId = document.getElementById("current-clearance-id").value;
    const comments = document.getElementById("signature-comments").value;
    const usingSaved = document.getElementById("using-saved-sig").value === "true";

    // Reject requires comments
    if (action === "reject") {
        const err = Validate.comments(comments, { requiredMsg: "Please provide a reason for rejection" });
        if (err) { setFieldError("signature-comments", err); showToast(err, "warning"); return; }
    } else {
        const err = Validate.comments(comments);
        if (err) { setFieldError("signature-comments", err); showToast(err, "warning"); return; }
    }
    setFieldError("signature-comments", null);

    let signatureData = null;
    if (action === "approve") {
        if (usingSaved) signatureData = getSavedSignature();
        else if (!document.getElementById("draw-signature").classList.contains("hidden")) {
            if (signaturePad && !signaturePad.isEmpty()) signatureData = signaturePad.toDataURL();
            else { showToast("Please draw your signature", "warning"); return; }
        } else {
            const typedName = document.getElementById("typed-signature").value;
            if (!typedName || !typedName.trim()) { showToast("Please type your signature", "warning"); return; }
            const canvas = document.createElement("canvas");
            canvas.width = 400; canvas.height = 100;
            const ctx = canvas.getContext("2d");
            ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 400, 100);
            ctx.font = 'italic 36px "Brush Script MT", cursive';
            ctx.fillStyle = "#14532D"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
            ctx.fillText(typedName, 200, 50);
            signatureData = canvas.toDataURL();
        }
        if (!signatureData || !signatureData.startsWith("data:image/")) {
            showToast("A valid signature is required to approve", "warning");
            return;
        }
    }
    try {
        await API.processClearance(clearanceId, { action, comments, signature_data: signatureData }, currentUser.id);
        showToast(`Clearance ${action}d successfully!`);
        closeModal("signatureModal");
        loadDashboardContent();
    } catch {}
}

// ============= ADMIN: USERS =============
async function loadUsersContent() {
    const container = document.getElementById("dashboard-content");
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const { users } = await API.getUsers(currentUser.id);
        container.innerHTML = `
      <div class="flex-between dashboard-header">
        <div>
          <h1>User Management</h1>
          <p class="text-secondary">${users.length} registered users</p>
        </div>
      </div>
      <div class="card">
        <div class="card-body">
          <div class="clearance-table-container">
            <table class="clearance-table" data-testid="users-table">
              <thead><tr>
                <th>Full Name</th><th>Email</th><th>Role</th>
                <th>Office / Course</th><th>Status</th><th>Registered</th><th>Actions</th>
              </tr></thead>
              <tbody>
                ${users.map((u) => `
                  <tr>
                    <td class="student-name">${escapeHtml(u.full_name)}</td>
                    <td>${escapeHtml(u.email)}</td>
                    <td><span class="badge badge-${u.role === "admin" ? "approved" : u.role === "faculty" ? "pending" : "muted"}">${escapeHtml(u.role)}</span></td>
                    <td>${escapeHtml(u.office || u.course || "-")}</td>
                    <td>${u.is_locked
                        ? '<span class="badge badge-failure" data-testid="user-locked-badge">🔒 Locked</span>'
                        : '<span class="badge badge-success">Active</span>'}</td>
                    <td>${u.created_at ? formatDate(u.created_at) : "-"}</td>
                    <td class="user-actions">
                      ${u.is_locked ? `<button class="btn btn-sm btn-outline" onclick="unlockUser('${u.id}','${escapeHtml(u.full_name)}')" data-testid="unlock-user-${u.id}">Unlock</button>` : ""}
                      ${u.id !== currentUser.id ? `<button class="btn btn-sm btn-danger" onclick="confirmDeleteUser('${u.id}','${escapeHtml(u.full_name)}')" data-testid="delete-user-${u.id}">Delete</button>` : '<span class="text-muted">you</span>'}
                    </td>
                  </tr>`).join("")}
              </tbody>
            </table>
          </div>
        </div>
      </div>`;
    } catch {
        container.innerHTML = '<p class="text-danger text-center">Failed to load users</p>';
    }
}
async function confirmDeleteUser(id, name) {
    if (!confirm(`Delete user "${name}"? This action is permanent and will be audit-logged.`)) return;
    try {
        await API.deleteUser(id, currentUser.id);
        showToast("User deleted");
        loadUsersContent();
    } catch {}
}

async function unlockUser(id, name) {
    if (!confirm(`Unlock account for "${name}"? Their failed-login lockout will be cleared.`)) return;
    try {
        await API.unlockUser(id, currentUser.id);
        showToast("Account unlocked");
        loadUsersContent();
    } catch {}
}

// ============= ADMIN: AUDIT =============
async function loadAuditContent(filters = {}) {
    const container = document.getElementById("dashboard-content");
    container.innerHTML = '<div class="loading"><div class="spinner"></div></div>';
    try {
        const [{ logs, count }, { actions, resource_types }] = await Promise.all([
            API.getAuditLogs(currentUser.id, filters),
            API.getAuditLogActions(currentUser.id),
        ]);
        container.innerHTML = `
      <div class="flex-between dashboard-header">
        <div>
          <h1>Audit Trail</h1>
          <p class="text-secondary">${count} entries • complete system activity log</p>
        </div>
      </div>
      <div class="filters" style="margin-bottom:1.5rem;">
        <div class="filter-group"><label>Action</label>
          <select id="audit-filter-action" onchange="applyAuditFilters()">
            <option value="">All</option>
            ${(actions || []).map((a) => `<option value="${a}" ${filters.action === a ? "selected" : ""}>${a}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>Resource</label>
          <select id="audit-filter-resource" onchange="applyAuditFilters()">
            <option value="">All</option>
            ${(resource_types || []).map((r) => `<option value="${r}" ${filters.resource_type === r ? "selected" : ""}>${r}</option>`).join("")}
          </select></div>
        <div class="filter-group"><label>Status</label>
          <select id="audit-filter-status" onchange="applyAuditFilters()">
            <option value="">All</option>
            <option value="success" ${filters.status === "success" ? "selected" : ""}>Success</option>
            <option value="failure" ${filters.status === "failure" ? "selected" : ""}>Failure</option>
          </select></div>
        <div class="filter-group" style="flex:1;"><label>Actor email</label>
          <input type="text" id="audit-filter-email" value="${escapeHtml(filters.actor_email || "")}" placeholder="search..." oninput="if(event.key==='Enter')applyAuditFilters()" onblur="applyAuditFilters()"></div>
      </div>

      <div class="card">
        <div class="card-body" style="padding:0;">
          <div class="clearance-table-container">
            <table class="clearance-table audit-table" data-testid="audit-table">
              <thead><tr>
                <th>Timestamp</th><th>Actor</th><th>Role</th>
                <th>Action</th><th>Resource</th><th>Status</th><th>IP</th><th>Details</th>
              </tr></thead>
              <tbody>
                ${(logs || []).length === 0
                    ? `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:2rem;">No audit log entries match these filters.</td></tr>`
                    : logs.map((e) => `
                    <tr class="${e.status === "failure" ? "rejected" : ""}">
                      <td class="audit-ts">${formatDateTime(e.timestamp)}</td>
                      <td>${escapeHtml(e.actor_email || "-")}</td>
                      <td>${escapeHtml(e.actor_role || "-")}</td>
                      <td><code>${escapeHtml(e.action)}</code></td>
                      <td>${escapeHtml(e.resource_type)}${e.resource_id ? `<br><small class="text-muted">${escapeHtml(e.resource_id).slice(0, 8)}…</small>` : ""}</td>
                      <td>${getStatusBadge(e.status)}</td>
                      <td><small>${escapeHtml(e.ip_address || "-")}</small></td>
                      <td>${e.details && Object.keys(e.details).length
                        ? `<details><summary>view</summary><pre class="audit-details">${escapeHtml(JSON.stringify(e.details, null, 2))}</pre></details>`
                        : "-"}</td>
                    </tr>`).join("")}
              </tbody>
            </table>
          </div>
        </div>
      </div>`;
    } catch {
        container.innerHTML = '<p class="text-danger text-center">Failed to load audit logs</p>';
    }
}
function applyAuditFilters() {
    const filters = {
        action: document.getElementById("audit-filter-action")?.value || "",
        resource_type: document.getElementById("audit-filter-resource")?.value || "",
        status: document.getElementById("audit-filter-status")?.value || "",
        actor_email: document.getElementById("audit-filter-email")?.value || "",
    };
    loadAuditContent(filters);
}

// ============= PRINT =============
async function printClearance(id) {
    try {
        const result = await API.getClearance(id, currentUser.id);
        const c = result.clearance;
        const printWindow = window.open("", "_blank");
        printWindow.document.write(`<!DOCTYPE html><html><head><title>Clearance - ${escapeHtml(c.student_name)}</title>
      <style>
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:'Georgia',serif;padding:20px;font-size:11px;color:#1a1a1a}
        .slip{max-width:800px;margin:0 auto}
        .top-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;font-size:10px;color:#666}
        .header{text-align:center;border-bottom:3px solid #14532D;padding-bottom:15px;margin-bottom:15px}
        .header img{width:80px;height:80px}
        .header h2{color:#14532D;margin:10px 0 5px;font-size:20px}
        .header h3{font-size:12px;font-weight:normal}
        .header h4{font-size:14px;margin-top:5px;letter-spacing:2px}
        .info-section{margin:15px 0}
        .info-row{display:flex;gap:30px;margin:8px 0;align-items:center}
        .checkbox{display:inline-block;width:14px;height:14px;border:1.5px solid #333;margin-right:4px;vertical-align:middle;text-align:center;font-size:10px;line-height:12px}
        .checkbox.checked{background:#14532D;color:white}
        .checkbox.checked::after{content:'✓'}
        .student-info{margin:15px 0}
        .field{margin:6px 0}
        .field label{font-weight:bold}
        .field .value{border-bottom:1px solid #333;padding:0 10px;min-width:200px;display:inline-block}
        table{width:100%;border-collapse:collapse;margin:15px 0}
        th,td{border:1px solid #333;padding:8px 10px;text-align:left}
        th{background:#14532D;color:white;font-size:10px;text-transform:uppercase;letter-spacing:0.5px}
        td{font-size:11px}
        .code{font-family:'Courier New',monospace;font-weight:bold;font-size:10px}
        .approver{font-size:9px;color:#666}
        .validation-section{margin-top:30px;padding-top:20px;border-top:2px solid #14532D}
        .validation-title{font-weight:bold;font-size:12px;margin-bottom:15px;text-align:center}
        .signature-box{display:flex;justify-content:space-between;margin-top:20px}
        .signature-item{text-align:center;width:45%}
        .signature-line{border-top:1px solid #333;margin-top:50px;padding-top:5px}
        .signature-label{font-size:10px;font-weight:bold}
        .signature-sublabel{font-size:9px;color:#666}
        .footer{text-align:center;margin-top:20px;font-size:9px;color:#666}
        @media print{body{padding:10px}.slip{border:none}}
      </style></head><body>
      <div class="slip">
        <div class="top-header">
          <span>${new Date().toLocaleDateString("en-PH", { month: "numeric", day: "numeric", year: "2-digit", hour: "numeric", minute: "2-digit", hour12: true })}</span>
          <span><strong>Clearance - ${escapeHtml(c.student_name)}</strong></span>
        </div>
        <div class="header">
          <img src="/images/minsu-logo.jpg" alt="MinSU">
          <h2>Mindoro State University</h2>
          <h3>Office of Student Affairs Services</h3>
          <h4>STUDENT'S CLEARANCE SLIP</h4>
        </div>
        <div class="info-section">
          <div class="info-row">
            <span><span class="checkbox ${c.semester === "1st Semester" ? "checked" : ""}"></span> 1st Sem</span>
            <span><span class="checkbox ${c.semester === "2nd Semester" ? "checked" : ""}"></span> 2nd Sem</span>
            <span><span class="checkbox ${c.semester === "Summer" ? "checked" : ""}"></span> Summer</span>
            <span style="margin-left:auto;"><strong>AY ${escapeHtml(c.academic_year)}</strong></span>
          </div>
          <div class="info-row">
            <span><span class="checkbox ${c.campus === "MMC" ? "checked" : ""}"></span> MMC</span>
            <span><span class="checkbox ${c.campus === "MBC" ? "checked" : ""}"></span> MBC</span>
            <span><span class="checkbox ${c.campus === "MCC" ? "checked" : ""}"></span> MCC</span>
            <span style="margin-left:auto;"><strong>College:</strong> ${escapeHtml(c.college || "-")}</span>
          </div>
        </div>
        <div class="student-info">
          <div class="field"><label>Name:</label> <span class="value">${escapeHtml(c.student_name)}</span></div>
          <div class="field"><label>Student No.:</label> <span class="value">${escapeHtml(c.student_number)}</span></div>
          <div class="field"><label>Course/Yr/Sec:</label> <span class="value">${escapeHtml(c.course)} / ${escapeHtml(c.year_level)} / ${escapeHtml(c.section)}</span></div>
        </div>
        <table>
          <thead><tr>
            <th style="width:30%;">CLEARING OFFICERS</th>
            <th style="width:20%;">REMARKS</th>
            <th style="width:18%;">DATE</th>
            <th style="width:32%;">APPROVAL CODE</th>
          </tr></thead>
          <tbody>
            ${c.approvals.map((a) => `<tr>
              <td>${escapeHtml(a.office)}</td>
              <td>${escapeHtml(a.comments || (a.status === "approved" ? "Cleared" : ""))}</td>
              <td>${a.approved_at ? formatDate(a.approved_at) : ""}</td>
              <td>${a.approval_code ? `<span class="code">${escapeHtml(a.approval_code)}</span><br><span class="approver">${escapeHtml(a.approved_by_name || "")}</span>` : ""}</td>
            </tr>`).join("")}
          </tbody>
        </table>
        <div class="validation-section">
          <div class="validation-title">FOR VALIDATION - REGISTRAR'S OFFICE USE ONLY</div>
          <div class="signature-box">
            <div class="signature-item"><div class="signature-line"><div class="signature-label">Validated By:</div><div class="signature-sublabel">Signature Over Printed Name</div></div></div>
            <div class="signature-item"><div class="signature-line"><div class="signature-label">Date Validated:</div><div class="signature-sublabel">MM/DD/YYYY</div></div></div>
          </div>
        </div>
        <div class="footer">
          <p>This clearance is valid for ${escapeHtml(c.semester)}, AY ${escapeHtml(c.academic_year)} only.</p>
          <p>Clearance ID: ${escapeHtml(c.id)}</p>
          <p style="margin-top:5px;"><em>Note: This document requires physical validation signature to be official.</em></p>
        </div>
      </div>
      <script>window.onload=function(){setTimeout(()=>window.print(),500)}</script>
      </body></html>`);
        printWindow.document.close();
    } catch {
        showToast("Failed to print", "error");
    }
}

// ============= MAIN =============
async function renderApp() {
    try {
        constants = await API.getConstants();
    } catch {
        constants = {
            offices: ["University Librarian", "Guidance Counselor", "SAS Director/Coordinator", "Student Affairs/Finance", "College Dean/Program Chair", "Registrar"],
            courses: ["BSIT", "BSCS", "BSED", "BEED", "BSBA", "BSCrim", "BSHM", "BSTM"],
            year_levels: ["1st Year", "2nd Year", "3rd Year", "4th Year"],
            sections: ["F1", "F2", "F3"],
            campuses: ["MMC", "MBC", "MCC"],
            colleges: ["CAAF", "CAS", "CBM", "CCS", "CCJE", "CTE", "IABE", "IF"],
        };
    }
    const user = loadUser();
    if (user) renderDashboard();
    else renderLoginPage();
}

// Expose functions used inline in HTML
window.logout = logout;
window.switchView = switchView;
window.openCreateClearanceModal = openCreateClearanceModal;
window.viewClearance = viewClearance;
window.viewAuditTrail = viewAuditTrail;
window.openSignatureModal = openSignatureModal;
window.closeModal = closeModal;
window.clearSignature = clearSignature;
window.saveCurrentSignature = saveCurrentSignature;
window.useSavedSignature = useSavedSignature;
window.deleteSavedSignature = deleteSavedSignature;
window.rejectClearance = rejectClearance;
window.submitSignature = submitSignature;
window.switchSignatureTab = switchSignatureTab;
window.searchClearances = searchClearances;
window.filterClearances = filterClearances;
window.applyFilters = applyFilters;
window.applyAuditFilters = applyAuditFilters;
window.confirmDeleteUser = confirmDeleteUser;
window.unlockUser = unlockUser;
window.printClearance = printClearance;
window.loadDashboardContent = loadDashboardContent;
window.renderApp = renderApp;

// Initial render
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderApp);
} else {
    renderApp();
}
window.addEventListener("click", (e) => {
    if (e.target.classList && e.target.classList.contains("modal")) e.target.classList.remove("active");
});
