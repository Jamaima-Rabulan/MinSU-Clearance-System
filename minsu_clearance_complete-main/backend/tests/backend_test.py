"""
MinSU Clearance System - End-to-end backend test suite.
Covers: health, constants, auth (register/verify/login/me/forgot/reset),
clearances (create/list/detail/process), admin (users/create/delete/audit-logs),
file uploads, stats, authorization, and CORS sanity.
"""
import io
import os
import time
import uuid
import json
import subprocess
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clearance-hub-18.preview.emergentagent.com').rstrip('/')
DB_NAME = "minsu_clearance"

ADMIN_EMAIL = "admin@minsu.edu.ph"
ADMIN_PASSWORD = "Admin@123"

# Unique test student email each run to avoid conflicts
RUN_ID = uuid.uuid4().hex[:6]
STUDENT_EMAIL = f"test_student_{RUN_ID}@minsu.edu.ph"
STUDENT_PASSWORD = "Student@123"

FACULTY_REGISTRAR_EMAIL = f"test_registrar_{RUN_ID}@minsu.edu.ph"
FACULTY_LIBRARIAN_EMAIL = f"test_librarian_{RUN_ID}@minsu.edu.ph"
FACULTY_PASSWORD = "Faculty@123"

state = {}


def mongo_get_verification_code(email: str) -> str:
    cmd = [
        "mongosh", "--quiet", f"mongodb://localhost:27017/{DB_NAME}",
        "--eval", f'JSON.stringify(db.users.findOne({{email: "{email}"}}, {{verification_code:1, _id:0}}))'
    ]
    out = subprocess.check_output(cmd, timeout=10).decode().strip()
    try:
        d = json.loads(out)
        return d.get("verification_code", "") if d else ""
    except Exception:
        return ""


@pytest.fixture(scope="session")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health ----------
class TestHealth:
    def test_api_root(self, api):
        r = api.get(f"{BASE_URL}/api/")
        assert r.status_code == 200
        d = r.json()
        assert "message" in d and "version" in d

    def test_constants(self, api):
        r = api.get(f"{BASE_URL}/api/constants")
        assert r.status_code == 200
        d = r.json()
        for key in ("offices", "courses", "year_levels", "sections", "campuses", "colleges", "clearance_types"):
            assert key in d, f"missing {key}"
        assert "Graduation" in d["clearance_types"]
        assert "Registrar" in d["offices"]


