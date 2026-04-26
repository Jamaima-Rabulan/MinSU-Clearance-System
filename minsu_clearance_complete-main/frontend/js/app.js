// MinSU Clearance System - Main App (Vanilla JS SPA)
const API_BASE = 'https://minsu-clearance-system.onrender.com';
const TOKEN_KEY = 'minsu_token';
const USER_KEY = 'minsu_user';

const state = {
  user: null,
  token: null,
  constants: { offices: [], courses: [], year_levels: [], sections: [], campuses: [], colleges: [], clearance_types: [] },
  view: 'auth',
  authMode: 'login',
  pendingVerifyEmail: null,
  pendingResetEmail: null,
  currentPage: 'dashboard',
  selectedClearance: null
};

// =========== API HELPER ===========
const api = {
  async call(endpoint, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (state.token) headers['Authorization'] = `Bearer ${state.token}`;
    if (options.body instanceof FormData) delete headers['Content-Type'];

    const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
  let data;
try {
  data = await res.json();
} catch (e) {
  throw new Error("Invalid server response");
}

    if (!res.ok) {
      const msg = data && data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  }
};

// =========== PASSWORD INPUT WITH EYE TOGGLE ===========
function passwordField(attrs = {}) {
  const wrap = DOM.el('div', { class: 'password-wrap' });
  const input = DOM.el('input', { type: 'password', ...attrs });
  const toggle = DOM.el('button', { type: 'button', class: 'pw-toggle', tabindex: '-1', 'aria-label': 'Toggle password visibility', 'data-testid': `pw-toggle-${attrs.name || attrs['data-testid'] || 'x'}`, onClick: () => {
    const isText = input.type === 'text';
    input.type = isText ? 'password' : 'text';
    icon.className = isText ? 'fa-solid fa-eye' : 'fa-solid fa-eye-slash';
  }});
  const icon = DOM.el('i', { class: 'fa-solid fa-eye' });
  toggle.appendChild(icon);
  wrap.appendChild(input);
  wrap.appendChild(toggle);
  return { wrap, input };
}

// =========== TOAST ===========
function toast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const icons = { success: 'check-circle', error: 'circle-exclamation', warning: 'triangle-exclamation', info: 'circle-info' };
  const node = DOM.el('div', { class: `toast ${type}` }, [
    DOM.el('i', { class: `fa-solid fa-${icons[type] || 'circle-info'}` }),
    DOM.el('span', { text: message })
  ]);
  container.appendChild(node);
  setTimeout(() => { node.style.opacity = '0'; node.style.transform = 'translateX(100%)'; node.style.transition = 'all 300ms'; setTimeout(() => node.remove(), 300); }, 4000);
}

// =========== INIT ===========
async function init() {
  state.token = localStorage.getItem(TOKEN_KEY);
  const userJson = localStorage.getItem(USER_KEY);

  if (state.token && userJson) {
    try {
      state.user = JSON.parse(userJson);
      const data = await api.call('/auth/me');
      state.user = data.user;
      localStorage.setItem(USER_KEY, JSON.stringify(state.user));
      state.view = 'app';
    } catch (e) {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(USER_KEY);
      state.user = null;
      state.token = null;
      state.view = 'auth';
    }
  }

  // 🔥 LOAD CONSTANTS FIRST
  try {
    const c = await api.call('/constants');
    state.constants = c;
  } catch (e) {}

  // 🔥 FORCE RE-RENDER AFTER DATA
  render();
}
// =========== RENDER ROUTER ===========
function render() {
  const app = document.getElementById('app');
  app.innerHTML = '';
  if (state.view === 'auth') app.appendChild(renderAuth());
  else if (state.view === 'verify') app.appendChild(renderVerify());
  else if (state.view === 'forgot') app.appendChild(renderForgot());
  else if (state.view === 'reset') app.appendChild(renderReset());
  else app.appendChild(renderApp());
}

// =========== AUTH PAGE ===========
function renderAuth() {
  const wrap = DOM.el('div', { class: 'auth-page' });
  wrap.appendChild(DOM.el('div', { class: 'auth-bg' }));
  const container = DOM.el('div', { class: 'auth-container' });

  container.appendChild(DOM.el('div', { class: 'auth-logo' }, [
    DOM.el('img', { src: 'images/minsu-logo.jpg', alt: 'MinSU' }),
    DOM.el('div', { class: 'brand' }, [
      DOM.el('h1', { text: 'MinSU Clearance' }),
      DOM.el('p', { text: 'Mindoro State University' })
    ])
  ]));

  // Tabs
  const tabs = DOM.el('div', { class: 'auth-tabs' }, [
    DOM.el('button', { class: `auth-tab ${state.authMode === 'login' ? 'active' : ''}`, 'data-testid': 'auth-tab-login', onClick: () => { state.authMode = 'login'; render(); } }, 'Sign In'),
    DOM.el('button', { class: `auth-tab ${state.authMode === 'register' ? 'active' : ''}`, 'data-testid': 'auth-tab-register', onClick: () => { state.authMode = 'register'; render(); } }, 'Register')
  ]);
  container.appendChild(tabs);

  if (state.authMode === 'login') container.appendChild(renderLoginForm());
  else container.appendChild(renderRegisterForm());

  wrap.appendChild(container);
  return wrap;
}

function renderLoginForm() {
  const form = DOM.el('form', { 'data-testid': 'login-form', onSubmit: async (e) => {
    e.preventDefault();
    const email = e.target.email.value.trim();
    const password = e.target.password.value;
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true; btn.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> Signing in...';
    try {
    const data = await api.call('/auth/login', { 
  method: 'POST', 
  body: JSON.stringify({ email, password }) 
});

console.log("LOGIN RESPONSE:", data);

if (!data || !data.access_token) {
  throw new Error("Login failed: no token received");
}

state.token = data.access_token;
state.user = data.user;

localStorage.setItem(TOKEN_KEY, state.token);
localStorage.setItem(USER_KEY, JSON.stringify(state.user));

state.view = 'app';
state.currentPage = 'dashboard';

toast(`Welcome, ${state.user.full_name}!`, 'success');
render();
    } catch (err) {
      if (String(err.message).toLowerCase().includes('verify')) {
        state.pendingVerifyEmail = email;
        toast(err.message, 'warning');
        state.view = 'verify'; render();
      } else {
        toast(err.message, 'error');
      }
      btn.disabled = false; btn.innerHTML = 'Sign In';
    }
  }});

  form.appendChild(DOM.el('div', { class: 'form-group' }, [
    DOM.el('label', { text: 'Email Address' }),
    DOM.el('input', { type: 'email', name: 'email', required: true, autocomplete: 'email', 'data-testid': 'login-email-input', placeholder: 'you@minsu.edu.ph' })
  ]));
  form.appendChild(DOM.el('div', { class: 'form-group' }, [
    DOM.el('label', { text: 'Password' }),
    passwordField({ name: 'password', required: true, autocomplete: 'current-password', 'data-testid': 'login-password-input', placeholder: 'Enter your password' }).wrap
  ]));
  form.appendChild(DOM.el('div', { class: 'flex-between mb-16', style: { fontSize: '13px' } }, [
    DOM.el('span'),
    DOM.el('button', { type: 'button', class: 'link-button', 'data-testid': 'forgot-password-link', onClick: () => { state.view = 'forgot'; render(); } }, 'Forgot password?')
  ]));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary btn-block btn-lg', 'data-testid': 'login-submit-btn' }, 'Sign In'));
  return form;
}

function renderRegisterForm() {
  const form = DOM.el('form', { 'data-testid': 'register-form', onSubmit: async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = Object.fromEntries(fd.entries());
    payload.role = 'student';
    if (payload.password !== payload.confirm_password) { toast('Passwords do not match', 'error'); return; }
    delete payload.confirm_password;
    if (payload.password.length < 6) { toast('Password must be at least 6 characters', 'error'); return; }
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true; btn.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> Creating account...';
    try {
      const data = await api.call('/auth/register', { method: 'POST', body: JSON.stringify(payload) });
      state.pendingVerifyEmail = data.email;
      toast(data.message + (data.dev_code ? ` (Dev code: ${data.dev_code})` : ''), 'success');
      state.view = 'verify'; render();
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false; btn.innerHTML = 'Create Account';
    }
  }});

  const c = state.constants;
  const mk = (label, name, type = 'text', required = true) =>
    DOM.el('div', { class: 'form-group' }, [
      DOM.el('label', { text: label }),
      type === 'password' ? passwordField({ name, required, 'data-testid': `register-${name}-input` }).wrap : DOM.el('input', { type, name, required, 'data-testid': `register-${name}-input` })
    ]);
  const mkSel = (label, name, opts) =>
    DOM.el('div', { class: 'form-group' }, [
      DOM.el('label', { text: label }),
      DOM.el('select', { name, required: true, 'data-testid': `register-${name}-select` },
        [DOM.el('option', { value: '' }, `Select ${label}`), ...opts.map(o => DOM.el('option', { value: o }, o))])
    ]);

  form.appendChild(mk('Full Name', 'full_name'));
  form.appendChild(mk('Email Address', 'email', 'email'));
  form.appendChild(DOM.el('div', { class: 'form-row' }, [mk('Password', 'password', 'password'), mk('Confirm Password', 'confirm_password', 'password')]));
  form.appendChild(mk('Student ID', 'student_id'));
  form.appendChild(DOM.el('div', { class: 'form-row' }, [mkSel('Campus', 'campus', c.campuses), mkSel('College', 'college', c.colleges)]));
  form.appendChild(mkSel('Course', 'course', c.courses));
  form.appendChild(DOM.el('div', { class: 'form-row' }, [mkSel('Year Level', 'year_level', c.year_levels), mkSel('Section', 'section', c.sections)]));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary btn-block btn-lg mt-8', 'data-testid': 'register-submit-btn' }, 'Create Account'));
  return form;
}

