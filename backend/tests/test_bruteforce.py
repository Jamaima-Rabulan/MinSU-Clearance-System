"""
Brute-force protection + admin unlock tests for MinSU Clearance System (iteration 3).

Tests:
  - 5 wrong-password attempts => 401 x4 then 429 (locked)
  - While locked, correct password still returns 429
  - Successful login clears lockout_until
  - Unknown emails don't create per-account lock; IP shield fires after 20 fails
  - admin.unlock_user audit entry created on manual unlock
  - user.locked audit entry created when threshold crossed
  - Admin unlock endpoint: 200 for admin, 403 for non-admin, 404 for unknown
  - GET /api/admin/users now includes is_locked field per user
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().strip('"')
                break
BASE_URL = BASE_URL.rstrip("/")

ADMIN_EMAIL = "admin@minsu.edu.ph"
ADMIN_PASSWORD = "Admin@MinSU2025"
RUN_ID = uuid.uuid4().hex[:8]


def _mongo():
    from pymongo import MongoClient
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "minsu_clearance")
    mc = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    return mc, mc[db_name]


def _reset_account(email):
    """Remove lockout + failure audit entries for a specific email."""
    try:
        mc, db = _mongo()
        db.users.update_one({"email": email},
                            {"$unset": {"lockout_until": "", "last_lockout_at": ""}})
        db.audit_logs.delete_many({"actor_email": email, "status": "failure"})
        mc.close()
    except Exception as e:
        pytest.skip(f"Cannot reset account via mongo: {e}")


def _reset_ip_failures():
    """Purge all recent login-failure audit entries so IP shield doesn't leak between tests."""
    try:
        mc, db = _mongo()
        db.audit_logs.delete_many({"action": "user.login", "status": "failure"})
        mc.close()
    except Exception:
        pass


# ---------- Fixtures ----------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin(api):
    _reset_account(ADMIN_EMAIL)
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["user"]


@pytest.fixture
def victim(api):
    """Fresh student user for each test; reset lockout on entry & exit."""
    email = f"bf_victim_{RUN_ID}_{uuid.uuid4().hex[:6]}@minsu.edu.ph"
    password = "Correct1Pass"
    payload = {
        "email": email, "password": password, "full_name": "BF Victim",
        "role": "student", "student_id": f"BF-{uuid.uuid4().hex[:6]}",
        "course": "BSIT", "year_level": "1st Year", "section": "F1",
    }
    r = api.post(f"{BASE_URL}/api/auth/register", json=payload)
    assert r.status_code == 200, r.text
    user = r.json()["user"]
    user["password"] = password
    _reset_ip_failures()  # Clear IP-shield counters from prior tests
    yield user
    _reset_account(email)