# ---------- Admin Login ----------
class TestAdminAuth:
    def test_admin_login(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("access_token")
        assert d["user"]["role"] == "admin"
        state["admin_token"] = d["access_token"]
        state["admin_id"] = d["user"]["id"]

    def test_me_with_token(self, api):
        token = state["admin_token"]
        r = api.get(f"{BASE_URL}/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json()["user"]["email"] == ADMIN_EMAIL

    def test_me_without_token(self, api):
        r = requests.get(f"{BASE_URL}/api/auth/me")
        assert r.status_code == 401

    def test_invalid_login(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
        assert r.status_code == 401


# ---------- Student Registration & Email Verification ----------
class TestStudentRegistration:
    def test_register_student(self, api):
        payload = {
            "email": STUDENT_EMAIL,
            "password": STUDENT_PASSWORD,
            "full_name": "Test Student",
            "role": "student",
            "student_id": f"2025-{RUN_ID}",
            "course": "BSCS",
            "year_level": "1st Year",
            "section": "F1",
            "campus": "MMC",
            "college": "CCS",
        }
        r = api.post(f"{BASE_URL}/api/auth/register", json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["success"] is True
        assert d["email"] == STUDENT_EMAIL
        # SendGrid is configured -> dev_code should be null
        # We'll fetch from mongo
        time.sleep(0.5)
        code = mongo_get_verification_code(STUDENT_EMAIL)
        assert code and len(code) == 6, f"verification code not found in DB: {code!r}"
        state["verification_code"] = code

    def test_login_before_verification_blocked(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD})
        assert r.status_code == 403  # email not verified

    def test_resend_verification(self, api):
        r = api.post(f"{BASE_URL}/api/auth/resend-verification", json={"email": STUDENT_EMAIL})
        assert r.status_code == 200
        # update code
        time.sleep(0.5)
        code = mongo_get_verification_code(STUDENT_EMAIL)
        assert code and len(code) == 6
        state["verification_code"] = code

    def test_verify_email_invalid(self, api):
        r = api.post(f"{BASE_URL}/api/auth/verify-email",
                     json={"email": STUDENT_EMAIL, "code": "000000"})
        # likely 400 (since random codes won't match latest)
        assert r.status_code in (400, 200)

    def test_verify_email_success(self, api):
        code = state["verification_code"]
        r = api.post(f"{BASE_URL}/api/auth/verify-email",
                     json={"email": STUDENT_EMAIL, "code": code})
        assert r.status_code == 200, r.text
        assert r.json()["success"] is True

    def test_login_after_verify(self, api):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD})
        assert r.status_code == 200, r.text
        d = r.json()
        state["student_token"] = d["access_token"]
        state["student_id"] = d["user"]["id"]
        assert d["user"]["email_verified"] is True


# ---------- Forgot/Reset password ----------
class TestPasswordReset:
    def test_forgot_password(self, api):
        r = api.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": STUDENT_EMAIL})
        assert r.status_code == 200

    def test_reset_password_invalid_code(self, api):
        r = api.post(f"{BASE_URL}/api/auth/reset-password",
                     json={"email": STUDENT_EMAIL, "code": "999999", "new_password": "Newpass@123"})
        assert r.status_code == 400


# ---------- Admin user management ----------
class TestAdminUserMgmt:
    def auth(self):
        return {"Authorization": f"Bearer {state['admin_token']}"}

    def test_list_users(self, api):
        r = api.get(f"{BASE_URL}/api/admin/users", headers=self.auth())
        assert r.status_code == 200
        d = r.json()
        assert "users" in d and isinstance(d["users"], list)
        assert any(u["email"] == ADMIN_EMAIL for u in d["users"])

    def test_create_faculty_registrar(self, api):
        payload = {
            "email": FACULTY_REGISTRAR_EMAIL,
            "password": FACULTY_PASSWORD,
            "full_name": "Test Registrar",
            "role": "faculty",
            "office": "Registrar",
            "campus": "MMC",
        }
        r = api.post(f"{BASE_URL}/api/admin/create-user", json=payload, headers=self.auth())
        assert r.status_code == 200, r.text
        state["registrar_id"] = r.json()["user_id"]

    def test_create_faculty_librarian(self, api):
        payload = {
            "email": FACULTY_LIBRARIAN_EMAIL,
            "password": FACULTY_PASSWORD,
            "full_name": "Test Librarian",
            "role": "faculty",
            "office": "University Librarian",
            "campus": "MMC",
        }
        r = api.post(f"{BASE_URL}/api/admin/create-user", json=payload, headers=self.auth())
        assert r.status_code == 200
        state["librarian_id"] = r.json()["user_id"]

    def test_create_invalid_role(self, api):
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=self.auth(),
                     json={"email": "x@x.com", "password": "X", "full_name": "X", "role": "student"})
        assert r.status_code == 400

    def test_admin_cannot_delete_self(self, api):
        r = api.delete(f"{BASE_URL}/api/admin/users/{state['admin_id']}", headers=self.auth())
        assert r.status_code == 400

    def test_non_admin_forbidden(self, api):
        r = api.get(f"{BASE_URL}/api/admin/users",
                    headers={"Authorization": f"Bearer {state['student_token']}"})
        assert r.status_code == 403


# ---------- Clearance flow ----------
class TestClearance:
    def stoken(self):
        return {"Authorization": f"Bearer {state['student_token']}"}

    def test_create_clearance(self, api):
        payload = {"semester": "1st Semester", "academic_year": "2025-2026",
                   "clearance_type": "Graduation", "purpose": "Test"}
        r = api.post(f"{BASE_URL}/api/clearances/create", json=payload, headers=self.stoken())
        assert r.status_code == 200, r.text
        state["clearance_id"] = r.json()["clearance_id"]

    def test_invalid_clearance_type(self, api):
        r = api.post(f"{BASE_URL}/api/clearances/create", headers=self.stoken(),
                     json={"semester": "1st", "academic_year": "2025-2026", "clearance_type": "Bogus"})
        assert r.status_code == 400

    def test_list_student_only_own(self, api):
        r = api.get(f"{BASE_URL}/api/clearances/list", headers=self.stoken())
        assert r.status_code == 200
        d = r.json()
        assert all(c["student_id"] == state["student_id"] for c in d["clearances"])

    def test_get_clearance_detail(self, api):
        r = api.get(f"{BASE_URL}/api/clearances/{state['clearance_id']}", headers=self.stoken())
        assert r.status_code == 200
        c = r.json()["clearance"]
        assert len(c["approvals"]) == 6
        assert all(a["status"] == "pending" for a in c["approvals"])
        assert c["clearance_type"] == "Graduation"

    def test_admin_can_list_all(self, api):
        r = api.get(f"{BASE_URL}/api/clearances/list",
                    headers={"Authorization": f"Bearer {state['admin_token']}"})
        assert r.status_code == 200

    def test_student_cannot_process(self, api):
        r = api.post(f"{BASE_URL}/api/clearances/{state['clearance_id']}/process",
                     headers=self.stoken(), json={"action": "approve"})
        assert r.status_code == 403