// =========== VERIFY EMAIL PAGE ===========
function renderVerify() {
  const wrap = DOM.el('div', { class: 'auth-page' });
  wrap.appendChild(DOM.el('div', { class: 'auth-bg' }));
  const container = DOM.el('div', { class: 'auth-container' });

  container.appendChild(DOM.el('div', { class: 'auth-logo' }, [
    DOM.el('img', { src: 'images/minsu-logo.jpg', alt: 'MinSU' }),
    DOM.el('div', { class: 'brand' }, [
      DOM.el('h1', { text: 'Verify Your Email' }),
      DOM.el('p', { text: 'Enter the 6-digit code sent to your inbox' })
    ])
  ]));
  container.appendChild(DOM.el('div', { class: 'alert info', 'data-testid': 'verify-email-info' }, [
    DOM.el('i', { class: 'fa-solid fa-envelope-open-text' }),
    DOM.el('div', {}, [
      DOM.el('strong', { text: 'Code sent to: ' }),
      DOM.el('span', { text: state.pendingVerifyEmail || '' })
    ])
  ]));

  const form = DOM.el('form', { 'data-testid': 'verify-form', onSubmit: async (e) => {
    e.preventDefault();
    const code = Array.from(e.target.querySelectorAll('.otp-row input')).map(i => i.value).join('');
    if (code.length !== 6) { toast('Please enter all 6 digits', 'error'); return; }
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true; btn.innerHTML = '<span class="spinner" style="width:16px;height:16px;border-width:2px"></span> Verifying...';
    try {
      await api.call('/auth/verify-email', { method: 'POST', body: JSON.stringify({ email: state.pendingVerifyEmail, code }) });
      toast('Email verified! You can now sign in.', 'success');
      state.authMode = 'login'; state.view = 'auth'; state.pendingVerifyEmail = null; render();
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false; btn.innerHTML = 'Verify Email';
    }
  }});

  const otpRow = DOM.el('div', { class: 'otp-row' });
  for (let i = 0; i < 6; i++) {
    const inp = DOM.el('input', { type: 'text', maxlength: '1', inputmode: 'numeric', pattern: '[0-9]*', 'data-testid': `verify-code-input-${i}`, autocomplete: 'one-time-code' });
    inp.addEventListener('input', (ev) => {
      ev.target.value = ev.target.value.replace(/\D/g, '');
      if (ev.target.value && i < 5) otpRow.children[i + 1].focus();
    });
    inp.addEventListener('keydown', (ev) => {
      if (ev.key === 'Backspace' && !ev.target.value && i > 0) otpRow.children[i - 1].focus();
    });
    inp.addEventListener('paste', (ev) => {
      ev.preventDefault();
      const text = (ev.clipboardData || window.clipboardData).getData('text').replace(/\D/g, '').slice(0, 6);
      for (let j = 0; j < text.length && j < 6; j++) otpRow.children[j].value = text[j];
      if (text.length === 6) otpRow.children[5].focus();
    });
    otpRow.appendChild(inp);
  }
  form.appendChild(otpRow);
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary btn-block btn-lg', 'data-testid': 'verify-submit-btn' }, 'Verify Email'));

  const actions = DOM.el('div', { class: 'flex-between mt-16', style: { fontSize: '13px' } }, [
    DOM.el('button', { type: 'button', class: 'link-button', 'data-testid': 'verify-back-btn', onClick: () => { state.view = 'auth'; render(); } }, '← Back to login'),
    DOM.el('button', { type: 'button', class: 'link-button', 'data-testid': 'verify-resend-btn', onClick: async () => {
      try {
        const r = await api.call('/auth/resend-verification', { method: 'POST', body: JSON.stringify({ email: state.pendingVerifyEmail }) });
        toast(r.message + (r.dev_code ? ` (Dev: ${r.dev_code})` : ''), 'success');
      } catch (err) { toast(err.message, 'error'); }
    } }, 'Resend code')
  ]);
  form.appendChild(actions);
  container.appendChild(form);
  wrap.appendChild(container);
  setTimeout(() => otpRow.children[0].focus(), 100);
  return wrap;
}

// =========== FORGOT/RESET PASSWORD ===========
function renderForgot() {
  const wrap = DOM.el('div', { class: 'auth-page' });
  wrap.appendChild(DOM.el('div', { class: 'auth-bg' }));
  const c = DOM.el('div', { class: 'auth-container' });
  c.appendChild(DOM.el('div', { class: 'auth-logo' }, [
    DOM.el('img', { src: 'images/minsu-logo.jpg' }),
    DOM.el('div', { class: 'brand' }, [DOM.el('h1', { text: 'Forgot Password' }), DOM.el('p', { text: 'We will send a reset code to your email' })])
  ]));
  const form = DOM.el('form', { 'data-testid': 'forgot-form', onSubmit: async (e) => {
    e.preventDefault();
    const email = e.target.email.value.trim();
    try {
      const data = await api.call('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) });
      state.pendingResetEmail = email;
      toast(data.message + (data.dev_code ? ` (Dev: ${data.dev_code})` : ''), 'success');
      state.view = 'reset'; render();
    } catch (err) { toast(err.message, 'error'); }
  }});
  form.appendChild(DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Email' }), DOM.el('input', { type: 'email', name: 'email', required: true, 'data-testid': 'forgot-email-input' })]));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary btn-block btn-lg', 'data-testid': 'forgot-submit-btn' }, 'Send Reset Code'));
  form.appendChild(DOM.el('button', { type: 'button', class: 'link-button mt-16', onClick: () => { state.view = 'auth'; render(); } }, '← Back to login'));
  c.appendChild(form);
  wrap.appendChild(c);
  return wrap;
}

function renderReset() {
  const wrap = DOM.el('div', { class: 'auth-page' });
  wrap.appendChild(DOM.el('div', { class: 'auth-bg' }));
  const c = DOM.el('div', { class: 'auth-container' });
  c.appendChild(DOM.el('div', { class: 'auth-logo' }, [
    DOM.el('img', { src: 'images/minsu-logo.jpg' }),
    DOM.el('div', { class: 'brand' }, [DOM.el('h1', { text: 'Reset Password' }), DOM.el('p', { text: 'Enter the code from your email' })])
  ]));
  const form = DOM.el('form', { onSubmit: async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const data = Object.fromEntries(fd.entries());
    if (data.new_password !== data.confirm) { toast('Passwords do not match', 'error'); return; }
    if (data.new_password.length < 6) { toast('Password must be 6+ characters', 'error'); return; }
    try {
      await api.call('/auth/reset-password', { method: 'POST', body: JSON.stringify({ email: state.pendingResetEmail, code: data.code, new_password: data.new_password }) });
      toast('Password reset! Please sign in.', 'success');
      state.view = 'auth'; state.authMode = 'login'; render();
    } catch (err) { toast(err.message, 'error'); }
  }});
  form.appendChild(DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: '6-Digit Code' }), DOM.el('input', { name: 'code', required: true, maxlength: '6', 'data-testid': 'reset-code-input' })]));
  form.appendChild(DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'New Password' }), passwordField({ name: 'new_password', required: true, 'data-testid': 'reset-password-input' }).wrap]));
  form.appendChild(DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Confirm New Password' }), passwordField({ name: 'confirm', required: true }).wrap]));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary btn-block btn-lg', 'data-testid': 'reset-submit-btn' }, 'Reset Password'));
  form.appendChild(DOM.el('button', { type: 'button', class: 'link-button mt-16', onClick: () => { state.view = 'auth'; render(); } }, '← Back to login'));
  c.appendChild(form);
  wrap.appendChild(c);
  return wrap;
}

