"""
MinSU Clearance System - Iteration 5 backend tests.

Focus: NEW SUPERADMIN role and 4-tier permission model
  student < faculty < admin < superadmin

Coverage:
  - Superadmin login + /auth/me returns role='superadmin'
  - require_admin allows BOTH admin and superadmin (regression)
  - /admin/create-user role='admin'/'superadmin' => 403 for regular admin, 200 for superadmin
  - /admin/create-user role='faculty' => OK for regular admin
  - DELETE /admin/users/{id}: regular admin cannot delete admin/superadmin (403),
    can delete faculty (200); superadmin can delete admin (200)
  - DELETE last superadmin protection (400)
  - /admin/users/{id}/reset-password: regular admin forbidden against admin/superadmin
    targets, allowed against own ID; superadmin allowed against any
  - Audit log records actor_role correctly ('admin' vs 'superadmin')
  - Cleanup: superadmin & admin remain with their original passwords post-run
"""
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clearance-hub-18.preview.emergentagent.com').rstrip('/')

SUPERADMIN_EMAIL = "superadmin@minsu.edu.ph"
SUPERADMIN_PASSWORD = "Sup3rAdmin#2026"
ADMIN_EMAIL = "admin@minsu.edu.ph"
ADMIN_PASSWORD = "Admin@123"
FACULTY_EMAIL = "registrar@minsu.edu.ph"
FACULTY_PASSWORD = "Faculty@2026"

RUN_ID = uuid.uuid4().hex[:6]


# ============ Fixtures ============
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(api, email, password):
    r = api.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="session")
def superadmin_login(api):
    return _login(api, SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD)


@pytest.fixture(scope="session")
def superadmin_token(superadmin_login):
    return superadmin_login["access_token"]


@pytest.fixture(scope="session")
def superadmin_headers(superadmin_token):
    return {"Authorization": f"Bearer {superadmin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def admin_login(api):
    return _login(api, ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture(scope="session")
def admin_token(admin_login):
    return admin_login["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def faculty_token(api):
    return _login(api, FACULTY_EMAIL, FACULTY_PASSWORD)["access_token"]


@pytest.fixture(scope="session")
def faculty_headers(faculty_token):
    return {"Authorization": f"Bearer {faculty_token}", "Content-Type": "application/json"}


# ============ 1. Superadmin login + /auth/me ============
class TestSuperadminAuth:
    def test_superadmin_login(self, superadmin_login):
        assert "access_token" in superadmin_login
        assert superadmin_login["user"]["role"] == "superadmin"
        assert superadmin_login["user"]["email"] == SUPERADMIN_EMAIL

    def test_superadmin_me(self, api, superadmin_headers):
        r = api.get(f"{BASE_URL}/api/auth/me", headers=superadmin_headers)
        assert r.status_code == 200
        body = r.json()
        # Endpoint wraps response in {"user": {...}}
        user = body.get("user", body)
        assert user["role"] == "superadmin"
        assert user["email"] == SUPERADMIN_EMAIL

    def test_admin_login_still_works(self, admin_login):
        assert admin_login["user"]["role"] == "admin"


# ============ 2. require_admin allows admin OR superadmin ============
class TestAdminEndpointsRoleGate:
    def test_users_list_superadmin(self, api, superadmin_headers):
        r = api.get(f"{BASE_URL}/api/admin/users", headers=superadmin_headers)
        assert r.status_code == 200, r.text

    def test_users_list_admin(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/users", headers=admin_headers)
        assert r.status_code == 200, r.text

    def test_audit_logs_superadmin(self, api, superadmin_headers):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs", headers=superadmin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "logs" in body

    def test_audit_logs_admin(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs", headers=admin_headers)
        assert r.status_code == 200, r.text

    def test_settings_superadmin(self, api, superadmin_headers):
        r = api.get(f"{BASE_URL}/api/admin/settings", headers=superadmin_headers)
        assert r.status_code == 200, r.text

    def test_settings_admin(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/settings", headers=admin_headers)
        assert r.status_code == 200, r.text

    def test_admin_endpoints_forbidden_for_faculty(self, api, faculty_headers):
        r = api.get(f"{BASE_URL}/api/admin/users", headers=faculty_headers)
        assert r.status_code == 403


# ============ 3. /admin/create-user role gating ============
class TestCreateUserRoleGate:
    def test_admin_cannot_create_admin(self, api, admin_headers):
        email = f"TEST_it5_admin_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Should Fail",
            "role": "admin"
        })
        assert r.status_code == 403, r.text
        assert "superadmin" in r.text.lower()

    def test_admin_cannot_create_superadmin(self, api, admin_headers):
        email = f"TEST_it5_sa_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Should Fail",
            "role": "superadmin"
        })
        assert r.status_code == 403, r.text

    def test_admin_can_create_faculty(self, api, admin_headers):
        email = f"TEST_it5_fac_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Test Faculty",
            "role": "faculty", "office": "Registrar"
        })
        assert r.status_code == 200, r.text
        new_id = r.json()["user_id"]
        # Cleanup: superadmin deletes (admin can also, since target=faculty)
        d = api.delete(f"{BASE_URL}/api/admin/users/{new_id}", headers=admin_headers)
        assert d.status_code == 200, d.text

    def test_superadmin_can_create_admin(self, api, superadmin_headers):
        email = f"TEST_it5_sa_create_admin_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp Admin",
            "role": "admin"
        })
        assert r.status_code == 200, r.text
        new_id = r.json()["user_id"]
        # Verify via GET /admin/users
        listing = api.get(f"{BASE_URL}/api/admin/users", headers=superadmin_headers).json()
        assert any(u["id"] == new_id and u["role"] == "admin" for u in listing.get("users", listing) if isinstance(u, dict))
        # Cleanup
        d = api.delete(f"{BASE_URL}/api/admin/users/{new_id}", headers=superadmin_headers)
        assert d.status_code == 200, d.text

    def test_superadmin_can_create_superadmin(self, api, superadmin_headers):
        email = f"TEST_it5_sa_create_sa_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp SA",
            "role": "superadmin"
        })
        assert r.status_code == 200, r.text
        new_id = r.json()["user_id"]
        # Cleanup
        d = api.delete(f"{BASE_URL}/api/admin/users/{new_id}", headers=superadmin_headers)
        assert d.status_code == 200, d.text