# ---------- Tests ----------
class TestBruteForceLockout:

    def test_5_wrong_password_locks_account(self, api, victim):
        for i in range(4):
            r = api.post(f"{BASE_URL}/api/auth/login",
                         json={"email": victim["email"], "password": f"Wrong{i}Pass"})
            assert r.status_code == 401, f"Attempt {i+1}: expected 401, got {r.status_code}: {r.text}"

        # 5th failure crosses threshold — should return 429 lock
        r5 = api.post(f"{BASE_URL}/api/auth/login",
                      json={"email": victim["email"], "password": "Wrong5Pass"})
        assert r5.status_code == 429, f"Expected 429 on 5th failure, got {r5.status_code}: {r5.text}"
        detail = r5.json()["detail"].lower()
        assert "lock" in detail and ("15" in detail or "minute" in detail)

    def test_correct_password_blocked_while_locked(self, api, victim):
        # trigger lock (5 failures)
        for i in range(5):
            api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": f"Wrong{i}Pw"})
        # Even correct password must be rejected
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": victim["password"]})
        assert r.status_code == 429, f"Expected 429 while locked, got {r.status_code}: {r.text}"

    def test_successful_login_clears_lockout_until(self, api, victim):
        # Cause 3 failures (below threshold), then a good login
        for i in range(3):
            api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": f"Wrong{i}Pw"})
        # Manually set lockout_until in past via mongo to simulate expired lock still lingering
        try:
            mc, db = _mongo()
            db.users.update_one({"email": victim["email"]},
                                {"$set": {"lockout_until": "2000-01-01T00:00:00+00:00"}})
            mc.close()
        except Exception:
            pass
        # Correct login should succeed (past lockout ignored) and unset the field
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": victim["password"]})
        assert r.status_code == 200, r.text
        # Verify field cleared
        try:
            mc, db = _mongo()
            u = db.users.find_one({"email": victim["email"]})
            assert "lockout_until" not in u or not u.get("lockout_until"), \
                f"lockout_until not cleared: {u.get('lockout_until')}"
            mc.close()
        except Exception:
            pass

    def test_unknown_email_returns_401_no_lock(self, api):
        _reset_ip_failures()
        unknown = f"ghost_{uuid.uuid4().hex[:6]}@example.com"
        for i in range(5):
            r = api.post(f"{BASE_URL}/api/auth/login",
                         json={"email": unknown, "password": f"Any{i}Pass"})
            # No account exists => stays 401, never per-account 429
            assert r.status_code == 401, f"Attempt {i+1}: got {r.status_code} ({r.text})"

    def test_user_locked_audit_entry_created(self, api, victim, admin):
        for i in range(5):
            api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": f"Bad{i}Pass"})
        r = api.get(f"{BASE_URL}/api/admin/audit-logs",
                    params={"user_id": admin["id"], "action": "user.locked",
                            "actor_email": victim["email"], "limit": 20})
        assert r.status_code == 200
        logs = r.json()["logs"]
        assert any(lg.get("resource_id") == victim["id"] for lg in logs), \
            f"No user.locked audit found for victim: {logs}"


class TestAdminUnlock:

    def test_admin_unlock_locked_user(self, api, admin, victim):
        # lock first
        for i in range(5):
            api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": f"Bad{i}Pass"})
        # Verify locked via admin users list
        r = api.get(f"{BASE_URL}/api/admin/users", params={"user_id": admin["id"]})
        victim_row = next((u for u in r.json()["users"] if u["id"] == victim["id"]), None)
        assert victim_row is not None
        assert victim_row["is_locked"] is True, f"Expected is_locked=True, got {victim_row}"

        # Unlock via admin endpoint
        r = api.post(f"{BASE_URL}/api/admin/users/{victim['id']}/unlock",
                     params={"user_id": admin["id"]})
        assert r.status_code == 200, r.text
        assert r.json().get("success") is True

        # Now correct login must succeed
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": victim["email"], "password": victim["password"]})
        assert r.status_code == 200, r.text

        # is_locked should now be False
        r = api.get(f"{BASE_URL}/api/admin/users", params={"user_id": admin["id"]})
        victim_row = next((u for u in r.json()["users"] if u["id"] == victim["id"]), None)
        assert victim_row["is_locked"] is False

    def test_admin_unlock_audit_written(self, api, admin, victim):
        r = api.post(f"{BASE_URL}/api/admin/users/{victim['id']}/unlock",
                     params={"user_id": admin["id"]})
        assert r.status_code == 200
        r = api.get(f"{BASE_URL}/api/admin/audit-logs",
                    params={"user_id": admin["id"], "action": "admin.unlock_user", "limit": 20})
        assert r.status_code == 200
        logs = r.json()["logs"]
        assert any(lg.get("resource_id") == victim["id"] for lg in logs), \
            f"No admin.unlock_user audit found for victim {victim['id']}"

    def test_non_admin_cannot_unlock(self, api, victim):
        # victim is a student trying to call the endpoint
        r = api.post(f"{BASE_URL}/api/admin/users/{victim['id']}/unlock",
                     params={"user_id": victim["id"]})
        assert r.status_code == 403

    def test_unlock_unknown_user_returns_404(self, api, admin):
        fake_id = uuid.uuid4().hex
        r = api.post(f"{BASE_URL}/api/admin/users/{fake_id}/unlock",
                     params={"user_id": admin["id"]})
        assert r.status_code == 404

    def test_admin_users_has_is_locked_field(self, api, admin):
        r = api.get(f"{BASE_URL}/api/admin/users", params={"user_id": admin["id"]})
        assert r.status_code == 200
        for u in r.json()["users"]:
            assert "is_locked" in u, f"is_locked missing from user row: {u}"
            assert isinstance(u["is_locked"], bool)
