"""
MinSU Clearance System - Iteration 3 backend tests.
Focus on NEW functionality:
  - Admin Email Settings (GET/POST /api/admin/settings) DB-backed override of SendGrid env
  - POST /api/admin/settings/test-email
  - GET  /api/admin/users/{id}/suggest-password (strong password generator)
  - POST /api/admin/users/{id}/reset-password (admin resets any user)
  - POST /api/auth/change-password (self-service)
  - Audit log entries: SETTINGS_UPDATED, PASSWORD_RESET_BY_ADMIN, PASSWORD_CHANGED
  - Regression: admin login, password complexity, faculty seeded, bulk-process
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clearance-hub-18.preview.emergentagent.com').rstrip('/')

ADMIN_EMAIL = "admin@minsu.edu.ph"
ADMIN_PASSWORD = "Admin@123"
FACULTY_EMAIL = "registrar@minsu.edu.ph"
FACULTY_PASSWORD = "Faculty@2026"

# We will create a throw-away user for change-password / reset-password tests
RUN_ID = uuid.uuid4().hex[:6]
TEST_USER_EMAIL = f"TEST_it3_{RUN_ID}@minsu.edu.ph"
TEST_USER_INITIAL_PW = "InitPass1!"
TEST_USER_FULL_NAME = f"TEST Iter3 User {RUN_ID}"

state = {}


# ============ Fixtures ============
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def faculty_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": FACULTY_EMAIL, "password": FACULTY_PASSWORD})
    assert r.status_code == 200, f"Faculty login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def test_user(api, admin_headers):
    """Create a throw-away faculty user via admin/create-user. Cleaned up at session end."""
    payload = {
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_INITIAL_PW,
        "full_name": TEST_USER_FULL_NAME,
        "role": "faculty",
        "office": "Registrar"
    }
    r = api.post(f"{BASE_URL}/api/admin/create-user", json=payload, headers=admin_headers)
    assert r.status_code in (200, 201), f"create-user failed: {r.status_code} {r.text}"
    j = r.json()
    user = j.get("user") or j
    user_id = user.get("id") or user.get("user_id")
    assert user_id, f"No id in create-user response: {j}"
    state["test_user_id"] = user_id
    state["test_user_email"] = TEST_USER_EMAIL
    state["test_user_password"] = TEST_USER_INITIAL_PW
    yield {"id": user_id, "email": TEST_USER_EMAIL, "password": TEST_USER_INITIAL_PW}
    # Teardown: delete the user
    try:
        api.delete(f"{BASE_URL}/api/admin/users/{user_id}", headers=admin_headers)
    except Exception:
        pass


def _login(api, email, password):
    return api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})


# ============ Health / regression: admin login ============
class TestRegressionBaseline:
    def test_admin_login_still_works(self, api):
        r = _login(api, ADMIN_EMAIL, ADMIN_PASSWORD)
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_faculty_seeded_login(self, api):
        r = _login(api, FACULTY_EMAIL, FACULTY_PASSWORD)
        assert r.status_code == 200, f"Faculty login failed: {r.text}"

    def test_password_complexity_still_enforced_on_register(self, api):
        # Weak password rejected
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"TEST_weak_{uuid.uuid4().hex[:6]}@minsu.edu.ph",
            "password": "abc",
            "full_name": "Weak Tester",
            "student_id": "2025-99999",
            "course": "BSCS",
            "year_level": "1st Year",
            "section": "F1",
            "campus": "MMC",
            "college": "CCS"
        })
        assert r.status_code == 400
        assert any(k in r.text.lower() for k in ["password", "8", "uppercase", "digit"])


# ============ Admin Settings GET ============
class TestAdminSettingsGet:
    def test_get_settings_unauthenticated(self, api):
        r = api.get(f"{BASE_URL}/api/admin/settings")
        assert r.status_code in (401, 403)

    def test_get_settings_as_faculty_forbidden(self, api, faculty_token):
        r = api.get(f"{BASE_URL}/api/admin/settings",
                    headers={"Authorization": f"Bearer {faculty_token}"})
        assert r.status_code == 403

    def test_get_settings_as_admin(self, api, admin_headers):
        # Reset any prior overrides first
        api.post(f"{BASE_URL}/api/admin/settings",
                 json={"sender_name": "", "sender_email": "", "sendgrid_api_key": ""},
                 headers=admin_headers)

        r = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("sendgrid_api_key_masked", "sendgrid_api_key_set", "sender_email", "sender_name", "source"):
            assert k in j, f"missing key {k} in {j}"
        assert isinstance(j["source"], dict)
        for k in ("sendgrid_api_key", "sender_email", "sender_name"):
            assert j["source"][k] == "env", f"After cleanup, {k} source should be 'env', got {j['source'][k]}"
        # API key should never be sent in clear-text
        assert "sendgrid_api_key" not in j  # only the masked version is present
        state["initial_sender_name"] = j["sender_name"]
        state["initial_sender_email"] = j["sender_email"]


# ============ Admin Settings POST ============
class TestAdminSettingsPost:
    def test_unauthenticated_post(self, api):
        r = api.post(f"{BASE_URL}/api/admin/settings", json={"sender_name": "X"})
        assert r.status_code in (401, 403)

    def test_faculty_post_forbidden(self, api, faculty_token):
        r = api.post(f"{BASE_URL}/api/admin/settings",
                     json={"sender_name": "X"},
                     headers={"Authorization": f"Bearer {faculty_token}"})
        assert r.status_code == 403

    def test_update_sender_name(self, api, admin_headers):
        new_name = f"TEST Sender {RUN_ID}"
        r = api.post(f"{BASE_URL}/api/admin/settings",
                     json={"sender_name": new_name}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

        # Verify GET reflects the change with source=db
        g = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert g.status_code == 200
        gj = g.json()
        assert gj["sender_name"] == new_name
        assert gj["source"]["sender_name"] == "db"
        # other fields untouched
        assert gj["source"]["sender_email"] == "env"

    def test_clear_override_with_empty_string(self, api, admin_headers):
        # Set first
        api.post(f"{BASE_URL}/api/admin/settings",
                 json={"sender_email": "tmp_override@minsu.edu.ph"}, headers=admin_headers)
        g1 = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers).json()
        assert g1["source"]["sender_email"] == "db"

        # Clear with empty string
        r = api.post(f"{BASE_URL}/api/admin/settings",
                     json={"sender_email": ""}, headers=admin_headers)
        assert r.status_code == 200

        g2 = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers).json()
        assert g2["source"]["sender_email"] == "env"

    def test_update_sendgrid_api_key_masked(self, api, admin_headers):
        new_key = "SG.test123ABCDEFghij_dummyForTesting1234"
        r = api.post(f"{BASE_URL}/api/admin/settings",
                     json={"sendgrid_api_key": new_key}, headers=admin_headers)
        assert r.status_code == 200

        g = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers).json()
        assert g["sendgrid_api_key_set"] is True
        assert g["source"]["sendgrid_api_key"] == "db"
        masked = g["sendgrid_api_key_masked"]
        # Should start with "SG.tes" and not contain the full key
        assert masked.startswith("SG.tes"), f"masked should keep prefix, got {masked}"
        assert new_key not in masked
        assert "..." in masked


# ============ Test-email endpoint ============
class TestTestEmail:
    def test_test_email_unauthenticated(self, api):
        r = api.post(f"{BASE_URL}/api/admin/settings/test-email",
                     json={"to_email": "anywhere@example.com"})
        assert r.status_code in (401, 403)

    def test_test_email_faculty_forbidden(self, api, faculty_token):
        r = api.post(f"{BASE_URL}/api/admin/settings/test-email",
                     json={"to_email": "anywhere@example.com"},
                     headers={"Authorization": f"Bearer {faculty_token}"})
        assert r.status_code == 403

    def test_test_email_admin_unverified_sender(self, api, admin_headers):
        # First, ensure DB sendgrid key is cleared so we use the real env key
        api.post(f"{BASE_URL}/api/admin/settings",
                 json={"sendgrid_api_key": ""}, headers=admin_headers)

        r = api.post(f"{BASE_URL}/api/admin/settings/test-email",
                     json={"to_email": "deliverability-check@example.com"},
                     headers=admin_headers)
        # Expected: 500 because sender unverified, BUT if env has no key configured,
        # endpoint returns 400 ("No SendGrid API key configured") which is also acceptable evidence
        # the endpoint is wired correctly. Either way, it should NOT 200.
        assert r.status_code in (400, 500), f"Unexpected status {r.status_code}: {r.text}"
        detail = (r.json().get("detail") or "").lower()
        if r.status_code == 500:
            assert "sender" in detail and "verified" in detail, \
                f"500 detail must mention sender verification, got: {detail}"


# ============ Suggest password ============
class TestSuggestPassword:
    def test_suggest_password_returns_strong(self, api, admin_headers, test_user):
        r = api.get(f"{BASE_URL}/api/admin/users/{test_user['id']}/suggest-password",
                    headers=admin_headers)
        assert r.status_code == 200, r.text
        s = r.json().get("suggestion", "")
        assert isinstance(s, str)
        assert len(s) >= 8
        assert any(c.isupper() for c in s), f"no upper in {s}"
        assert any(c.islower() for c in s), f"no lower in {s}"
        assert any(c.isdigit() for c in s), f"no digit in {s}"

    def test_suggest_password_unique(self, api, admin_headers, test_user):
        s1 = api.get(f"{BASE_URL}/api/admin/users/{test_user['id']}/suggest-password",
                     headers=admin_headers).json()["suggestion"]
        s2 = api.get(f"{BASE_URL}/api/admin/users/{test_user['id']}/suggest-password",
                     headers=admin_headers).json()["suggestion"]
        assert s1 != s2, "suggestions should be random"

    def test_suggest_password_unauthenticated(self, api, test_user):
        r = api.get(f"{BASE_URL}/api/admin/users/{test_user['id']}/suggest-password")
        assert r.status_code in (401, 403)


# ============ Admin reset password ============
class TestAdminResetPassword:
    def test_reset_unauthenticated(self, api, test_user):
        r = api.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/reset-password",
                     json={"new_password": "Strong1Pass!"})
        assert r.status_code in (401, 403)

    def test_reset_faculty_forbidden(self, api, faculty_token, test_user):
        r = api.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/reset-password",
                     json={"new_password": "Strong1Pass!"},
                     headers={"Authorization": f"Bearer {faculty_token}"})
        assert r.status_code == 403

    def test_reset_weak_password_rejected(self, api, admin_headers, test_user):
        r = api.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/reset-password",
                     json={"new_password": "abc"}, headers=admin_headers)
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert any(t in detail for t in ["8", "uppercase", "digit", "lowercase", "password"])

    def test_reset_strong_password_works(self, api, admin_headers, test_user):
        new_pw = f"NewAdmReset{RUN_ID}1!"
        r = api.post(f"{BASE_URL}/api/admin/users/{test_user['id']}/reset-password",
                     json={"new_password": new_pw}, headers=admin_headers)
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

        # Login with new password should succeed
        l_new = _login(api, test_user["email"], new_pw)
        assert l_new.status_code == 200, f"login with new pw failed: {l_new.text}"

        # Login with old password should fail
        l_old = _login(api, test_user["email"], TEST_USER_INITIAL_PW)
        assert l_old.status_code in (400, 401, 403), f"old pw still works! {l_old.status_code}"

        state["test_user_password"] = new_pw  # remember for change-password tests


# ============ Change own password ============
class TestChangeOwnPassword:
    def test_change_password_unauthenticated(self, api):
        r = api.post(f"{BASE_URL}/api/auth/change-password",
                     json={"current_password": "x", "new_password": "Strong1Pass!"})
        assert r.status_code == 401

    def _user_token(self, api):
        pw = state.get("test_user_password", TEST_USER_INITIAL_PW)
        r = _login(api, state["test_user_email"], pw)
        assert r.status_code == 200, f"user login failed: {r.text}"
        return r.json()["access_token"]

    def test_change_password_wrong_current(self, api, test_user):
        token = self._user_token(api)
        r = api.post(f"{BASE_URL}/api/auth/change-password",
                     json={"current_password": "WrongPwd123!", "new_password": "AnotherStrong1!"},
                     headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "current password" in (r.json().get("detail") or "").lower()

    def test_change_password_weak_new(self, api, test_user):
        token = self._user_token(api)
        cur = state["test_user_password"]
        r = api.post(f"{BASE_URL}/api/auth/change-password",
                     json={"current_password": cur, "new_password": "abc"},
                     headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        detail = (r.json().get("detail") or "").lower()
        assert any(t in detail for t in ["8", "uppercase", "digit", "lowercase"])

    def test_change_password_same_as_current(self, api, test_user):
        token = self._user_token(api)
        cur = state["test_user_password"]
        r = api.post(f"{BASE_URL}/api/auth/change-password",
                     json={"current_password": cur, "new_password": cur},
                     headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 400
        assert "different" in (r.json().get("detail") or "").lower()

    def test_change_password_success(self, api, test_user):
        token = self._user_token(api)
        cur = state["test_user_password"]
        new_pw = f"ChangedSelf{RUN_ID}1!"
        r = api.post(f"{BASE_URL}/api/auth/change-password",
                     json={"current_password": cur, "new_password": new_pw},
                     headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

        # New password works
        l_new = _login(api, test_user["email"], new_pw)
        assert l_new.status_code == 200

        # Old password fails
        l_old = _login(api, test_user["email"], cur)
        assert l_old.status_code in (400, 401, 403)

        state["test_user_password"] = new_pw


# ============ Audit logs ============
class TestAuditLogs:
    def _fetch_actions(self, api, admin_headers, actions, limit=200):
        # The audit endpoint in iter-1 supports page-based; iter-2 added cursor.
        r = api.get(f"{BASE_URL}/api/admin/audit-logs?page_size={limit}",
                    headers=admin_headers)
        assert r.status_code == 200, r.text
        logs = r.json().get("logs", [])
        return [lg for lg in logs if lg.get("action") in actions]

    def test_audit_contains_new_actions(self, api, admin_headers):
        actions = self._fetch_actions(api, admin_headers,
                                      {"SETTINGS_UPDATED", "PASSWORD_RESET_BY_ADMIN", "PASSWORD_CHANGED"})
        found = {lg["action"] for lg in actions}
        assert "SETTINGS_UPDATED" in found, f"SETTINGS_UPDATED missing. Found: {found}"
        assert "PASSWORD_RESET_BY_ADMIN" in found, f"PASSWORD_RESET_BY_ADMIN missing. Found: {found}"
        assert "PASSWORD_CHANGED" in found, f"PASSWORD_CHANGED missing. Found: {found}"


# ============ Regression: bulk-process still works (smoke) ============
class TestBulkProcessSmoke:
    def test_bulk_process_endpoint_reachable(self, api, faculty_token):
        # Send empty list — should validate input, not 500
        r = api.post(f"{BASE_URL}/api/clearances/bulk-process",
                     json={"clearance_ids": [], "action": "approve"},
                     headers={"Authorization": f"Bearer {faculty_token}"})
        # Acceptable: 200 with 0 processed, OR 400 validation error
        assert r.status_code in (200, 400, 422), f"Unexpected: {r.status_code} {r.text}"


# ============ Cleanup: restore env-default settings ============
@pytest.fixture(scope="session", autouse=True)
def _cleanup_settings(admin_headers, request):
    """Restore env-default state for app_settings + restore test user pw if any."""
    yield
    try:
        s = requests.Session()
        s.headers.update(admin_headers)
        # Clear all overrides
        s.post(f"{BASE_URL}/api/admin/settings",
               json={"sendgrid_api_key": "", "sender_email": "", "sender_name": ""})
    except Exception as e:
        print(f"cleanup failed: {e}")
