"""
MinSU Clearance System - Backend API Tests
Covers: auth (register/login/logout), bcrypt hashing, clearances (create/list/process),
registrar-last rule, stats, admin (users/audit-logs), clearance audit trail.
"""

import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback: read frontend .env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().strip('"')
                    break
    except Exception:
        pass
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
BASE_URL = BASE_URL.rstrip("/")

ADMIN_EMAIL = "admin@minsu.edu.ph"
ADMIN_PASSWORD = "Admin@MinSU2025"

RUN_ID = uuid.uuid4().hex[:8]
OFFICES = [
    "University Librarian",
    "Guidance Counselor",
    "SAS Director/Coordinator",
    "Student Affairs/Finance",
    "College Dean/Program Chair",
    "Registrar",
]


# --------------------- Fixtures ---------------------
@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def admin(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return r.json()["user"]


@pytest.fixture(scope="session")
def student(api):
    payload = {
        "email": f"test_student_{RUN_ID}@minsu.edu.ph",
        "password": "Student@2025",
        "full_name": "Test Student",
        "role": "student",
        "student_id": f"MBC2024-{RUN_ID}",
        "course": "BSIT",
        "year_level": "3rd Year",
        "section": "F1",
        "campus": "MBC",
        "college": "CCS",
    }
    r = api.post(f"{BASE_URL}/api/auth/register", json=payload)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    return {**data["user"], "password": payload["password"]}


@pytest.fixture(scope="session")
def faculty_users(api):
    users = {}
    office_keys = {
        "University Librarian": "librarian",
        "Guidance Counselor": "guidance",
        "SAS Director/Coordinator": "sas",
        "Student Affairs/Finance": "finance",
        "College Dean/Program Chair": "dean",
        "Registrar": "registrar",
    }
    for office in OFFICES:
        key = office_keys[office]
        payload = {
            "email": f"test_fac_{key}_{RUN_ID}@minsu.edu.ph",
            "password": "Faculty@2025",
            "full_name": f"Test {office}",
            "role": "faculty",
            "office": office,
        }
        r = api.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert r.status_code == 200, f"{office}: {r.text}"
        users[office] = r.json()["user"]
    return users


# --------------------- Health ---------------------
def test_root(api):
    r = api.get(f"{BASE_URL}/api/")
    assert r.status_code == 200
    assert "MinSU" in r.json().get("message", "")


def test_constants(api):
    r = api.get(f"{BASE_URL}/api/constants")
    assert r.status_code == 200
    d = r.json()
    for key in ["offices", "courses", "year_levels", "sections", "campuses", "colleges"]:
        assert key in d and isinstance(d[key], list) and len(d[key]) > 0
    assert set(d["offices"]) == set(OFFICES)


# --------------------- Auth ---------------------
class TestAuth:
    def test_admin_login(self, admin):
        assert admin["role"] == "admin"
        assert admin["email"] == ADMIN_EMAIL

    def test_login_wrong_password(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": ADMIN_EMAIL, "password": "WrongPassword"})
        assert r.status_code == 401

    def test_login_unknown_user(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": f"nouser_{RUN_ID}@x.com", "password": "x"})
        assert r.status_code == 401

    def test_register_student_success(self, student):
        assert student["role"] == "student"
        assert student["course"] == "BSIT"

    def test_register_duplicate_email(self, api, student):
        payload = {
            "email": student["email"], "password": "x", "full_name": "dup",
            "role": "student", "student_id": "X", "course": "BSIT",
            "year_level": "1st Year", "section": "F1",
        }
        r = api.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert r.status_code == 400

    def test_register_student_missing_fields(self, api):
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"bad_{RUN_ID}@x.com", "password": "p",
            "full_name": "x", "role": "student"
        })
        assert r.status_code == 400

    def test_register_faculty_bad_office(self, api):
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"badfac_{RUN_ID}@x.com", "password": "p",
            "full_name": "x", "role": "faculty", "office": "NotAnOffice"
        })
        assert r.status_code == 400

    def test_get_user(self, api, student):
        r = api.get(f"{BASE_URL}/api/auth/user/{student['id']}")
        assert r.status_code == 200
        assert r.json()["email"] == student["email"]

    def test_logout_writes_audit(self, api, student, admin):
        r = api.post(f"{BASE_URL}/api/auth/logout", params={"user_id": student["id"]})
        assert r.status_code == 200
        # Verify via admin audit-logs
        r2 = api.get(f"{BASE_URL}/api/admin/audit-logs",
                     params={"user_id": admin["id"], "action": "user.logout"})
        assert r2.status_code == 200
        logs = r2.json()["logs"]
        assert any(lg.get("resource_id") == student["id"] for lg in logs)