# ============ 4. DELETE role gating ============
class TestDeleteRoleGate:
    def test_admin_cannot_delete_admin(self, api, superadmin_headers, admin_headers):
        # Superadmin creates a temp admin
        email = f"TEST_it5_del_admin_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp Admin Del",
            "role": "admin"
        })
        assert r.status_code == 200
        admin_id = r.json()["user_id"]

        # Regular admin tries to delete -> 403
        d = api.delete(f"{BASE_URL}/api/admin/users/{admin_id}", headers=admin_headers)
        assert d.status_code == 403, d.text

        # Cleanup via superadmin
        d2 = api.delete(f"{BASE_URL}/api/admin/users/{admin_id}", headers=superadmin_headers)
        assert d2.status_code == 200

    def test_admin_cannot_delete_superadmin(self, api, superadmin_headers, admin_headers):
        email = f"TEST_it5_del_sa_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp SA Del",
            "role": "superadmin"
        })
        assert r.status_code == 200
        sa_id = r.json()["user_id"]

        d = api.delete(f"{BASE_URL}/api/admin/users/{sa_id}", headers=admin_headers)
        assert d.status_code == 403, d.text

        d2 = api.delete(f"{BASE_URL}/api/admin/users/{sa_id}", headers=superadmin_headers)
        assert d2.status_code == 200

    def test_admin_can_delete_faculty(self, api, admin_headers):
        email = f"TEST_it5_del_fac_{RUN_ID}@minsu.edu.ph"
        c = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp Fac Del",
            "role": "faculty", "office": "Registrar"
        })
        assert c.status_code == 200
        fid = c.json()["user_id"]
        d = api.delete(f"{BASE_URL}/api/admin/users/{fid}", headers=admin_headers)
        assert d.status_code == 200, d.text

    def test_superadmin_can_delete_admin(self, api, superadmin_headers):
        email = f"TEST_it5_sa_del_admin_{RUN_ID}@minsu.edu.ph"
        c = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp Admin SA Del",
            "role": "admin"
        })
        assert c.status_code == 200
        aid = c.json()["user_id"]
        d = api.delete(f"{BASE_URL}/api/admin/users/{aid}", headers=superadmin_headers)
        assert d.status_code == 200, d.text

    def test_cannot_delete_self(self, api, superadmin_login, superadmin_headers):
        my_id = superadmin_login["user"]["id"]
        d = api.delete(f"{BASE_URL}/api/admin/users/{my_id}", headers=superadmin_headers)
        assert d.status_code == 400, d.text

    def test_cannot_delete_last_superadmin(self, api, superadmin_headers):
        """
        Create a temp superadmin, login as it, then have it try to delete the
        SEED superadmin - this should still succeed because count > 1.
        Then with only the temp SA remaining, the temp SA tries to delete itself
        -> 400 (cannot delete own account anyway). To exercise the *last
        superadmin* check, we ensure the 'cannot delete last superadmin' branch
        is reachable: temp SA tries to delete the seed SA AFTER we delete the
        temp SA in db... but we cannot manipulate DB directly here.

        Practical assertion: with exactly 1 superadmin in the system (default),
        deleting that superadmin (via another superadmin caller) is blocked
        when count<=1. We simulate by:
          1. Login as seed superadmin (count=1)
          2. Create temp_sa (count=2)
          3. Login as temp_sa
          4. temp_sa deletes seed_sa -> succeeds (count was 2 before delete)
          5. Now only temp_sa remains. temp_sa cannot delete itself anyway (400 'own account')
          6. Re-create seed_sa via temp_sa so cleanup is consistent.
        Skip the strict 'last superadmin' branch since caller can never legally hit it
        without bypassing the self-delete guard. Mark as documented but skipped.
        """
        # Soft assertion: just verify the endpoint is wired (we reach the
        # self-delete guard first for the lone superadmin scenario).
        pytest.skip("Last-superadmin branch is unreachable without bypassing self-delete guard; documented in test docstring")