// =========== APP LAYOUT ===========
function renderApp() {
  const layout = DOM.el('div', { class: 'app-layout' });

  // Sidebar
  const sb = DOM.el('aside', { class: 'sidebar', id: 'sidebar' });
  sb.appendChild(DOM.el('div', { class: 'sidebar-brand' }, [
    DOM.el('img', { src: 'images/minsu-logo.jpg' }),
    DOM.el('div', { class: 'brand-text' }, [
      'MinSU Clearance',
      DOM.el('small', { text: 'Mindoro State University' })
    ])
  ]));

  const u = state.user;
  const initials = u.full_name.split(' ').map(s => s[0]).slice(0, 2).join('').toUpperCase();
  sb.appendChild(DOM.el('div', { class: 'sidebar-user' }, [
    DOM.el('div', { class: 'avatar', text: initials }),
    DOM.el('div', { class: 'sidebar-user-info' }, [
      DOM.el('div', { class: 'name', text: u.full_name }),
      DOM.el('div', { class: 'role', text: u.role + (u.office ? ` · ${u.office}` : '') })
    ])
  ]));

  const nav = DOM.el('nav', { class: 'sidebar-nav' });
  const pages = [{ id: 'dashboard', label: 'Dashboard', icon: 'house' }, { id: 'clearances', label: 'Clearances', icon: 'file-circle-check' }];
  if (u.role === 'student') pages.push({ id: 'create', label: 'Request Clearance', icon: 'plus-circle' });
  if (u.role === 'admin' || u.role === 'superadmin') {
    pages.push({ id: 'users', label: 'Users', icon: 'users' });
    pages.push({ id: 'create-user', label: 'Add Faculty/Admin', icon: 'user-plus' });
    pages.push({ id: 'audit', label: 'Audit Log', icon: 'clipboard-list' });
    pages.push({ id: 'settings', label: 'Email Settings', icon: 'envelope' });
  }
  pages.push({ id: 'profile', label: 'My Account', icon: 'user-gear' });
  for (const p of pages) {
    nav.appendChild(DOM.el('button', { class: `nav-item ${state.currentPage === p.id ? 'active' : ''}`, 'data-testid': `nav-${p.id}`, onClick: () => { state.currentPage = p.id; state.selectedClearance = null; render(); } }, [
      DOM.el('i', { class: `fa-solid fa-${p.icon}` }),
      p.label
    ]));
  }
  sb.appendChild(nav);

  sb.appendChild(DOM.el('div', { class: 'sidebar-footer' }, [
    DOM.el('button', { class: 'btn btn-outline btn-block', 'data-testid': 'logout-btn', style: { color: 'white', borderColor: 'rgba(255,255,255,0.3)', background: 'transparent' }, onClick: handleLogout }, [
      DOM.el('i', { class: 'fa-solid fa-right-from-bracket' }), 'Sign out'
    ])
  ]));

  layout.appendChild(sb);

  const main = DOM.el('main', { class: 'main-area' });
  main.appendChild(DOM.el('button', { class: 'menu-toggle', onClick: () => document.getElementById('sidebar').classList.toggle('open') }, [DOM.el('i', { class: 'fa-solid fa-bars' })]));

  if (state.selectedClearance) main.appendChild(renderClearanceDetail());
  else if (state.currentPage === 'dashboard') main.appendChild(renderDashboard());
  else if (state.currentPage === 'clearances') main.appendChild(renderClearancesList());
  else if (state.currentPage === 'create') main.appendChild(renderCreateClearance());
  else if (state.currentPage === 'users') main.appendChild(renderUsersPage());
  else if (state.currentPage === 'create-user') main.appendChild(renderCreateUser());
  else if (state.currentPage === 'audit') main.appendChild(renderAuditLog());
  else if (state.currentPage === 'settings') main.appendChild(renderSettings());
  else if (state.currentPage === 'profile') main.appendChild(renderProfile());

  layout.appendChild(main);
  return layout;
}

async function handleLogout() {
  try { await api.call('/auth/logout', { method: 'POST' }); } catch (e) {}
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  state.user = null; state.token = null; state.view = 'auth'; state.authMode = 'login';
  render();
  toast('Signed out', 'info');
}

// =========== DASHBOARD ===========
function renderDashboard() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [
      DOM.el('h1', { text: `Welcome, ${state.user.full_name.split(' ')[0]}!` }),
      DOM.el('p', { class: 'subtitle', text: dashSubtitle() })
    ])
  ]));

  const grid = DOM.el('div', { class: 'stats-grid', 'data-testid': 'stats-grid' });
  ['total', 'pending', 'approved', 'rejected'].forEach(k => {
    const card = DOM.el('div', { class: 'stat-card', 'data-testid': `stat-${k}` }, [
      DOM.el('div', { class: `stat-icon ${k}` }, [DOM.el('i', { class: `fa-solid fa-${{total:'file-lines',pending:'hourglass-half',approved:'check',rejected:'xmark'}[k]}` })]),
      DOM.el('div', { class: 'stat-info' }, [
        DOM.el('div', { class: 'label', text: k.charAt(0).toUpperCase() + k.slice(1) }),
        DOM.el('div', { class: 'value', text: '...', id: `stat-${k}` })
      ])
    ]);
    grid.appendChild(card);
  });
  wrap.appendChild(grid);

  api.call('/stats').then(s => {
    document.getElementById('stat-total').textContent = s.total;
    document.getElementById('stat-pending').textContent = s.pending;
    document.getElementById('stat-approved').textContent = s.approved;
    document.getElementById('stat-rejected').textContent = s.rejected;
  }).catch(() => {});

  // Quick actions
  const actions = DOM.el('div', { class: 'card' });
  actions.appendChild(DOM.el('h2', { text: 'Quick Actions', class: 'mb-16' }));
  const btnRow = DOM.el('div', { class: 'flex gap-12', style: { flexWrap: 'wrap' } });
  if (state.user.role === 'student') {
    btnRow.appendChild(DOM.el('button', { class: 'btn btn-primary', 'data-testid': 'quick-create-clearance', onClick: () => { state.currentPage = 'create'; render(); } }, [DOM.el('i', { class: 'fa-solid fa-plus' }), 'Request Clearance']));
  }
  btnRow.appendChild(DOM.el('button', { class: 'btn btn-secondary', onClick: () => { state.currentPage = 'clearances'; render(); } }, [DOM.el('i', { class: 'fa-solid fa-list' }), 'View Clearances']));
  if (state.user.role === 'admin') {
    btnRow.appendChild(DOM.el('button', { class: 'btn btn-secondary', onClick: () => { state.currentPage = 'audit'; render(); } }, [DOM.el('i', { class: 'fa-solid fa-clipboard-list' }), 'Audit Log']));
  }
  actions.appendChild(btnRow);
  wrap.appendChild(actions);

  return wrap;
}

function dashSubtitle() {
  const r = state.user.role;
  if (r === 'student') return `${state.user.course || ''} · ${state.user.year_level || ''} · ${state.user.section || ''}`;
  if (r === 'faculty') return `${state.user.office || ''} · Faculty Member`;
  if (r === 'superadmin') return 'Super Administrator · Full system access';
  return 'System Administrator';
}