# --------------------- Bcrypt verification ---------------------
class TestBcrypt:
    def test_bcrypt_hash_format_via_mongo(self, student):
        """Verify directly in MongoDB that new user has $2b$ hash."""
        try:
            from pymongo import MongoClient
        except ImportError:
            pytest.skip("pymongo not installed")
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "minsu_clearance")
        mc = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
        try:
            user = mc[db_name].users.find_one({"id": student["id"]})
            assert user is not None, "Student not found in DB"
            ph = user.get("password_hash", "")
            assert ph.startswith("$2"), f"Expected bcrypt hash, got {ph[:10]}"
            # Admin hash should also be bcrypt
            admin_doc = mc[db_name].users.find_one({"email": ADMIN_EMAIL})
            assert admin_doc["password_hash"].startswith("$2")
        finally:
            mc.close()

    def test_new_user_can_login(self, api, student):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": student["email"], "password": student["password"]})
        assert r.status_code == 200


# --------------------- Clearance ---------------------
class TestClearance:
    def test_create_clearance_as_student(self, api, student):
        r = api.post(f"{BASE_URL}/api/clearances/create",
                     params={"user_id": student["id"]},
                     json={"semester": "1st Semester", "academic_year": "2025-2026"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "clearance_id" in data
        student["_clr_id"] = data["clearance_id"]

    def test_faculty_cannot_create(self, api, faculty_users):
        fac = faculty_users["University Librarian"]
        r = api.post(f"{BASE_URL}/api/clearances/create",
                     params={"user_id": fac["id"]},
                     json={"semester": "1st Semester", "academic_year": "2025-2026"})
        assert r.status_code == 403

    def test_get_clearance(self, api, student):
        cid = student["_clr_id"]
        r = api.get(f"{BASE_URL}/api/clearances/{cid}",
                    params={"user_id": student["id"]})
        assert r.status_code == 200
        c = r.json()["clearance"]
        assert c["overall_status"] == "pending"
        assert len(c["approvals"]) == 6

    def test_student_list_own(self, api, student):
        r = api.get(f"{BASE_URL}/api/clearances/list",
                    params={"user_id": student["id"]})
        assert r.status_code == 200
        assert len(r.json()["clearances"]) >= 1

    def test_faculty_list_pending(self, api, faculty_users):
        fac = faculty_users["University Librarian"]
        r = api.get(f"{BASE_URL}/api/clearances/list", params={"user_id": fac["id"]})
        assert r.status_code == 200
        # Should include the freshly created one
        assert any(True for _ in r.json()["clearances"])

    def test_registrar_gated_when_others_pending(self, api, student, faculty_users):
        cid = student["_clr_id"]
        registrar = faculty_users["Registrar"]
        r = api.post(f"{BASE_URL}/api/clearances/{cid}/process",
                     params={"user_id": registrar["id"]},
                     json={"action": "approve"})
        assert r.status_code == 400
        assert "Registrar" in r.text or "pending" in r.text.lower()

    def test_approve_non_registrar_offices(self, api, student, faculty_users):
        cid = student["_clr_id"]
        for office in OFFICES:
            if office == "Registrar":
                continue
            fac = faculty_users[office]
            r = api.post(f"{BASE_URL}/api/clearances/{cid}/process",
                         params={"user_id": fac["id"]},
                         json={"action": "approve", "comments": f"ok by {office}"})
            assert r.status_code == 200, f"{office}: {r.text}"

    def test_registrar_can_approve_last(self, api, student, faculty_users):
        cid = student["_clr_id"]
        registrar = faculty_users["Registrar"]
        r = api.post(f"{BASE_URL}/api/clearances/{cid}/process",
                     params={"user_id": registrar["id"]},
                     json={"action": "approve"})
        assert r.status_code == 200, r.text
        # Verify approved end-state
        g = api.get(f"{BASE_URL}/api/clearances/{cid}",
                    params={"user_id": student["id"]})
        assert g.json()["clearance"]["overall_status"] == "approved"

    def test_double_process_blocked(self, api, student, faculty_users):
        cid = student["_clr_id"]
        fac = faculty_users["University Librarian"]
        r = api.post(f"{BASE_URL}/api/clearances/{cid}/process",
                     params={"user_id": fac["id"]},
                     json={"action": "approve"})
        assert r.status_code == 400


# --------------------- Rejection flow (separate clearance) ---------------------
class TestRejection:
    def test_reject_flow(self, api):
        # New student
        email = f"test_rej_student_{RUN_ID}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": "Student@2025", "full_name": "Rej Student",
            "role": "student", "student_id": f"REJ-{RUN_ID}", "course": "BSIT",
            "year_level": "2nd Year", "section": "F1", "campus": "MBC", "college": "CCS",
        })
        assert r.status_code == 200
        st = r.json()["user"]
        r = api.post(f"{BASE_URL}/api/clearances/create",
                     params={"user_id": st["id"]},
                     json={"semester": "2nd Semester", "academic_year": "2025-2026"})
        cid = r.json()["clearance_id"]
        # Reuse previously-registered faculty from main session would fail (different session scope),
        # so register a fresh faculty here.
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"test_rej_fac_{RUN_ID}@minsu.edu.ph", "password": "Faculty@2025",
            "full_name": "Rej Fac", "role": "faculty", "office": "Guidance Counselor",
        })
        assert r.status_code == 200
        fac = r.json()["user"]
        r = api.post(f"{BASE_URL}/api/clearances/{cid}/process",
                     params={"user_id": fac["id"]},
                     json={"action": "reject", "comments": "missing docs"})
        assert r.status_code == 200
        g = api.get(f"{BASE_URL}/api/clearances/{cid}", params={"user_id": st["id"]})
        assert g.json()["clearance"]["overall_status"] == "rejected"


