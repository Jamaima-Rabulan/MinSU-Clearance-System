"""
MinSU Clearance System - Iteration 2 backend tests.
Focus on NEW functionality:
  - Tightened CORS (allow only known origins)
  - Password complexity on register / admin/create-user / reset-password
  - Faculty seeding for all 6 offices (login + admin/users listing)
  - Bulk approval (approve/reject/registrar gating)
  - Cursor pagination on /api/admin/audit-logs
  - Authorization checks remain intact
  - End-to-end happy path still works
"""
import os
import uuid
import json
import subprocess
import time
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://clearance-hub-18.preview.emergentagent.com').rstrip('/')
DB_NAME = os.environ.get('DB_NAME', 'minsu_clearance')

ADMIN_EMAIL = "admin@minsu.edu.ph"
ADMIN_PASSWORD = "Admin@123"
FACULTY_PASSWORD = "Faculty@2026"

OFFICE_TO_EMAIL = {
    "University Librarian": "universitylibrarian@minsu.edu.ph",
    "Guidance Counselor": "guidancecounselor@minsu.edu.ph",
    "SAS Director/Coordinator": "sasdirector_coordinator@minsu.edu.ph",
    "Student Affairs/Finance": "studentaffairs_finance@minsu.edu.ph",
    "College Dean/Program Chair": "collegedean_programchair@minsu.edu.ph",
    "Registrar": "registrar@minsu.edu.ph",
}

RUN_ID = uuid.uuid4().hex[:6]
STUDENT_EMAIL = f"it2_student_{RUN_ID}@minsu.edu.ph"
STUDENT_PASSWORD = "Student@123"

state = {}


def mongo_get_verification_code(email: str) -> str:
    cmd = ["mongosh", "--quiet", f"mongodb://localhost:27017/{DB_NAME}",
           "--eval", f'JSON.stringify(db.users.findOne({{email: "{email}"}}, {{verification_code:1, _id:0}}))']
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


@pytest.fixture(scope="session")
def admin_token(api):
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


# ============ CORS (application level — direct to uvicorn) ============
# NOTE: The kubernetes/cloudflare ingress layer adds its own permissive
# Access-Control-Allow-Origin: * header in front of the app, which we cannot
# control from the backend. We therefore validate the FastAPI CORSMiddleware
# behaviour by hitting uvicorn directly on localhost:8001.
APP_DIRECT = "http://localhost:8001"


class TestCORS:
    def test_disallowed_origin_no_acao(self, api):
        """Request from evil.com should NOT get an Access-Control-Allow-Origin header from the app."""
        r = api.get(f"{APP_DIRECT}/api/", headers={"Origin": "https://evil.com"})
        assert r.status_code == 200
        acao = r.headers.get("Access-Control-Allow-Origin", "") or r.headers.get("access-control-allow-origin", "")
        assert acao == "", f"App leaked ACAO for disallowed origin: {acao!r}"

    def test_allowed_origin_localhost(self, api):
        r = api.get(f"{APP_DIRECT}/api/", headers={"Origin": "http://localhost:3000"})
        assert r.status_code == 200
        acao = r.headers.get("Access-Control-Allow-Origin", "") or r.headers.get("access-control-allow-origin", "")
        assert acao == "http://localhost:3000", f"Expected localhost:3000 echo, got: {acao!r}"


# ============ Password complexity ============
WEAK_CASES = [
    ("Sh0rt", "at least 8"),         # too short
    ("alllower1", "uppercase"),       # missing uppercase
    ("ALLUPPER1", "lowercase"),       # missing lowercase
    ("NoDigitsHere", "digit"),        # missing digit
]


class TestPasswordComplexityRegister:
    @pytest.mark.parametrize("password,expected_substr", WEAK_CASES)
    def test_register_weak_password(self, api, password, expected_substr):
        email = f"it2_weak_{uuid.uuid4().hex[:6]}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/auth/register", json={
            "email": email, "password": password, "full_name": "Weak PW",
            "role": "student", "student_id": "2025-99999",
            "course": "BSCS", "year_level": "1st Year", "section": "F1",
            "campus": "MMC", "college": "CCS"
        })
        assert r.status_code == 400, f"Expected 400 for weak pw {password!r}, got {r.status_code}: {r.text}"
        d = r.json()
        assert "detail" in d
        assert expected_substr.lower() in d["detail"].lower(), \
            f"Detail should mention {expected_substr!r}, got: {d['detail']!r}"