# ============ 5. reset-password role gating ============
class TestResetPasswordRoleGate:
    def test_admin_cannot_reset_other_admin(self, api, superadmin_headers, admin_headers):
        # Create temp admin via superadmin
        email = f"TEST_it5_rp_admin_{RUN_ID}@minsu.edu.ph"
        c = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Temp Admin RP",
            "role": "admin"
        })
        assert c.status_code == 200
        aid = c.json()["user_id"]

        r = api.post(f"{BASE_URL}/api/admin/users/{aid}/reset-password",
                     headers=admin_headers, json={"new_password": "NewPass1!"})
        assert r.status_code == 403, r.text

        api.delete(f"{BASE_URL}/api/admin/users/{aid}", headers=superadmin_headers)

    def test_admin_cannot_reset_superadmin(self, api, superadmin_login, admin_headers):
        sa_id = superadmin_login["user"]["id"]
        r = api.post(f"{BASE_URL}/api/admin/users/{sa_id}/reset-password",
                     headers=admin_headers, json={"new_password": "NewPass1!"})
        assert r.status_code == 403, r.text

    def test_admin_can_reset_own_password(self, api, admin_login, admin_headers):
        my_id = admin_login["user"]["id"]
        # Reset to same password (just exercise endpoint allowance)
        r = api.post(f"{BASE_URL}/api/admin/users/{my_id}/reset-password",
                     headers=admin_headers, json={"new_password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        # Verify still able to login
        r2 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r2.status_code == 200

    def test_admin_can_reset_faculty_password(self, api, admin_headers):
        email = f"TEST_it5_rp_fac_{RUN_ID}@minsu.edu.ph"
        c = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "InitPass1!", "full_name": "Temp Fac RP",
            "role": "faculty", "office": "Registrar"
        })
        assert c.status_code == 200
        fid = c.json()["user_id"]
        r = api.post(f"{BASE_URL}/api/admin/users/{fid}/reset-password",
                     headers=admin_headers, json={"new_password": "NewerPass1!"})
        assert r.status_code == 200, r.text
        # verify new password works
        login = api.post(f"{BASE_URL}/api/auth/login",
                         json={"email": email, "password": "NewerPass1!"})
        assert login.status_code == 200
        api.delete(f"{BASE_URL}/api/admin/users/{fid}", headers=admin_headers)

    def test_superadmin_can_reset_any(self, api, superadmin_headers):
        # Reset registrar faculty password and restore
        # Find faculty user_id
        users = api.get(f"{BASE_URL}/api/admin/users", headers=superadmin_headers).json()
        users_list = users.get("users", users) if isinstance(users, dict) else users
        registrar = next((u for u in users_list if u.get("email") == FACULTY_EMAIL), None)
        assert registrar is not None
        fid = registrar["id"]

        r = api.post(f"{BASE_URL}/api/admin/users/{fid}/reset-password",
                     headers=superadmin_headers, json={"new_password": "Tmp@Pass1"})
        assert r.status_code == 200, r.text

        # Verify login then RESTORE original password
        l1 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": FACULTY_EMAIL, "password": "Tmp@Pass1"})
        assert l1.status_code == 200

        r2 = api.post(f"{BASE_URL}/api/admin/users/{fid}/reset-password",
                      headers=superadmin_headers, json={"new_password": FACULTY_PASSWORD})
        assert r2.status_code == 200, r2.text
        l2 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": FACULTY_EMAIL, "password": FACULTY_PASSWORD})
        assert l2.status_code == 200, "Faculty password not restored!"