// =========== CLEARANCES LIST ===========
function renderClearancesList() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [
      DOM.el('h1', { text: 'Clearances' }),
      DOM.el('p', { class: 'subtitle', text: state.user.role === 'student' ? 'Your clearance requests' : state.user.role === 'faculty' ? 'Pending approvals for your office' : 'All clearances in the system' })
    ])
  ]));

  const card = DOM.el('div', { class: 'card' });
  const filterRow = DOM.el('div', { class: 'filters' });
  const statusSel = DOM.el('select', { 'data-testid': 'filter-status' }, [DOM.el('option', { value: '' }, 'All statuses'), ...['pending','approved','rejected'].map(s => DOM.el('option', { value: s }, s.charAt(0).toUpperCase() + s.slice(1)))]);
  filterRow.appendChild(statusSel);

  // Faculty/Admin: program/year/section filters for targeted bulk approval
  let courseSel = null, yearSel = null, sectionSel = null;
  if (state.user.role !== 'student') {
    courseSel = DOM.el('select', { 'data-testid': 'filter-course' }, [
      DOM.el('option', { value: '' }, 'All programs'),
      ...state.constants.courses.map(c => DOM.el('option', { value: c }, c))
    ]);
    yearSel = DOM.el('select', { 'data-testid': 'filter-year' }, [
      DOM.el('option', { value: '' }, 'All year levels'),
      ...state.constants.year_levels.map(y => DOM.el('option', { value: y }, y))
    ]);
    sectionSel = DOM.el('select', { 'data-testid': 'filter-section' }, [
      DOM.el('option', { value: '' }, 'All sections'),
      ...state.constants.sections.map(s => DOM.el('option', { value: s }, s))
    ]);
    filterRow.appendChild(courseSel);
    filterRow.appendChild(yearSel);
    filterRow.appendChild(sectionSel);
    const clearBtn = DOM.el('button', { class: 'btn btn-sm btn-outline', 'data-testid': 'clear-filters', onClick: () => {
      statusSel.value = ''; courseSel.value = ''; yearSel.value = ''; sectionSel.value = '';
      load();
    }}, [DOM.el('i', { class: 'fa-solid fa-rotate-left' }), 'Clear']);
    filterRow.appendChild(clearBtn);
  }
  card.appendChild(filterRow);

  // Bulk action bar (faculty only)
  const bulkBar = DOM.el('div', { class: 'flex-between mb-16', id: 'bulk-bar', style: { display: 'none', padding: '12px 16px', background: 'var(--green-50)', borderRadius: 'var(--radius-sm)' } });
  if (state.user.role === 'faculty') {
    card.appendChild(bulkBar);
  }

  const tableWrap = DOM.el('div', { class: 'table-wrap', id: 'clearances-table' });
  card.appendChild(tableWrap);
  wrap.appendChild(card);

  const selected = new Set();

  function refreshBulkBar() {
    if (state.user.role !== 'faculty') return;
    const n = selected.size;
    if (n === 0) { bulkBar.style.display = 'none'; return; }
    bulkBar.style.display = 'flex';
    bulkBar.innerHTML = '';
    const filterTags = [];
    if (courseSel && courseSel.value) filterTags.push(courseSel.value);
    if (yearSel && yearSel.value) filterTags.push(yearSel.value);
    if (sectionSel && sectionSel.value) filterTags.push(`Section ${sectionSel.value}`);
    const left = DOM.el('div', {}, [
      DOM.el('strong', { text: `${n} clearance${n > 1 ? 's' : ''} selected` }),
      filterTags.length ? DOM.el('span', { class: 'text-muted', style: { marginLeft: '12px', fontSize: '13px' }, text: `(${filterTags.join(' · ')})` }) : null
    ]);
    bulkBar.appendChild(left);
    const right = DOM.el('div', { class: 'flex gap-8' });
    right.appendChild(DOM.el('button', { class: 'btn btn-sm btn-outline', onClick: () => { selected.clear(); load(); } }, 'Clear'));
    right.appendChild(DOM.el('button', { class: 'btn btn-sm btn-primary', 'data-testid': 'bulk-approve-btn', onClick: () => bulkProcess('approve') }, [DOM.el('i', { class: 'fa-solid fa-check' }), 'Approve all']));
    right.appendChild(DOM.el('button', { class: 'btn btn-sm btn-danger', 'data-testid': 'bulk-reject-btn', onClick: () => bulkProcess('reject') }, [DOM.el('i', { class: 'fa-solid fa-xmark' }), 'Reject all']));
    bulkBar.appendChild(right);
  }

  async function bulkProcess(action) {
    const comments = action === 'reject' ? prompt('Reason for rejecting all selected clearances:') : (prompt('Optional comments for batch approval:') || '');
    if (action === 'reject' && !comments) { toast('Reason required for rejection', 'warning'); return; }
    try {
      const res = await api.call('/clearances/bulk-process', { method: 'POST', body: JSON.stringify({
        clearance_ids: Array.from(selected), action, comments: comments || null
      })});
      toast(`Processed ${res.summary.processed}, skipped ${res.summary.skipped}, fully approved ${res.summary.fully_approved}`, 'success');
      selected.clear();
      load();
    } catch (err) { toast(err.message, 'error'); }
  }

  async function load() {
    tableWrap.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span></div>';
    try {
      const params = new URLSearchParams();
      if (statusSel.value) params.set('status', statusSel.value);
      if (courseSel && courseSel.value) params.set('course', courseSel.value);
      if (yearSel && yearSel.value) params.set('year_level', yearSel.value);
      if (sectionSel && sectionSel.value) params.set('section', sectionSel.value);
      params.set('page_size', '100');
      const data = await api.call(`/clearances/list?${params}`);
      tableWrap.innerHTML = '';
      if (!data.clearances.length) {
        tableWrap.appendChild(DOM.el('div', { class: 'empty-state' }, [DOM.el('i', { class: 'fa-solid fa-file-circle-xmark' }), DOM.el('p', { text: 'No clearances found' })]));
        refreshBulkBar();
        return;
      }
      const table = DOM.el('table');
      const thead = DOM.el('thead');
      const headRow = DOM.el('tr');
      const isFac = state.user.role === 'faculty';
      const baseHeaders = state.user.role === 'student'
        ? ['Type', 'Semester', 'Status', 'Created', 'Action']
        : ['Student', 'ID', 'Type', 'Course', 'Status', 'Created', 'Action'];
      const headers = isFac ? ['', ...baseHeaders] : baseHeaders;
      if (isFac) {
        const selAll = DOM.el('input', { type: 'checkbox', 'data-testid': 'select-all-checkbox', onChange: (e) => {
          const checked = e.target.checked;
          tableWrap.querySelectorAll('tbody input[type=checkbox]').forEach(cb => {
            cb.checked = checked;
            const id = cb.dataset.id;
            if (checked) selected.add(id); else selected.delete(id);
          });
          refreshBulkBar();
        }});
        const th = DOM.el('th'); th.appendChild(selAll); headRow.appendChild(th);
        baseHeaders.forEach(h => headRow.appendChild(DOM.el('th', { text: h })));
      } else {
        headers.forEach(h => headRow.appendChild(DOM.el('th', { text: h })));
      }
      thead.appendChild(headRow); table.appendChild(thead);
      const tbody = DOM.el('tbody');
      data.clearances.forEach(c => {
        const row = DOM.el('tr');
        if (isFac) {
          const td = DOM.el('td');
          const cb = DOM.el('input', { type: 'checkbox', 'data-id': c.id, 'data-testid': `select-${c.id}`, onChange: (e) => {
            if (e.target.checked) selected.add(c.id); else selected.delete(c.id);
            refreshBulkBar();
          }});
          if (selected.has(c.id)) cb.checked = true;
          td.appendChild(cb);
          row.appendChild(td);
        }
        const cells = state.user.role === 'student'
          ? [c.clearance_type || 'End of Semester', `${c.semester} ${c.academic_year}`, statusBadge(c.overall_status), formatDate(c.created_at)]
          : [c.student_name, c.student_number, c.clearance_type || 'End of Semester', `${c.course || ''} ${c.year_level || ''} ${c.section || ''}`, statusBadge(c.overall_status), formatDate(c.created_at)];
        cells.forEach(v => {
          const td = DOM.el('td');
          if (typeof v === 'string') td.textContent = v;
          else td.appendChild(v);
          row.appendChild(td);
        });
        const actionTd = DOM.el('td');
        actionTd.appendChild(DOM.el('button', { class: 'btn btn-sm btn-outline', 'data-testid': `view-clearance-${c.id}`, onClick: () => { state.selectedClearance = c.id; render(); } }, [DOM.el('i', { class: 'fa-solid fa-eye' }), 'View']));
        row.appendChild(actionTd);
        tbody.appendChild(row);
      });
      table.appendChild(tbody);
      tableWrap.appendChild(table);
      refreshBulkBar();
    } catch (err) {
      tableWrap.innerHTML = '';
      tableWrap.appendChild(DOM.el('div', { class: 'alert error' }, [DOM.el('i', { class: 'fa-solid fa-circle-exclamation' }), err.message]));
    }
  }

  statusSel.addEventListener('change', load);
  if (courseSel) courseSel.addEventListener('change', load);
  if (yearSel) yearSel.addEventListener('change', load);
  if (sectionSel) sectionSel.addEventListener('change', load);
  setTimeout(load, 0);
  return wrap;
}

function statusBadge(s) {
  return DOM.el('span', { class: `badge ${s}`, text: (s || 'pending').toUpperCase() });
}
function formatDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}
function formatDateTime(s) {
  if (!s) return '—';
  return new Date(s).toLocaleString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// =========== CREATE CLEARANCE ===========
function renderCreateClearance() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [
      DOM.el('h1', { text: 'Request Clearance' }),
      DOM.el('p', { class: 'subtitle', text: 'Submit a new clearance request to start the approval process.' })
    ])
  ]));

  const card = DOM.el('div', { class: 'card' });
  const form = DOM.el('form', { 'data-testid': 'create-clearance-form', onSubmit: async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Creating...';
    try {
      const data = await api.call('/clearances/create', { method: 'POST', body: JSON.stringify(fd) });
      toast('Clearance request submitted!', 'success');
      state.currentPage = 'clearances'; state.selectedClearance = data.clearance_id; render();
    } catch (err) {
      toast(err.message, 'error');
      btn.disabled = false; btn.textContent = 'Submit Request';
    }
  }});

  form.appendChild(DOM.el('div', { class: 'form-group' }, [
    DOM.el('label', { text: 'Clearance Type *' }),
    DOM.el('select', { name: 'clearance_type', required: true, 'data-testid': 'clearance-type-select' },
      state.constants.clearance_types.map(t => DOM.el('option', { value: t }, t)))
  ]));
  form.appendChild(DOM.el('div', { class: 'form-row' }, [
    DOM.el('div', { class: 'form-group' }, [
      DOM.el('label', { text: 'Semester *' }),
      DOM.el('select', { name: 'semester', required: true, 'data-testid': 'semester-select' },
        ['1st Semester', '2nd Semester', 'Summer', 'Midyear'].map(s => DOM.el('option', { value: s }, s)))
    ]),
    DOM.el('div', { class: 'form-group' }, [
      DOM.el('label', { text: 'Academic Year *' }),
      DOM.el('input', { name: 'academic_year', placeholder: 'e.g. 2025-2026', required: true, 'data-testid': 'academic-year-input' })
    ])
  ]));
  form.appendChild(DOM.el('div', { class: 'form-group' }, [
    DOM.el('label', { text: 'Purpose / Notes (optional)' }),
    DOM.el('textarea', { name: 'purpose', placeholder: 'Add a brief purpose, e.g. for graduation requirements...', 'data-testid': 'purpose-input' })
  ]));

  form.appendChild(DOM.el('div', { class: 'alert info' }, [
    DOM.el('i', { class: 'fa-solid fa-circle-info' }),
    DOM.el('div', { html: 'After submission, you can <strong>upload supporting files</strong> from the clearance detail page.' })
  ]));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary', 'data-testid': 'submit-clearance-btn' }, [DOM.el('i', { class: 'fa-solid fa-paper-plane' }), 'Submit Request']));
  card.appendChild(form);
  wrap.appendChild(card);
  return wrap;
}