class TestPasswordComplexityAdminCreate:
    @pytest.mark.parametrize("password,expected_substr", WEAK_CASES)
    def test_admin_create_weak_password(self, api, admin_headers, password, expected_substr):
        email = f"it2_admweak_{uuid.uuid4().hex[:6]}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": password, "full_name": "Weak Faculty",
            "role": "faculty", "office": "University Librarian"
        })
        assert r.status_code == 400, f"Expected 400 for weak pw {password!r}, got {r.status_code}: {r.text}"
        d = r.json()
        assert expected_substr.lower() in d["detail"].lower()

    def test_admin_create_strong_password_succeeds(self, api, admin_headers):
        email = f"it2_strong_{uuid.uuid4().hex[:6]}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "Strong@2026", "full_name": "Strong Faculty",
            "role": "faculty", "office": "University Librarian"
        })
        assert r.status_code == 200, r.text
        state.setdefault("cleanup_user_ids", []).append(r.json()["user_id"])


class TestPasswordComplexityResetPassword:
    """Reset password also enforces password complexity."""
    @pytest.fixture(scope="class")
    def reset_user(self, api, admin_headers):
        email = f"it2_reset_{uuid.uuid4().hex[:6]}@minsu.edu.ph"
        r = api.post(f"{BASE_URL}/api/admin/create-user", headers=admin_headers, json={
            "email": email, "password": "Initial@2026", "full_name": "Reset Test",
            "role": "faculty", "office": "Guidance Counselor"
        })
        assert r.status_code == 200, r.text
        uid = r.json()["user_id"]

        # Trigger forgot-password to mint a reset_code
        r = api.post(f"{BASE_URL}/api/auth/forgot-password", json={"email": email})
        assert r.status_code == 200
        # Read code from Mongo (SendGrid sender unverified, dev_code may be null)
        cmd = ["mongosh", "--quiet", f"mongodb://localhost:27017/{DB_NAME}",
               "--eval", f'JSON.stringify(db.users.findOne({{email: "{email}"}}, {{reset_code:1, _id:0}}))']
        out = subprocess.check_output(cmd, timeout=10).decode().strip()
        code = json.loads(out).get("reset_code", "")
        assert code, f"reset_code not found for {email}"
        yield {"email": email, "code": code, "id": uid}
        # cleanup
        state.setdefault("cleanup_user_ids", []).append(uid)

    @pytest.mark.parametrize("password,expected_substr", WEAK_CASES)
    def test_reset_weak_password(self, api, reset_user, password, expected_substr):
        r = api.post(f"{BASE_URL}/api/auth/reset-password", json={
            "email": reset_user["email"], "code": reset_user["code"], "new_password": password
        })
        assert r.status_code == 400, r.text
        assert expected_substr.lower() in r.json()["detail"].lower()


# ============ Faculty seeding ============
class TestFacultySeeding:
    def test_admin_users_lists_all_six_seeded_faculty(self, api, admin_headers):
        # Page through admin users to find all faculty emails
        seen = {}
        for page in range(1, 6):
            r = api.get(f"{BASE_URL}/api/admin/users?page={page}&page_size=100", headers=admin_headers)
            assert r.status_code == 200
            users = r.json().get("users", [])
            for u in users:
                if u.get("email") in OFFICE_TO_EMAIL.values():
                    seen[u["email"]] = u
            if len(users) < 100:
                break
        for office, email in OFFICE_TO_EMAIL.items():
            assert email in seen, f"Missing seeded faculty {email}"
            u = seen[email]
            assert u.get("role") == "faculty", f"{email} role={u.get('role')}"
            assert u.get("office") == office, f"{email} office={u.get('office')} expected {office}"
            assert u.get("email_verified") is True, f"{email} not verified"

    @pytest.mark.parametrize("office,email", list(OFFICE_TO_EMAIL.items()))
    def test_seeded_faculty_can_login(self, api, office, email):
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": email, "password": FACULTY_PASSWORD})
        assert r.status_code == 200, f"Login failed for {email}: {r.text}"
        d = r.json()
        assert d["user"]["role"] == "faculty"
        assert d["user"]["office"] == office
        # Stash librarian + registrar tokens for bulk tests
        if office == "University Librarian":
            state["librarian_token"] = d["access_token"]
        if office == "Registrar":
            state["registrar_token"] = d["access_token"]