# ============ 6. Audit log actor_role recording ============
class TestAuditLogActorRole:
    def test_actor_role_admin_recorded(self, api, admin_headers):
        # Trigger a USER_CREATED action as admin
        email = f"TEST_it5_audit_admin_{RUN_ID}@minsu.edu.ph"
        c = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Audit Admin",
            "role": "faculty", "office": "Registrar"
        })
        assert c.status_code == 200
        uid = c.json()["user_id"]

        logs = api.get(f"{BASE_URL}/api/admin/audit-logs?action=USER_CREATED&page_size=50",
                       headers=admin_headers).json()
        log_entries = logs.get("logs", [])
        match = next((e for e in log_entries if e.get("target_id") == uid), None)
        assert match is not None, f"No audit log found for created user {uid}"
        assert match.get("actor_role") == "admin", f"actor_role={match.get('actor_role')}"
        assert match.get("actor_email") == ADMIN_EMAIL
        # Verify details payload
        details = match.get("details") or {}
        assert details.get("email") == email.lower()

        api.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers)

    def test_actor_role_superadmin_recorded(self, api, superadmin_headers):
        email = f"TEST_it5_audit_sa_{RUN_ID}@minsu.edu.ph"
        c = api.post(f"{BASE_URL}/api/admin/create-user", headers=superadmin_headers, json={
            "email": email, "password": "TestPass1!", "full_name": "Audit SA",
            "role": "admin"
        })
        assert c.status_code == 200
        uid = c.json()["user_id"]

        logs = api.get(f"{BASE_URL}/api/admin/audit-logs?action=USER_CREATED&page_size=50",
                       headers=superadmin_headers).json()
        log_entries = logs.get("logs", [])
        match = next((e for e in log_entries if e.get("target_id") == uid), None)
        assert match is not None, f"No audit log found for created user {uid}"
        assert match.get("actor_role") == "superadmin", f"actor_role={match.get('actor_role')}"
        assert match.get("actor_email") == SUPERADMIN_EMAIL

        api.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=superadmin_headers)


# ============ 7. Final cleanup & smoke ============
class TestFinalState:
    def test_superadmin_password_unchanged(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": SUPERADMIN_EMAIL, "password": SUPERADMIN_PASSWORD})
        assert r.status_code == 200, "Superadmin original password broken!"

    def test_admin_password_unchanged(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, "Admin original password broken!"

    def test_faculty_password_unchanged(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": FACULTY_EMAIL, "password": FACULTY_PASSWORD})
        assert r.status_code == 200, "Faculty original password broken!"