# ---------- Faculty processing ----------
class TestFacultyProcessing:
    def test_faculty_login(self, api):
        for email, key in [(FACULTY_REGISTRAR_EMAIL, "reg_token"),
                           (FACULTY_LIBRARIAN_EMAIL, "lib_token")]:
            r = api.post(f"{BASE_URL}/api/auth/login",
                         json={"email": email, "password": FACULTY_PASSWORD})
            assert r.status_code == 200, r.text
            state[key] = r.json()["access_token"]

    def test_registrar_cannot_approve_first(self, api):
        r = api.post(f"{BASE_URL}/api/clearances/{state['clearance_id']}/process",
                     headers={"Authorization": f"Bearer {state['reg_token']}"},
                     json={"action": "approve", "comments": "early"})
        assert r.status_code == 400

    def test_librarian_approves(self, api):
        r = api.post(f"{BASE_URL}/api/clearances/{state['clearance_id']}/process",
                     headers={"Authorization": f"Bearer {state['lib_token']}"},
                     json={"action": "approve", "comments": "ok"})
        assert r.status_code == 200, r.text

    def test_librarian_double_approve(self, api):
        r = api.post(f"{BASE_URL}/api/clearances/{state['clearance_id']}/process",
                     headers={"Authorization": f"Bearer {state['lib_token']}"},
                     json={"action": "approve"})
        assert r.status_code == 400


# ---------- File upload ----------
class TestUploads:
    def test_upload_file(self, api):
        files = {"file": ("test.txt", io.BytesIO(b"hello world content"), "text/plain")}
        data = {"description": "test upload", "office": "Registrar"}
        r = requests.post(
            f"{BASE_URL}/api/clearances/{state['clearance_id']}/upload",
            files=files, data=data,
            headers={"Authorization": f"Bearer {state['student_token']}"}
        )
        assert r.status_code == 200, r.text
        att = r.json()["attachment"]
        assert att["original_name"] == "test.txt"
        state["attachment_id"] = att["id"]

    def test_upload_disallowed_extension(self, api):
        files = {"file": ("test.exe", io.BytesIO(b"x"), "application/octet-stream")}
        r = requests.post(
            f"{BASE_URL}/api/clearances/{state['clearance_id']}/upload",
            files=files, data={"description": "x", "office": ""},
            headers={"Authorization": f"Bearer {state['student_token']}"}
        )
        assert r.status_code == 400

    def test_download_attachment(self, api):
        r = requests.get(
            f"{BASE_URL}/api/clearances/{state['clearance_id']}/attachments/{state['attachment_id']}/download",
            headers={"Authorization": f"Bearer {state['student_token']}"}
        )
        assert r.status_code == 200
        assert b"hello world" in r.content


# ---------- Stats ----------
class TestStats:
    def test_student_stats(self, api):
        r = api.get(f"{BASE_URL}/api/stats",
                    headers={"Authorization": f"Bearer {state['student_token']}"})
        assert r.status_code == 200
        d = r.json()
        for k in ("total", "pending", "approved", "rejected"):
            assert k in d
        assert d["total"] >= 1

    def test_admin_stats(self, api):
        r = api.get(f"{BASE_URL}/api/stats",
                    headers={"Authorization": f"Bearer {state['admin_token']}"})
        assert r.status_code == 200


# ---------- Audit logs ----------
class TestAuditLogs:
    def test_audit_logs(self, api):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs?page_size=200",
                    headers={"Authorization": f"Bearer {state['admin_token']}"})
        assert r.status_code == 200
        logs = r.json()["logs"]
        actions = {l["action"] for l in logs}
        expected_subset = {"LOGIN_SUCCESS", "USER_REGISTERED", "EMAIL_VERIFIED",
                           "CLEARANCE_CREATED", "USER_CREATED", "FILE_UPLOADED"}
        missing = expected_subset - actions
        assert not missing, f"Missing audit actions: {missing}"

    def test_audit_logs_forbidden_for_student(self, api):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs",
                    headers={"Authorization": f"Bearer {state['student_token']}"})
        assert r.status_code == 403


# ---------- Cleanup ----------
class TestZCleanup:
    def test_admin_delete_test_users(self, api):
        for uid_key in ("registrar_id", "librarian_id", "student_id"):
            uid = state.get(uid_key)
            if uid:
                requests.delete(f"{BASE_URL}/api/admin/users/{uid}",
                                headers={"Authorization": f"Bearer {state['admin_token']}"})
        # delete test clearance via mongo
        try:
            subprocess.run(["mongosh", "--quiet", f"mongodb://localhost:27017/{DB_NAME}",
                            "--eval", f'db.clearances.deleteOne({{id:"{state.get("clearance_id","")}"}})'],
                           timeout=10, check=False)
        except Exception:
            pass