# ============ Bulk approval setup: create student + 3 clearances ============
@pytest.fixture(scope="session")
def student_with_clearances(api, admin_headers):
    """Register student, verify, login, create 3 clearances. Returns (token, [cids])."""
    # Register
    r = api.post(f"{BASE_URL}/api/auth/register", json={
        "email": STUDENT_EMAIL, "password": STUDENT_PASSWORD,
        "full_name": "It2 Student", "role": "student", "student_id": f"2025-IT2{RUN_ID}",
        "course": "BSCS", "year_level": "1st Year", "section": "F1",
        "campus": "MMC", "college": "CCS"
    })
    assert r.status_code == 200, r.text
    code = r.json().get("dev_code") or mongo_get_verification_code(STUDENT_EMAIL)
    assert code, "no verification code"
    r = api.post(f"{BASE_URL}/api/auth/verify-email", json={"email": STUDENT_EMAIL, "code": code})
    assert r.status_code == 200, r.text
    r = api.post(f"{BASE_URL}/api/auth/login",
                 json={"email": STUDENT_EMAIL, "password": STUDENT_PASSWORD})
    assert r.status_code == 200
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    cids = []
    for i in range(3):
        r = api.post(f"{BASE_URL}/api/clearances/create", headers=headers, json={
            "semester": "1st", "academic_year": "2025-2026",
            "clearance_type": "End of Semester", "purpose": f"bulk-test-{i}"
        })
        assert r.status_code == 200, r.text
        cids.append(r.json()["clearance_id"])
    state["student_token"] = token
    state["student_cids"] = cids
    return token, cids