// =========== CLEARANCE DETAIL ===========
function renderClearanceDetail() {
  const wrap = DOM.el('div', { id: 'clearance-detail' });
  wrap.appendChild(DOM.el('div', { class: 'page-header no-print' }, [
    DOM.el('div', {}, [
      DOM.el('button', { class: 'link-button mb-8', 'data-testid': 'back-to-list', onClick: () => { state.selectedClearance = null; render(); } }, '← Back to list'),
      DOM.el('h1', { text: 'Clearance Slip' })
    ]),
    DOM.el('button', { class: 'btn btn-primary', 'data-testid': 'print-btn', onClick: () => window.print() }, [DOM.el('i', { class: 'fa-solid fa-print' }), 'Print Slip'])
  ]));

  const card = DOM.el('div', { class: 'card', id: 'detail-card' });
  card.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span></div>';
  wrap.appendChild(card);

  api.call(`/clearances/${state.selectedClearance}`).then(data => {
    const c = data.clearance;
    card.innerHTML = '';

    // ============ OFFICIAL CLEARANCE SLIP (used both on-screen and for print) ============
    const slip = DOM.el('div', { class: 'clearance-slip' });

    // Header with logo
    const slipHeader = DOM.el('div', { class: 'slip-header' });
    slipHeader.appendChild(DOM.el('img', { src: 'images/minsu-logo.jpg', alt: 'MinSU', class: 'slip-logo' }));
    slipHeader.appendChild(DOM.el('h2', { class: 'slip-uni-name', text: 'Mindoro State University' }));
    slipHeader.appendChild(DOM.el('p', { class: 'slip-office', text: 'Office of Student Affairs Services' }));
    slipHeader.appendChild(DOM.el('h3', { class: 'slip-title', text: "STUDENT'S CLEARANCE SLIP" }));
    if (c.clearance_type && c.clearance_type !== 'End of Semester') {
      slipHeader.appendChild(DOM.el('p', { class: 'slip-subtitle', text: `(${c.clearance_type})` }));
    }
    slip.appendChild(slipHeader);

    slip.appendChild(DOM.el('div', { class: 'slip-divider' }));

    // Top info row: semester checkboxes | AY  /  campus checkboxes | College
    const checkbox = (label, checked) => DOM.el('span', { class: 'slip-checkbox' }, [
      DOM.el('span', { class: `slip-cb-box${checked ? ' checked' : ''}`, text: checked ? '✓' : '' }),
      DOM.el('span', { class: 'slip-cb-label', text: label })
    ]);
    const semStr = (c.semester || '').toLowerCase();
    const isFirst = semStr.includes('1st');
    const isSecond = semStr.includes('2nd');
    const isSummer = semStr.includes('summer') || semStr.includes('midyear');
    const camp = (c.campus || '').toUpperCase();

    const infoRow1 = DOM.el('div', { class: 'slip-info-row' }, [
      DOM.el('div', { class: 'slip-info-left' }, [
        checkbox('1st Sem', isFirst),
        checkbox('2nd Sem', isSecond),
        checkbox('Summer', isSummer)
      ]),
      DOM.el('div', { class: 'slip-info-right' }, [
        DOM.el('strong', { text: 'AY ' }),
        DOM.el('strong', { text: c.academic_year || '—' })
      ])
    ]);
    const infoRow2 = DOM.el('div', { class: 'slip-info-row' }, [
      DOM.el('div', { class: 'slip-info-left' }, [
        checkbox('MMC', camp === 'MMC'),
        checkbox('MBC', camp === 'MBC'),
        checkbox('MCC', camp === 'MCC')
      ]),
      DOM.el('div', { class: 'slip-info-right' }, [
        DOM.el('strong', { text: 'College: ' }),
        DOM.el('span', { text: c.college || '—' })
      ])
    ]);
    slip.appendChild(infoRow1);
    slip.appendChild(infoRow2);

    // Student details
    const sf = DOM.el('div', { class: 'slip-fields' });
    const fld = (lbl, val) => DOM.el('div', { class: 'slip-field' }, [
      DOM.el('span', { class: 'slip-field-label', text: lbl }),
      DOM.el('span', { class: 'slip-field-value', text: val || '' })
    ]);
    sf.appendChild(fld('Name:', c.student_name));
    sf.appendChild(fld('Student No.:', c.student_number));
    sf.appendChild(fld('Course/Yr/Sec:', `${c.course || ''} / ${c.year_level || ''} / ${c.section || ''}`));
    slip.appendChild(sf);

    // Approvals table
    const apprTable = DOM.el('table', { class: 'slip-table' });
    apprTable.appendChild(DOM.el('thead', {}, DOM.el('tr', {}, [
      DOM.el('th', { text: 'CLEARING OFFICERS' }),
      DOM.el('th', { text: 'REMARKS' }),
      DOM.el('th', { text: 'DATE' }),
      DOM.el('th', { text: 'APPROVAL CODE' })
    ])));
    const apprBody = DOM.el('tbody');
    (c.approvals || []).forEach(a => {
      const tr = DOM.el('tr');
      tr.appendChild(DOM.el('td', { text: a.office, class: 'slip-officer' }));
      const remarks = a.status === 'approved' ? (a.comments || 'Cleared') : a.status === 'rejected' ? `Rejected: ${a.comments || ''}` : '';
      tr.appendChild(DOM.el('td', { text: remarks }));
      tr.appendChild(DOM.el('td', { text: a.approved_at ? formatDate(a.approved_at) : '' }));
      tr.appendChild(DOM.el('td', { text: a.approval_code || '', class: 'slip-code' }));
      apprBody.appendChild(tr);
    });
    apprTable.appendChild(apprBody);
    slip.appendChild(apprTable);

    slip.appendChild(DOM.el('div', { class: 'slip-divider' }));

    // Validation footer
    slip.appendChild(DOM.el('p', { class: 'slip-validation-title', text: "FOR VALIDATION - REGISTRAR'S OFFICE USE ONLY" }));
    const valBlock = DOM.el('div', { class: 'slip-validation' });
    const validatorApproval = (c.approvals || []).find(a => a.office === 'Registrar' && a.status === 'approved');
    valBlock.appendChild(DOM.el('div', { class: 'slip-sig-block' }, [
      DOM.el('div', { class: 'slip-sig-line', text: validatorApproval ? validatorApproval.approved_by_name : '' }),
      DOM.el('div', { class: 'slip-sig-label' }, [
        DOM.el('strong', { text: 'Validated By:' }),
        DOM.el('span', { class: 'slip-sig-sub', text: 'Signature Over Printed Name' })
      ])
    ]));
    valBlock.appendChild(DOM.el('div', { class: 'slip-sig-block' }, [
      DOM.el('div', { class: 'slip-sig-line', text: validatorApproval ? formatDate(validatorApproval.approved_at) : '' }),
      DOM.el('div', { class: 'slip-sig-label' }, [
        DOM.el('strong', { text: 'Date Validated:' }),
        DOM.el('span', { class: 'slip-sig-sub', text: 'MM/DD/YYYY' })
      ])
    ]));
    slip.appendChild(valBlock);

    slip.appendChild(DOM.el('div', { class: 'slip-footer' }, [
      DOM.el('p', { text: `This clearance is valid for ${c.semester || ''}, AY ${c.academic_year || ''} only.` }),
      DOM.el('p', { class: 'slip-id', text: `Clearance ID: ${c.id}` }),
      DOM.el('p', { class: 'slip-note', text: 'Note: This document requires physical validation signature to be official.' })
    ]));

    card.appendChild(slip);

    // ============ INTERACTIVE SECTION (no-print) ============
    const interactive = DOM.el('div', { class: 'no-print mt-24' });
    interactive.appendChild(DOM.el('div', { class: 'flex-between mb-16' }, [
      DOM.el('h3', { text: 'Status & Actions' }),
      statusBadge(c.overall_status)
    ]));

    if (c.purpose) {
      interactive.appendChild(DOM.el('div', { class: 'alert info' }, [
        DOM.el('i', { class: 'fa-solid fa-circle-info' }),
        DOM.el('div', {}, [DOM.el('strong', { text: 'Purpose: ' }), c.purpose])
      ]));
    }

    // Action buttons section (faculty)
    (c.approvals || []).forEach(a => {
      if (state.user.role === 'faculty' && state.user.office === a.office && a.status === 'pending' && c.overall_status !== 'rejected') {
        const row = DOM.el('div', { class: 'flex gap-8 mb-8' });
        row.appendChild(DOM.el('strong', { text: `Your action for ${a.office}: `, style: { alignSelf: 'center' } }));
        row.appendChild(DOM.el('button', { class: 'btn btn-sm btn-primary', 'data-testid': `approve-${a.office}`, onClick: () => processClearance(c.id, 'approve') }, [DOM.el('i', { class: 'fa-solid fa-check' }), 'Approve']));
        row.appendChild(DOM.el('button', { class: 'btn btn-sm btn-danger', 'data-testid': `reject-${a.office}`, onClick: () => processClearance(c.id, 'reject') }, [DOM.el('i', { class: 'fa-solid fa-xmark' }), 'Reject']));
        interactive.appendChild(row);
      }
    });

    // Rejection notes
    const rejected = (c.approvals || []).filter(a => a.status === 'rejected');
    if (rejected.length) {
      interactive.appendChild(DOM.el('h4', { text: 'Rejection Notes', class: 'mt-16 mb-8' }));
      rejected.forEach(a => {
        interactive.appendChild(DOM.el('div', { class: 'alert error' }, [
          DOM.el('i', { class: 'fa-solid fa-circle-exclamation' }),
          DOM.el('div', {}, [DOM.el('strong', { text: a.office + ': ' }), a.comments || 'No reason provided'])
        ]));
      });
    }

    // Attachments
    interactive.appendChild(DOM.el('div', { class: 'divider' }));
    interactive.appendChild(DOM.el('div', { class: 'flex-between mb-16' }, [
      DOM.el('h3', { text: 'Attachments' }),
      DOM.el('span', { class: 'text-muted', style: { fontSize: '13px' }, text: `${(c.attachments || []).length} file(s)` })
    ]));
    const attList = DOM.el('div', { class: 'attachments-list' });
    if (!(c.attachments || []).length) {
      attList.appendChild(DOM.el('div', { class: 'empty-state', style: { padding: '20px' } }, [
        DOM.el('p', { class: 'text-muted', text: 'No files attached yet.' })
      ]));
    } else {
      c.attachments.forEach(a => {
        attList.appendChild(DOM.el('div', { class: 'attachment-item' }, [
          DOM.el('div', { class: 'file-icon' }, [DOM.el('i', { class: 'fa-solid fa-file' })]),
          DOM.el('div', { class: 'file-info' }, [
            DOM.el('div', { class: 'name', text: a.original_name }),
            DOM.el('div', { class: 'meta', text: `${(a.size / 1024).toFixed(1)} KB · uploaded by ${a.uploaded_by_name} · ${formatDateTime(a.uploaded_at)}${a.description ? ' · ' + a.description : ''}` })
          ]),
          DOM.el('button', { class: 'btn btn-sm btn-outline', onClick: () => downloadAttachment(c.id, a.id) }, [DOM.el('i', { class: 'fa-solid fa-download' }), 'Download'])
        ]));
      });
    }
    interactive.appendChild(attList);

    // Upload zone for student
    if (state.user.role === 'student' && c.student_id === state.user.id && c.overall_status !== 'approved') {
      const upload = DOM.el('div', { class: 'mt-16' });
      upload.appendChild(DOM.el('h4', { text: 'Upload Supporting File', class: 'mb-8' }));
      const uForm = DOM.el('form', { 'data-testid': 'upload-form', onSubmit: async (e) => {
        e.preventDefault();
        const fd = new FormData(e.target);
        if (!fd.get('file') || fd.get('file').size === 0) { toast('Please choose a file', 'error'); return; }
        const btn = e.target.querySelector('button[type=submit]');
        btn.disabled = true; btn.textContent = 'Uploading...';
        try {
          await api.call(`/clearances/${c.id}/upload`, { method: 'POST', body: fd });
          toast('File uploaded!', 'success'); render();
        } catch (err) {
          toast(err.message, 'error');
          btn.disabled = false; btn.textContent = 'Upload';
        }
      }});
      uForm.appendChild(DOM.el('div', { class: 'form-group' }, [
        DOM.el('label', { text: 'Choose file (PDF, DOC, image — max 10MB)' }),
        DOM.el('input', { type: 'file', name: 'file', required: true, 'data-testid': 'upload-file-input', accept: '.pdf,.png,.jpg,.jpeg,.doc,.docx,.xlsx,.txt' })
      ]));
      uForm.appendChild(DOM.el('div', { class: 'form-row' }, [
        DOM.el('div', { class: 'form-group' }, [
          DOM.el('label', { text: 'For Office (optional)' }),
          DOM.el('select', { name: 'office', 'data-testid': 'upload-office-select' }, [DOM.el('option', { value: '' }, 'General'), ...state.constants.offices.map(o => DOM.el('option', { value: o }, o))])
        ]),
        DOM.el('div', { class: 'form-group' }, [
          DOM.el('label', { text: 'Description (optional)' }),
          DOM.el('input', { name: 'description', placeholder: 'e.g. Library clearance receipt', 'data-testid': 'upload-description-input' })
        ])
      ]));
      uForm.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary', 'data-testid': 'upload-submit-btn' }, [DOM.el('i', { class: 'fa-solid fa-upload' }), 'Upload']));
      upload.appendChild(uForm);
      interactive.appendChild(upload);
    }

    card.appendChild(interactive);
  }).catch(err => {
    card.innerHTML = '';
    card.appendChild(DOM.el('div', { class: 'alert error' }, [DOM.el('i', { class: 'fa-solid fa-circle-exclamation' }), err.message]));
  });

  return wrap;
}