# --------------------- Stats ---------------------
class TestStats:
    def test_admin_stats(self, api, admin):
        r = api.get(f"{BASE_URL}/api/stats", params={"user_id": admin["id"]})
        assert r.status_code == 200
        d = r.json()
        for k in ["total", "pending", "approved", "rejected"]:
            assert k in d and isinstance(d[k], int)
        assert d["total"] >= 1

    def test_student_stats(self, api, student):
        r = api.get(f"{BASE_URL}/api/stats", params={"user_id": student["id"]})
        assert r.status_code == 200
        assert r.json()["total"] >= 1


# --------------------- Admin endpoints ---------------------
class TestAdmin:
    def test_admin_list_users(self, api, admin):
        r = api.get(f"{BASE_URL}/api/admin/users", params={"user_id": admin["id"]})
        assert r.status_code == 200
        users = r.json()["users"]
        assert any(u["email"] == ADMIN_EMAIL for u in users)
        # password_hash must not leak
        for u in users:
            assert "password_hash" not in u

    def test_non_admin_blocked(self, api, student):
        r = api.get(f"{BASE_URL}/api/admin/users", params={"user_id": student["id"]})
        assert r.status_code == 403

    def test_admin_audit_logs(self, api, admin):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs",
                    params={"user_id": admin["id"], "limit": 500})
        assert r.status_code == 200
        logs = r.json()["logs"]
        actions = {lg["action"] for lg in logs}
        expected = {"user.register", "user.login", "user.logout",
                    "clearance.create", "clearance.approve", "clearance.reject"}
        missing = expected - actions
        assert not missing, f"Missing audit actions: {missing}"

    def test_admin_audit_actions_endpoint(self, api, admin):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs/actions",
                    params={"user_id": admin["id"]})
        assert r.status_code == 200
        d = r.json()
        assert "actions" in d and "resource_types" in d
        assert "user.register" in d["actions"]

    def test_admin_delete_user(self, api, admin):
        # Create a disposable user
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": f"test_del_{RUN_ID}_{uuid.uuid4().hex[:4]}@minsu.edu.ph",
            "password": "Pass@2025", "full_name": "Del User", "role": "student",
            "student_id": "DEL-1", "course": "BSIT", "year_level": "1st Year",
            "section": "F1", "campus": "MBC", "college": "CCS",
        })
        assert r.status_code == 200
        target = r.json()["user"]
        r = api.delete(f"{BASE_URL}/api/admin/users/{target['id']}",
                       params={"user_id": admin["id"]})
        assert r.status_code == 200
        # Verify gone
        r2 = api.get(f"{BASE_URL}/api/auth/user/{target['id']}")
        assert r2.status_code == 404

    def test_non_admin_cannot_delete(self, api, student):
        r = api.delete(f"{BASE_URL}/api/admin/users/{student['id']}",
                       params={"user_id": student["id"]})
        assert r.status_code == 403


# --------------------- Clearance audit-trail ---------------------
class TestClearanceAuditTrail:
    def test_trail_contains_lifecycle(self, api, student):
        cid = student["_clr_id"]
        r = api.get(f"{BASE_URL}/api/clearances/{cid}/audit-trail",
                    params={"user_id": student["id"]})
        assert r.status_code == 200
        trail = r.json()["trail"]
        actions = [t["action"] for t in trail]
        assert "clearance.create" in actions
        # 5 non-registrar approvals + 1 registrar approval = 6 approves
        assert actions.count("clearance.approve") == 6