# ============ Bulk approval ============
class TestBulkApprove:
    def test_bulk_approve_mixed_valid_and_already_processed(self, api, student_with_clearances):
        token, cids = student_with_clearances
        # Login librarian fresh
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": OFFICE_TO_EMAIL["University Librarian"], "password": FACULTY_PASSWORD})
        assert r.status_code == 200
        lib_headers = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

        # First call: approve cid[0] and cid[1]
        r = api.post(f"{BASE_URL}/api/clearances/bulk-process", headers=lib_headers, json={
            "clearance_ids": [cids[0], cids[1]], "action": "approve", "comments": "ok"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["summary"]["total"] == 2
        assert d["summary"]["processed"] == 2
        assert d["summary"]["skipped"] == 0
        assert d["summary"]["fully_approved"] == 0  # only librarian approved, 5 offices left

        # Second call: include cid[0] (already processed) + cid[2] (new) + bogus
        bogus_id = str(uuid.uuid4())
        r = api.post(f"{BASE_URL}/api/clearances/bulk-process", headers=lib_headers, json={
            "clearance_ids": [cids[0], cids[2], bogus_id], "action": "approve"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["summary"]["total"] == 3
        assert d["summary"]["processed"] == 1
        assert d["summary"]["skipped"] == 2
        skipped_reasons = {s["id"]: s["reason"] for s in d["results"]["skipped"]}
        assert skipped_reasons.get(cids[0]) == "already_processed"
        assert skipped_reasons.get(bogus_id) == "not_found"


class TestBulkRegistrarGating:
    def test_registrar_bulk_blocked_when_others_pending(self, api, student_with_clearances):
        _, cids = student_with_clearances
        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": OFFICE_TO_EMAIL["Registrar"], "password": FACULTY_PASSWORD})
        assert r.status_code == 200
        reg_headers = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}

        r = api.post(f"{BASE_URL}/api/clearances/bulk-process", headers=reg_headers, json={
            "clearance_ids": cids, "action": "approve"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        # All cids should be skipped with reason others_pending:N
        assert d["summary"]["processed"] == 0
        assert d["summary"]["skipped"] == len(cids)
        for s in d["results"]["skipped"]:
            assert s["reason"].startswith("others_pending:"), f"reason={s['reason']}"


class TestBulkReject:
    def test_bulk_reject(self, api, admin_headers):
        # Create an isolated student + 1 clearance, then reject as librarian
        rid = uuid.uuid4().hex[:6]
        em = f"it2_rej_{rid}@minsu.edu.ph"
        api.post(f"{BASE_URL}/api/auth/register", json={
            "email": em, "password": "Student@123", "full_name": "Rej",
            "role": "student", "student_id": f"2025-RJ{rid}",
            "course": "BSCS", "year_level": "1st Year", "section": "F1",
            "campus": "MMC", "college": "CCS"
        })
        code = mongo_get_verification_code(em)
        api.post(f"{BASE_URL}/api/auth/verify-email", json={"email": em, "code": code})
        r = api.post(f"{BASE_URL}/api/auth/login", json={"email": em, "password": "Student@123"})
        stoken = r.json()["access_token"]
        sh = {"Authorization": f"Bearer {stoken}", "Content-Type": "application/json"}
        r = api.post(f"{BASE_URL}/api/clearances/create", headers=sh, json={
            "semester": "1st", "academic_year": "2025-2026", "clearance_type": "End of Semester"
        })
        cid = r.json()["clearance_id"]

        r = api.post(f"{BASE_URL}/api/auth/login",
                     json={"email": OFFICE_TO_EMAIL["University Librarian"], "password": FACULTY_PASSWORD})
        lh = {"Authorization": f"Bearer {r.json()['access_token']}", "Content-Type": "application/json"}
        r = api.post(f"{BASE_URL}/api/clearances/bulk-process", headers=lh, json={
            "clearance_ids": [cid], "action": "reject", "comments": "missing book return"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["summary"]["processed"] == 1
        # Verify clearance is now rejected
        r = api.get(f"{BASE_URL}/api/clearances/{cid}", headers=sh)
        assert r.status_code == 200
        assert r.json()["clearance"]["overall_status"] == "rejected"


# ============ Cursor pagination ============
class TestAuditCursor:
    def test_legacy_page_response(self, api, admin_headers):
        r = api.get(f"{BASE_URL}/api/admin/audit-logs?page=1&page_size=20", headers=admin_headers)
        assert r.status_code == 200
        d = r.json()
        assert d.get("mode") == "page"
        assert "pagination" in d
        assert isinstance(d["logs"], list)

    def test_cursor_response_and_descending(self, api, admin_headers):
        # Get latest logs and pick first.timestamp as cursor
        r = api.get(f"{BASE_URL}/api/admin/audit-logs?page_size=10", headers=admin_headers)
        logs = r.json()["logs"]
        if len(logs) < 2:
            pytest.skip("not enough audit logs")
        cursor = logs[0]["timestamp"]
        r = api.get(f"{BASE_URL}/api/admin/audit-logs?cursor={cursor}&page_size=5", headers=admin_headers)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mode") == "cursor"
        assert "pagination" not in d
        assert "has_next" in d
        assert "cursor" in d
        ts_list = [x["timestamp"] for x in d["logs"]]
        # All timestamps strictly less than cursor
        for ts in ts_list:
            assert ts < cursor, f"{ts} not < {cursor}"
        # Sorted descending
        assert ts_list == sorted(ts_list, reverse=True)


# ============ Authorization ============
class TestAuthZ:
    def test_non_admin_cannot_access_admin_users(self, api, student_with_clearances):
        token, _ = student_with_clearances
        r = api.get(f"{BASE_URL}/api/admin/users",
                    headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_non_admin_cannot_access_audit_logs(self, api, student_with_clearances):
        token, _ = student_with_clearances
        r = api.get(f"{BASE_URL}/api/admin/audit-logs",
                    headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403

    def test_non_faculty_cannot_bulk_process(self, api, student_with_clearances):
        token, cids = student_with_clearances
        r = api.post(f"{BASE_URL}/api/clearances/bulk-process",
                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                     json={"clearance_ids": cids, "action": "approve"})
        assert r.status_code == 403

    def test_admin_cannot_bulk_process(self, api, admin_headers):
        r = api.post(f"{BASE_URL}/api/clearances/bulk-process", headers=admin_headers,
                     json={"clearance_ids": ["x"], "action": "approve"})
        assert r.status_code == 403


# ============ Cleanup ============
class TestZCleanup:
    def test_cleanup(self, api, admin_headers):
        # Find and delete test students
        for em in [STUDENT_EMAIL]:
            cmd = ["mongosh", "--quiet", f"mongodb://localhost:27017/{DB_NAME}",
                   "--eval", f'db.users.deleteOne({{email: "{em}"}})']
            try:
                subprocess.check_output(cmd, timeout=10)
            except Exception:
                pass
        # Delete users created via admin/create-user
        for uid in state.get("cleanup_user_ids", []):
            api.delete(f"{BASE_URL}/api/admin/users/{uid}", headers=admin_headers)
        # Delete test clearances + reject test student
        cmd = ["mongosh", "--quiet", f"mongodb://localhost:27017/{DB_NAME}",
               "--eval", 'db.clearances.deleteMany({purpose: /bulk-test-/}); db.users.deleteMany({email: /^it2_/});']
        try:
            subprocess.check_output(cmd, timeout=10)
        except Exception:
            pass
        assert True