async function processClearance(id, action) {
  const comments = action === 'reject' ? prompt('Reason for rejection:') : prompt('Optional comments:') || '';
  if (action === 'reject' && !comments) { toast('Reason is required for rejection', 'warning'); return; }
  try {
    const data = await api.call(`/clearances/${id}/process`, { method: 'POST', body: JSON.stringify({ action, comments: comments || null }) });
    toast(`Clearance ${action}d successfully`, 'success');
    render();
  } catch (err) { toast(err.message, 'error'); }
}

async function downloadAttachment(clearanceId, attachmentId) {
  try {
    const res = await fetch(`${API_BASE}/api/clearances/${clearanceId}/attachments/${attachmentId}/download`, {
      headers: { Authorization: `Bearer ${state.token}` }
    });
    if (!res.ok) throw new Error('Download failed');
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const m = cd.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/);
    const name = m ? decodeURIComponent(m[1]) : 'download';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    URL.revokeObjectURL(a.href);
  } catch (err) { toast(err.message, 'error'); }
}

// =========== ADMIN: USERS ===========
function renderUsersPage() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [DOM.el('h1', { text: 'Users' }), DOM.el('p', { class: 'subtitle', text: 'Manage all user accounts.' })])
  ]));
  const card = DOM.el('div', { class: 'card' });
  const filters = DOM.el('div', { class: 'filters' });
  const search = DOM.el('input', { placeholder: 'Search by name, email, ID...', 'data-testid': 'users-search' });
  filters.appendChild(search);
  card.appendChild(filters);
  const tableWrap = DOM.el('div', { class: 'table-wrap' });
  card.appendChild(tableWrap);
  wrap.appendChild(card);

  const load = async () => {
    tableWrap.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span></div>';
    try {
      const params = new URLSearchParams();
      if (search.value) params.set('search', search.value);
      const data = await api.call(`/admin/users?${params}`);
      tableWrap.innerHTML = '';
      const t = DOM.el('table');
      const head = DOM.el('thead', {}, DOM.el('tr', {}, ['Name', 'Email', 'Role', 'Office/Course', 'Verified', 'Actions'].map(h => DOM.el('th', { text: h }))));
      t.appendChild(head);
      const tb = DOM.el('tbody');
      data.users.forEach(u => {
        const row = DOM.el('tr');
        const roleBadge = u.role === 'superadmin' ? DOM.el('span', { class: 'badge', style: { background: '#1a5f3f', color: 'white' }, text: 'SUPERADMIN' })
          : u.role === 'admin' ? DOM.el('span', { class: 'badge info', text: 'ADMIN' })
          : u.role === 'faculty' ? DOM.el('span', { class: 'badge', style: { background: 'var(--gold-100)', color: 'var(--warning)' }, text: 'FACULTY' })
          : DOM.el('span', { class: 'badge muted', text: u.role.toUpperCase() });
        [u.full_name, u.email, roleBadge,
         u.office || u.course || '—',
         u.email_verified ? DOM.el('span', { class: 'badge approved', text: '✓' }) : DOM.el('span', { class: 'badge muted', text: '—' })
        ].forEach(v => {
          const td = DOM.el('td');
          if (typeof v === 'string') td.textContent = v;
          else td.appendChild(v);
          row.appendChild(td);
        });
        const actTd = DOM.el('td');
        const actGroup = DOM.el('div', { class: 'flex gap-8' });
        const isPrivileged = u.role === 'admin' || u.role === 'superadmin';
        const canManage = !isPrivileged || state.user.role === 'superadmin' || u.id === state.user.id;
        if (canManage) {
          actGroup.appendChild(DOM.el('button', { class: 'btn btn-sm btn-outline', 'data-testid': `reset-pw-${u.id}`, onClick: () => openResetPasswordModal(u) }, [DOM.el('i', { class: 'fa-solid fa-key' }), 'Reset Password']));
        }
        const canDelete = u.id !== state.user.id && (!isPrivileged || state.user.role === 'superadmin');
        if (canDelete) {
          actGroup.appendChild(DOM.el('button', { class: 'btn btn-sm btn-danger', 'data-testid': `delete-user-${u.id}`, onClick: async () => {
            if (!confirm(`Delete ${u.full_name}? This cannot be undone.`)) return;
            try { await api.call(`/admin/users/${u.id}`, { method: 'DELETE' }); toast('User deleted', 'success'); load(); }
            catch (err) { toast(err.message, 'error'); }
          }}, [DOM.el('i', { class: 'fa-solid fa-trash' })]));
        }
        if (!actGroup.children.length) actGroup.appendChild(DOM.el('span', { class: 'text-muted', style: { fontSize: '12px' }, text: '🔒 Protected' }));
        actTd.appendChild(actGroup);
        row.appendChild(actTd);
        tb.appendChild(row);
      });
      t.appendChild(tb);
      tableWrap.appendChild(t);
    } catch (err) {
      tableWrap.innerHTML = '';
      tableWrap.appendChild(DOM.el('div', { class: 'alert error' }, err.message));
    }
  };
  let timer;
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 400); });
  setTimeout(load, 0);
  return wrap;
}

// =========== ADMIN: CREATE USER ===========
function renderCreateUser() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [DOM.el('h1', { text: 'Add Faculty / Admin' }), DOM.el('p', { class: 'subtitle', text: 'Create new staff or admin accounts (pre-verified).' })])
  ]));

  const card = DOM.el('div', { class: 'card' });
  const form = DOM.el('form', { 'data-testid': 'create-user-form', onSubmit: async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Creating...';
    try {
      await api.call('/admin/create-user', { method: 'POST', body: JSON.stringify(fd) });
      toast(`${fd.role} account created!`, 'success');
      e.target.reset();
    } catch (err) { toast(err.message, 'error'); }
    finally { btn.disabled = false; btn.textContent = 'Create Account'; }
  }});

  const roleOpts = [DOM.el('option', { value: 'faculty' }, 'Faculty')];
  if (state.user.role === 'superadmin') {
    roleOpts.push(DOM.el('option', { value: 'admin' }, 'Admin'));
    roleOpts.push(DOM.el('option', { value: 'superadmin' }, 'Superadmin'));
  }
  const roleSel = DOM.el('select', { name: 'role', required: true, 'data-testid': 'create-role-select', onChange: (e) => {
    const v = e.target.value;
    document.getElementById('office-row').style.display = v === 'faculty' ? '' : 'none';
  }}, roleOpts);

  form.appendChild(DOM.el('div', { class: 'form-row' }, [
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Full Name *' }), DOM.el('input', { name: 'full_name', required: true, 'data-testid': 'create-name-input' })]),
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Email *' }), DOM.el('input', { type: 'email', name: 'email', required: true, 'data-testid': 'create-email-input' })])
  ]));
  form.appendChild(DOM.el('div', { class: 'form-row' }, [
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Password *' }), passwordField({ name: 'password', required: true, 'data-testid': 'create-password-input' }).wrap]),
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Role *' }), roleSel])
  ]));
  form.appendChild(DOM.el('div', { id: 'office-row', class: 'form-row' }, [
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Office *' }), DOM.el('select', { name: 'office', 'data-testid': 'create-office-select' }, [DOM.el('option', { value: '' }, 'Select office'), ...state.constants.offices.map(o => DOM.el('option', { value: o }, o))])]),
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Campus' }), DOM.el('select', { name: 'campus', 'data-testid': 'create-campus-select' }, [DOM.el('option', { value: '' }, '—'), ...state.constants.campuses.map(c => DOM.el('option', { value: c }, c))])])
  ]));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary', 'data-testid': 'create-user-submit-btn' }, [DOM.el('i', { class: 'fa-solid fa-user-plus' }), 'Create Account']));
  card.appendChild(form);
  wrap.appendChild(card);
  return wrap;
}

// =========== ADMIN: AUDIT LOG ===========
function renderAuditLog() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [DOM.el('h1', { text: 'Audit Log' }), DOM.el('p', { class: 'subtitle', text: 'A complete record of every action in the system.' })])
  ]));

  const card = DOM.el('div', { class: 'card' });
  const filters = DOM.el('div', { class: 'filters' });
  const actionInp = DOM.el('input', { placeholder: 'Filter by action (e.g. LOGIN)', 'data-testid': 'audit-action-filter' });
  const emailInp = DOM.el('input', { placeholder: 'Filter by user email', 'data-testid': 'audit-email-filter' });
  filters.appendChild(actionInp); filters.appendChild(emailInp);
  card.appendChild(filters);
  const tableWrap = DOM.el('div', { class: 'table-wrap' });
  card.appendChild(tableWrap);
  wrap.appendChild(card);

  const load = async () => {
    tableWrap.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span></div>';
    try {
      const params = new URLSearchParams();
      if (actionInp.value) params.set('action', actionInp.value);
      if (emailInp.value) params.set('actor_email', emailInp.value);
      params.set('page_size', '100');
      const data = await api.call(`/admin/audit-logs?${params}`);
      tableWrap.innerHTML = '';
      if (!data.logs.length) {
        tableWrap.appendChild(DOM.el('div', { class: 'empty-state' }, [DOM.el('i', { class: 'fa-solid fa-clipboard-list' }), DOM.el('p', { text: 'No audit log entries match.' })]));
        return;
      }
      const t = DOM.el('table');
      t.appendChild(DOM.el('thead', {}, DOM.el('tr', {}, ['When', 'Actor', 'Action', 'Target', 'Details', 'IP'].map(h => DOM.el('th', { text: h })))));
      const tb = DOM.el('tbody');
      data.logs.forEach(l => {
        const row = DOM.el('tr');
        row.appendChild(DOM.el('td', { text: formatDateTime(l.timestamp) }));
        row.appendChild(DOM.el('td', {}, [
          DOM.el('div', { style: { fontWeight: '600' }, text: l.actor_email || '—' }),
          DOM.el('div', { class: 'text-muted', style: { fontSize: '12px' }, text: l.actor_role || '' })
        ]));
        const actCell = DOM.el('td');
        actCell.appendChild(DOM.el('span', { class: `badge ${badgeForAction(l.action)}`, text: l.action }));
        row.appendChild(actCell);
        row.appendChild(DOM.el('td', { text: l.target_type ? `${l.target_type}` : '—' }));
        row.appendChild(DOM.el('td', { text: l.details && Object.keys(l.details).length ? JSON.stringify(l.details) : '—', style: { maxWidth: '280px', fontSize: '12px', fontFamily: 'monospace', color: 'var(--ink-500)' } }));
        row.appendChild(DOM.el('td', { text: l.ip || '—', style: { fontFamily: 'monospace', fontSize: '12px' } }));
        tb.appendChild(row);
      });
      t.appendChild(tb);
      tableWrap.appendChild(t);
    } catch (err) {
      tableWrap.innerHTML = '';
      tableWrap.appendChild(DOM.el('div', { class: 'alert error' }, err.message));
    }
  };
  let timer;
  [actionInp, emailInp].forEach(i => i.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(load, 400); }));
  setTimeout(load, 0);
  return wrap;
}

function badgeForAction(action) {
  if (!action) return 'muted';
  if (action.includes('FAILED') || action.includes('REJECTED') || action.includes('DELETED')) return 'rejected';
  if (action.includes('SUCCESS') || action.includes('VERIFIED') || action.includes('APPROVED') || action.includes('CREATED')) return 'approved';
  if (action.includes('LOGIN') || action.includes('LOGOUT')) return 'info';
  return 'muted';
}

// =========== MODAL HELPERS ===========
function showModal(content, opts = {}) {
  const overlay = DOM.el('div', { class: 'modal-overlay', onClick: (e) => { if (e.target === overlay) overlay.remove(); } });
  const modal = DOM.el('div', { class: `modal ${opts.size || ''}` });
  if (opts.title) {
    modal.appendChild(DOM.el('div', { class: 'modal-header' }, [
      DOM.el('h2', { text: opts.title }),
      DOM.el('button', { class: 'modal-close', onClick: () => overlay.remove() }, [DOM.el('i', { class: 'fa-solid fa-xmark' })])
    ]));
  }
  modal.appendChild(DOM.el('div', { class: 'modal-body' }, [content]));
  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  return { close: () => overlay.remove(), modal };
}

// =========== ADMIN: RESET USER PASSWORD MODAL ===========
async function openResetPasswordModal(user) {
  const body = DOM.el('div');
  body.appendChild(DOM.el('p', { class: 'text-muted mb-16', text: `Reset password for ${user.full_name} (${user.email})` }));
  const pwField = passwordField({ name: 'new_password', required: true, 'data-testid': 'reset-pw-field', placeholder: 'New password' });
  body.appendChild(DOM.el('div', { class: 'form-group' }, [
    DOM.el('label', { text: 'New Password' }),
    pwField.wrap
  ]));
  body.appendChild(DOM.el('p', { class: 'input-help', text: 'Min 8 chars · 1 uppercase · 1 lowercase · 1 digit' }));
  const suggestRow = DOM.el('div', { class: 'flex gap-8 mt-8' });
  const suggested = DOM.el('span', { class: 'badge muted', style: { fontFamily: 'monospace', padding: '8px 12px' }, text: '—' });
  const refreshBtn = DOM.el('button', { type: 'button', class: 'btn btn-sm btn-outline', 'data-testid': 'suggest-pw-btn', onClick: async () => {
    try {
      const r = await api.call(`/admin/users/${user.id}/suggest-password`);
      suggested.textContent = r.suggestion;
      pwField.input.value = r.suggestion;
      pwField.input.type = 'text'; // show suggestion by default
    } catch (e) { toast(e.message, 'error'); }
  }}, [DOM.el('i', { class: 'fa-solid fa-wand-magic-sparkles' }), 'Suggest']);
  const useBtn = DOM.el('button', { type: 'button', class: 'btn btn-sm btn-secondary', onClick: () => { if (suggested.textContent !== '—') { pwField.input.value = suggested.textContent; pwField.input.type = 'text'; } } }, 'Use suggestion');
  suggestRow.appendChild(refreshBtn); suggestRow.appendChild(suggested); suggestRow.appendChild(useBtn);
  body.appendChild(suggestRow);

  const actions = DOM.el('div', { class: 'flex gap-8 mt-24', style: { justifyContent: 'flex-end' } });
  const closeBtn = DOM.el('button', { type: 'button', class: 'btn btn-outline', onClick: () => modalCtx.close() }, 'Cancel');
  const saveBtn = DOM.el('button', { type: 'button', class: 'btn btn-primary', 'data-testid': 'save-reset-pw-btn', onClick: async () => {
    const v = pwField.input.value;
    if (!v) { toast('Enter or generate a password first', 'warning'); return; }
    saveBtn.disabled = true; saveBtn.textContent = 'Saving...';
    try {
      await api.call(`/admin/users/${user.id}/reset-password`, { method: 'POST', body: JSON.stringify({ new_password: v }) });
      toast(`Password updated for ${user.email}`, 'success');
      modalCtx.close();
    } catch (e) {
      toast(e.message, 'error');
      saveBtn.disabled = false; saveBtn.textContent = 'Save password';
    }
  }}, 'Save password');
  actions.appendChild(closeBtn); actions.appendChild(saveBtn);
  body.appendChild(actions);

  const modalCtx = showModal(body, { title: 'Reset Password', size: '' });
  refreshBtn.click();
}

// =========== ADMIN: EMAIL SETTINGS PAGE ===========
function renderSettings() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [DOM.el('h1', { text: 'Email Settings' }), DOM.el('p', { class: 'subtitle', text: 'Configure SendGrid for outgoing emails. Changes take effect immediately — no restart needed.' })])
  ]));

  const card = DOM.el('div', { class: 'card', id: 'settings-card' });
  card.innerHTML = '<div class="text-center" style="padding:40px"><span class="spinner"></span></div>';
  wrap.appendChild(card);

  api.call('/admin/settings').then(s => {
    card.innerHTML = '';
    card.appendChild(DOM.el('div', { class: 'alert info' }, [
      DOM.el('i', { class: 'fa-solid fa-circle-info' }),
      DOM.el('div', { html: 'Don\'t have a SendGrid account? Sign up free at <a href="https://sendgrid.com" target="_blank">sendgrid.com</a> (100 emails/day free). Then verify your sender at <strong>Settings → Sender Authentication</strong> before sending.' })
    ]));

    const form = DOM.el('form', { 'data-testid': 'settings-form', onSubmit: async (e) => {
      e.preventDefault();
      const fd = Object.fromEntries(new FormData(e.target).entries());
      // If api key field was untouched, send empty string only when user explicitly cleared. We use a marker.
      const payload = {
        sender_email: fd.sender_email,
        sender_name: fd.sender_name
      };
      // Only include API key if user typed something
      if (fd.sendgrid_api_key && fd.sendgrid_api_key.trim()) {
        payload.sendgrid_api_key = fd.sendgrid_api_key.trim();
      }
      const btn = e.target.querySelector('button[type=submit]');
      btn.disabled = true; btn.textContent = 'Saving...';
      try {
        await api.call('/admin/settings', { method: 'POST', body: JSON.stringify(payload) });
        toast('Settings saved', 'success'); render();
      } catch (err) {
        toast(err.message, 'error');
        btn.disabled = false; btn.textContent = 'Save Settings';
      }
    }});

    form.appendChild(DOM.el('div', { class: 'form-group' }, [
      DOM.el('label', { text: 'SendGrid API Key' }),
      passwordField({ name: 'sendgrid_api_key', placeholder: s.sendgrid_api_key_set ? `Currently: ${s.sendgrid_api_key_masked} (leave blank to keep)` : 'SG.xxxx...', 'data-testid': 'settings-apikey-input' }).wrap,
      DOM.el('p', { class: 'input-help', text: s.sendgrid_api_key_set ? `✓ Configured (source: ${s.source.sendgrid_api_key})` : '⚠ Not configured — emails will not send.' })
    ]));
    form.appendChild(DOM.el('div', { class: 'form-row' }, [
      DOM.el('div', { class: 'form-group' }, [
        DOM.el('label', { text: 'Sender Email *' }),
        DOM.el('input', { type: 'email', name: 'sender_email', value: s.sender_email || '', required: true, 'data-testid': 'settings-sender-email' }),
        DOM.el('p', { class: 'input-help', text: 'Must be verified in SendGrid (Single Sender or Domain Auth)' })
      ]),
      DOM.el('div', { class: 'form-group' }, [
        DOM.el('label', { text: 'Sender Name *' }),
        DOM.el('input', { type: 'text', name: 'sender_name', value: s.sender_name || '', required: true, 'data-testid': 'settings-sender-name' })
      ])
    ]));
    form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary', 'data-testid': 'save-settings-btn' }, [DOM.el('i', { class: 'fa-solid fa-save' }), 'Save Settings']));
    card.appendChild(form);

    // Test email box
    card.appendChild(DOM.el('div', { class: 'divider' }));
    card.appendChild(DOM.el('h3', { text: 'Send a test email' }));
    card.appendChild(DOM.el('p', { class: 'text-muted mb-16', text: 'Verify your configuration by sending a test message.' }));
    const testRow = DOM.el('div', { class: 'flex gap-8' });
    const toInput = DOM.el('input', { type: 'email', placeholder: 'your-email@example.com', 'data-testid': 'test-email-to-input', value: state.user.email });
    const sendBtn = DOM.el('button', { class: 'btn btn-secondary', 'data-testid': 'send-test-email-btn', onClick: async () => {
      if (!toInput.value) { toast('Enter a recipient', 'warning'); return; }
      sendBtn.disabled = true; sendBtn.textContent = 'Sending...';
      try {
        await api.call('/admin/settings/test-email', { method: 'POST', body: JSON.stringify({ to_email: toInput.value }) });
        toast(`Test email sent to ${toInput.value}`, 'success');
      } catch (err) { toast(err.message, 'error'); }
      sendBtn.disabled = false; sendBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Send test';
    }}, [DOM.el('i', { class: 'fa-solid fa-paper-plane' }), 'Send test']);
    testRow.appendChild(toInput); testRow.appendChild(sendBtn);
    card.appendChild(testRow);
  }).catch(err => {
    card.innerHTML = '';
    card.appendChild(DOM.el('div', { class: 'alert error' }, err.message));
  });

  return wrap;
}

// =========== PROFILE / CHANGE OWN PASSWORD ===========
function renderProfile() {
  const wrap = DOM.el('div');
  wrap.appendChild(DOM.el('div', { class: 'page-header' }, [
    DOM.el('div', {}, [DOM.el('h1', { text: 'My Account' }), DOM.el('p', { class: 'subtitle', text: 'View profile information and update your password.' })])
  ]));

  const u = state.user;
  const infoCard = DOM.el('div', { class: 'card' });
  infoCard.appendChild(DOM.el('h2', { text: 'Profile', class: 'mb-16' }));
  const dg = DOM.el('div', { class: 'detail-grid' });
  const items = [
    ['Full Name', u.full_name], ['Email', u.email], ['Role', u.role],
    ['Office', u.office], ['Student ID', u.student_id], ['Course', u.course],
    ['Year & Section', u.year_level ? `${u.year_level} · ${u.section || ''}` : null],
    ['Campus', u.campus], ['College', u.college]
  ].filter(x => x[1]);
  items.forEach(([l, v]) => dg.appendChild(DOM.el('div', { class: 'detail-item' }, [
    DOM.el('div', { class: 'label', text: l }),
    DOM.el('div', { class: 'value', text: v })
  ])));
  infoCard.appendChild(dg);
  wrap.appendChild(infoCard);

  const pwCard = DOM.el('div', { class: 'card' });
  pwCard.appendChild(DOM.el('h2', { text: 'Change Password', class: 'mb-16' }));
  const form = DOM.el('form', { 'data-testid': 'change-password-form', onSubmit: async (e) => {
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(e.target).entries());
    if (fd.new_password !== fd.confirm_password) { toast('New passwords do not match', 'error'); return; }
    const btn = e.target.querySelector('button[type=submit]');
    btn.disabled = true; btn.textContent = 'Saving...';
    try {
      await api.call('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: fd.current_password, new_password: fd.new_password }) });
      toast('Password changed successfully', 'success');
      e.target.reset();
    } catch (err) { toast(err.message, 'error'); }
    btn.disabled = false; btn.textContent = 'Update Password';
  }});
  form.appendChild(DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Current Password' }), passwordField({ name: 'current_password', required: true, 'data-testid': 'current-pw-input' }).wrap]));
  form.appendChild(DOM.el('div', { class: 'form-row' }, [
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'New Password' }), passwordField({ name: 'new_password', required: true, 'data-testid': 'new-pw-input' }).wrap]),
    DOM.el('div', { class: 'form-group' }, [DOM.el('label', { text: 'Confirm New Password' }), passwordField({ name: 'confirm_password', required: true, 'data-testid': 'confirm-pw-input' }).wrap])
  ]));
  form.appendChild(DOM.el('p', { class: 'input-help', text: 'Min 8 chars · 1 uppercase · 1 lowercase · 1 digit' }));
  form.appendChild(DOM.el('button', { type: 'submit', class: 'btn btn-primary', 'data-testid': 'change-pw-submit-btn' }, [DOM.el('i', { class: 'fa-solid fa-key' }), 'Update Password']));
  pwCard.appendChild(form);
  wrap.appendChild(pwCard);

  return wrap;
}

// =========== START ===========
init();
