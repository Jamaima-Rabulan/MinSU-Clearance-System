from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel, Field, EmailStr, field_validator, model_validator
from typing import List, Optional
import uuid
import re
from datetime import datetime, timezone, timedelta
import hashlib
import bcrypt

# ================= MongoDB connection =================
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# ================= App =================
app = FastAPI(title="MinSU Clearance System")
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ================= Global validation error handler =================
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return the first human-friendly validation message as `detail`."""
    errors = exc.errors()
    if errors:
        first = errors[0]
        msg = first.get("msg", "Invalid input")
        # Strip pydantic's "Value error, " prefix
        if msg.lower().startswith("value error, "):
            msg = msg[len("Value error, "):]
        loc = ".".join(str(p) for p in first.get("loc", []) if p not in ("body",))
        detail = f"{loc}: {msg}" if loc and loc not in msg.lower() else msg
    else:
        detail = "Invalid input"
    return JSONResponse(status_code=422, content={"detail": detail})

# ================= Constants =================
OFFICES = [
    'University Librarian',
    'Guidance Counselor',
    'SAS Director/Coordinator',
    'Student Affairs/Finance',
    'College Dean/Program Chair',
    'Registrar',
]
CAMPUSES = ['MMC', 'MBC', 'MCC']
COLLEGES = ['CAAF', 'CAS', 'CBM', 'CCS', 'CCJE', 'CTE', 'IABE', 'IF']
COURSES = [
    'BSIT', 'BSIS', 'BSBio', 'BSMath', 'BAPolSci', 'ABEnglish', 'BSPsych',
    'BSED', 'BEED', 'BPEd', 'BTLEd', 'BSNEd',
    'BSBA', 'BSOA', 'BSA', 'BSMA',
    'BSCrim',
    'BSCS', 'BSEMC', 'ACT',
    'BSA-Crop Science', 'BSA-Animal Science', 'BSF', 'BSFi',
    'BSEntrep', 'BSHRM', 'BSTM', 'BSHM',
    'BSFisheries', 'BFT',
    'BSCPE', 'BSEE', 'BSCE', 'BSME',
]
YEAR_LEVELS = ['1st Year', '2nd Year', '3rd Year', '4th Year']
SECTIONS = ['F1', 'F2', 'F3']

# ================= Validation constants =================
VALID_ROLES = {"student", "faculty", "admin"}
VALID_SEMESTERS = {"1st Semester", "2nd Semester", "Summer"}
VALID_ACTIONS = {"approve", "reject"}
PASSWORD_MIN_LEN = 8
STUDENT_ID_RE = re.compile(r"^[A-Za-z0-9\-]{4,20}$")
ACADEMIC_YEAR_RE = re.compile(r"^\d{4}-\d{4}$")
FULL_NAME_MIN_LEN = 3
FULL_NAME_MAX_LEN = 120
COMMENTS_MAX_LEN = 500


def _validate_strong_password(pw: str) -> str:
    if not pw or len(pw) < PASSWORD_MIN_LEN:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LEN} characters long")
    if len(pw) > 128:
        raise ValueError("Password is too long (max 128 characters)")
    if not re.search(r"[A-Za-z]", pw):
        raise ValueError("Password must contain at least one letter")
    if not re.search(r"\d", pw):
        raise ValueError("Password must contain at least one number")
    return pw


# ================= Models =================
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: str = "student"
    student_id: Optional[str] = None
    office: Optional[str] = None
    course: Optional[str] = None
    year_level: Optional[str] = None
    section: Optional[str] = None
    campus: Optional[str] = None
    college: Optional[str] = None

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        return _validate_strong_password(v)

    @field_validator("full_name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < FULL_NAME_MIN_LEN:
            raise ValueError(f"Full name must be at least {FULL_NAME_MIN_LEN} characters")
        if len(v) > FULL_NAME_MAX_LEN:
            raise ValueError(f"Full name is too long (max {FULL_NAME_MAX_LEN})")
        if not re.match(r"^[A-Za-zÀ-ÿ .,'\-]+$", v):
            raise ValueError("Full name contains invalid characters")
        return v

    @field_validator("role")
    @classmethod
    def _role_ok(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Role must be one of {sorted(VALID_ROLES)}")
        return v

    @model_validator(mode="after")
    def _role_specific(self):
        if self.role == "student":
            if not self.student_id or not STUDENT_ID_RE.match(self.student_id):
                raise ValueError("Valid Student ID is required (4-20 chars, letters/digits/dashes)")
            if not self.course or self.course not in COURSES:
                raise ValueError("A valid Course is required for students")
            if not self.year_level or self.year_level not in YEAR_LEVELS:
                raise ValueError("A valid Year Level is required for students")
            if not self.section or self.section not in SECTIONS:
                raise ValueError("A valid Section is required for students")
            if self.campus and self.campus not in CAMPUSES:
                raise ValueError("Invalid Campus")
            if self.college and self.college not in COLLEGES:
                raise ValueError("Invalid College")
        elif self.role == "faculty":
            if not self.office or self.office not in OFFICES:
                raise ValueError("A valid Office is required for faculty")
        return self


class UserLogin(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def _password_present(cls, v: str) -> str:
        if not v or len(v) < 1:
            raise ValueError("Password is required")
        if len(v) > 128:
            raise ValueError("Password is too long")
        return v


class ClearanceCreate(BaseModel):
    semester: str
    academic_year: str

    @field_validator("semester")
    @classmethod
    def _sem_ok(cls, v: str) -> str:
        if v not in VALID_SEMESTERS:
            raise ValueError(f"Semester must be one of {sorted(VALID_SEMESTERS)}")
        return v

    @field_validator("academic_year")
    @classmethod
    def _ay_ok(cls, v: str) -> str:
        if not ACADEMIC_YEAR_RE.match(v or ""):
            raise ValueError("Academic year must be in the format YYYY-YYYY (e.g., 2025-2026)")
        start, end = v.split("-")
        if int(end) != int(start) + 1:
            raise ValueError("Academic year end must be one year after start")
        return v


class ClearanceProcess(BaseModel):
    action: str
    comments: Optional[str] = None
    signature_data: Optional[str] = None

    @field_validator("action")
    @classmethod
    def _action_ok(cls, v: str) -> str:
        if v not in VALID_ACTIONS:
            raise ValueError(f"Action must be one of {sorted(VALID_ACTIONS)}")
        return v

    @field_validator("comments")
    @classmethod
    def _comments_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) > COMMENTS_MAX_LEN:
            raise ValueError(f"Comments must be at most {COMMENTS_MAX_LEN} characters")
        return v or None

    @model_validator(mode="after")
    def _rules(self):
        if self.action == "reject":
            if not (self.comments and self.comments.strip()):
                raise ValueError("Rejection reason (comments) is required when rejecting a clearance")
        if self.action == "approve":
            if not self.signature_data or not self.signature_data.startswith("data:image/"):
                raise ValueError("A valid e-signature (PNG data URL) is required to approve")
            if len(self.signature_data) > 2_000_000:
                raise ValueError("Signature image is too large")
        return self

# ================= Helpers =================
def generate_uuid() -> str:
    return str(uuid.uuid4())

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    """Verify password. Supports bcrypt (new) and legacy sha256 hashes."""
    if not hashed:
        return False
    # bcrypt hashes always start with $2a$, $2b$, or $2y$
    if hashed.startswith("$2"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception:
            return False
    # Legacy sha256 fallback - allows migration for pre-existing accounts
    return hashlib.sha256(password.encode()).hexdigest() == hashed

async def migrate_to_bcrypt(user_id: str, plain_password: str) -> None:
    """Silently upgrade legacy sha256 password to bcrypt on successful login."""
    new_hash = hash_password(plain_password)
    await db.users.update_one({"id": user_id}, {"$set": {"password_hash": new_hash}})

def generate_approval_code() -> str:
    import random
    import string
    timestamp = datetime.now(timezone.utc).strftime("%y%m%d")
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"CLR-{timestamp}-{random_part}"

def get_client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "-"
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "-"

async def write_audit(
    *,
    actor_id: Optional[str],
    actor_email: Optional[str],
    actor_role: Optional[str],
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    status: str = "success",
    details: Optional[dict] = None,
    request: Optional[Request] = None,
) -> None:
    """Persist an audit log entry."""
    doc = {
        "id": generate_uuid(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor_id": actor_id,
        "actor_email": actor_email,
        "actor_role": actor_role,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "status": status,
        "details": details or {},
        "ip_address": get_client_ip(request),
        "user_agent": request.headers.get("user-agent", "-") if request else "-",
    }
    try:
        await db.audit_logs.insert_one(doc)
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")

def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "student_id": user.get("student_id"),
        "office": user.get("office"),
        "course": user.get("course"),
        "year_level": user.get("year_level"),
        "section": user.get("section"),
        "campus": user.get("campus"),
        "college": user.get("college"),
        "email_verified": user.get("email_verified", True),
    }

# ================= Auth =================
@api_router.post("/auth/register")
async def register(user_data: UserCreate, request: Request):
    existing = await db.users.find_one({"email": user_data.email.lower()})
    if existing:
        await write_audit(
            actor_id=None, actor_email=user_data.email, actor_role=user_data.role,
            action="user.register", resource_type="user", status="failure",
            details={"reason": "email_already_registered"}, request=request,
        )
        raise HTTPException(status_code=400, detail="Email already registered")

    # Role-specific field validation is enforced by Pydantic model_validator on UserCreate.

    user_id = generate_uuid()
    user_doc = {
        "id": user_id,
        "email": user_data.email.lower(),
        "password_hash": hash_password(user_data.password),
        "full_name": user_data.full_name,
        "role": user_data.role,
        "student_id": user_data.student_id,
        "office": user_data.office,
        "course": user_data.course,
        "year_level": user_data.year_level,
        "section": user_data.section,
        "campus": user_data.campus,
        "college": user_data.college,
        "email_verified": True,  # Auto-verified (no email service wired)
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user_doc)

    await write_audit(
        actor_id=user_id, actor_email=user_doc["email"], actor_role=user_doc["role"],
        action="user.register", resource_type="user", resource_id=user_id,
        status="success", details={"full_name": user_doc["full_name"]}, request=request,
    )

    return {"success": True, "user": public_user(user_doc), "message": "Registration successful!"}


# ================= Brute-force protection =================

BRUTEFORCE_MAX_FAILURES = 5      # threshold of failures within the window
BRUTEFORCE_WINDOW_MIN = 15       # rolling window (minutes) counted for triggering lockout
BRUTEFORCE_LOCKOUT_MIN = 15      # lockout duration (minutes) once threshold is exceeded
BRUTEFORCE_IP_MAX_FAILURES = 20  # per-IP secondary shield across all accounts


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _count_recent_failures(email: str, minutes: int) -> int:
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return await db.audit_logs.count_documents({
        "action": "user.login",
        "status": "failure",
        "actor_email": email,
        "timestamp": {"$gte": since},
    })


async def _count_recent_failures_by_ip(ip: str, minutes: int) -> int:
    if not ip or ip == "-":
        return 0
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    return await db.audit_logs.count_documents({
        "action": "user.login",
        "status": "failure",
        "ip_address": ip,
        "timestamp": {"$gte": since},
    })


async def _check_bruteforce(email: str, request: Request) -> None:
    """Raise 429 if the account or the source IP is currently locked out."""
    # Per-account lockout (persisted on user doc if we know the user)
    user = await db.users.find_one({"email": email}, {"lockout_until": 1})
    if user and user.get("lockout_until"):
        try:
            until = datetime.fromisoformat(user["lockout_until"])
        except ValueError:
            until = None
        if until and until > datetime.now(timezone.utc):
            remaining = int((until - datetime.now(timezone.utc)).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Too many failed attempts. Account is locked. "
                    f"Try again in {max(1, remaining // 60)} minute(s)."
                ),
            )

    # Per-IP secondary shield (protects against user enumeration)
    ip = get_client_ip(request)
    ip_fails = await _count_recent_failures_by_ip(ip, BRUTEFORCE_WINDOW_MIN)
    if ip_fails >= BRUTEFORCE_IP_MAX_FAILURES:
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts from this network. Please try again later.",
        )


async def _register_failure(email: str) -> Optional[str]:
    """Increment failure counter. Return lockout_until iso string if we just locked the account."""
    user = await db.users.find_one({"email": email}, {"id": 1})
    if not user:
        return None
    fails = await _count_recent_failures(email, BRUTEFORCE_WINDOW_MIN)
    # The current attempt's failure has already been written to audit_logs
    # before this helper runs, so `fails` already includes it.
    if fails >= BRUTEFORCE_MAX_FAILURES:
        lockout_until = (
            datetime.now(timezone.utc) + timedelta(minutes=BRUTEFORCE_LOCKOUT_MIN)
        ).isoformat()
        await db.users.update_one(
            {"email": email},
            {"$set": {"lockout_until": lockout_until, "last_lockout_at": _iso_now()}},
        )
        return lockout_until
    return None


async def _clear_failures(email: str) -> None:
    await db.users.update_one({"email": email}, {"$unset": {"lockout_until": ""}})


@api_router.post("/auth/login")
async def login(credentials: UserLogin, request: Request):
    email = credentials.email.lower()

    # 1. Enforce lockout FIRST (before any DB / hash work leaks timing info)
    await _check_bruteforce(email, request)

    user = await db.users.find_one({"email": email})
    if not user:
        await write_audit(
            actor_id=None, actor_email=email, actor_role=None,
            action="user.login", resource_type="user", status="failure",
            details={"reason": "user_not_found"}, request=request,
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(credentials.password, user["password_hash"]):
        await write_audit(
            actor_id=user["id"], actor_email=email, actor_role=user.get("role"),
            action="user.login", resource_type="user", resource_id=user["id"],
            status="failure", details={"reason": "invalid_password"}, request=request,
        )
        lockout = await _register_failure(email)
        if lockout:
            await write_audit(
                actor_id=user["id"], actor_email=email, actor_role=user.get("role"),
                action="user.locked", resource_type="user", resource_id=user["id"],
                status="failure",
                details={"lockout_until": lockout, "threshold": BRUTEFORCE_MAX_FAILURES},
                request=request,
            )
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Too many failed attempts. Account has been locked for "
                    f"{BRUTEFORCE_LOCKOUT_MIN} minutes."
                ),
            )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Successful login — clear counters + migrate legacy hash if needed
    await _clear_failures(email)
    if not user["password_hash"].startswith("$2"):
        await migrate_to_bcrypt(user["id"], credentials.password)

    await write_audit(
        actor_id=user["id"], actor_email=email, actor_role=user.get("role"),
        action="user.login", resource_type="user", resource_id=user["id"],
        status="success", request=request,
    )
    return {"success": True, "user": public_user(user)}


@api_router.post("/auth/logout")
async def logout(user_id: str, request: Request):
    user = await db.users.find_one({"id": user_id})
    await write_audit(
        actor_id=user_id,
        actor_email=user.get("email") if user else None,
        actor_role=user.get("role") if user else None,
        action="user.logout", resource_type="user", resource_id=user_id,
        status="success", request=request,
    )
    return {"success": True}


@api_router.get("/auth/user/{user_id}")
async def get_user(user_id: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return public_user(user)


# ================= Clearance =================
@api_router.post("/clearances/create")
async def create_clearance(data: ClearanceCreate, user_id: str, request: Request):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can create clearances")

    clearance_id = generate_uuid()
    approvals = [{
        "office": office,
        "status": "pending",
        "approved_by": None,
        "approved_by_name": None,
        "approved_at": None,
        "comments": None,
        "approval_code": None,
    } for office in OFFICES]

    clearance_doc = {
        "id": clearance_id,
        "student_id": user["id"],
        "student_name": user["full_name"],
        "student_email": user["email"],
        "student_number": user.get("student_id", ""),
        "course": user.get("course", ""),
        "year_level": user.get("year_level", ""),
        "section": user.get("section", ""),
        "campus": user.get("campus", ""),
        "college": user.get("college", ""),
        "semester": data.semester,
        "academic_year": data.academic_year,
        "overall_status": "pending",
        "approvals": approvals,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
    }
    await db.clearances.insert_one(clearance_doc)

    await write_audit(
        actor_id=user["id"], actor_email=user["email"], actor_role=user["role"],
        action="clearance.create", resource_type="clearance", resource_id=clearance_id,
        status="success",
        details={"semester": data.semester, "academic_year": data.academic_year},
        request=request,
    )
    return {"success": True, "clearance_id": clearance_id}


@api_router.get("/clearances/list")
async def list_clearances(
    user_id: str,
    course: Optional[str] = None,
    year_level: Optional[str] = None,
    section: Optional[str] = None,
    campus: Optional[str] = None,
    college: Optional[str] = None,
    status: Optional[str] = None,
):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query: dict = {}
    if user["role"] == "student":
        query["student_id"] = user["id"]
    elif user["role"] == "faculty":
        query["approvals"] = {
            "$elemMatch": {"office": user.get("office"), "status": "pending"}
        }
    if course:
        query["course"] = course
    if year_level:
        query["year_level"] = year_level
    if section:
        query["section"] = section
    if campus:
        query["campus"] = campus
    if college:
        query["college"] = college
    if status:
        query["overall_status"] = status

    clearances = await db.clearances.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return {"clearances": clearances}


@api_router.get("/clearances/{clearance_id}")
async def get_clearance(clearance_id: str, user_id: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    clearance = await db.clearances.find_one({"id": clearance_id}, {"_id": 0})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    if user["role"] == "student" and clearance["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"clearance": clearance}


@api_router.post("/clearances/{clearance_id}/process")
async def process_clearance(clearance_id: str, data: ClearanceProcess, user_id: str, request: Request):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["role"] != "faculty":
        raise HTTPException(status_code=403, detail="Only faculty can process clearances")

    clearance = await db.clearances.find_one({"id": clearance_id})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    office = user.get("office")
    if not office:
        raise HTTPException(status_code=400, detail="Faculty must have an assigned office")

    approvals = clearance.get("approvals", [])

    # Registrar gate
    if office == "Registrar":
        non_registrar = [a for a in approvals if a["office"] != "Registrar"]
        pending_count = sum(1 for a in non_registrar if a["status"] == "pending")
        if pending_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Registrar can only approve after all other offices. {pending_count} office(s) still pending.",
            )

    approval_found = False
    for approval in approvals:
        if approval["office"] == office:
            if approval["status"] != "pending":
                raise HTTPException(status_code=400, detail="This clearance has already been processed by your office")
            approval["status"] = "approved" if data.action == "approve" else "rejected"
            approval["approved_by"] = user["id"]
            approval["approved_by_name"] = user["full_name"]
            approval["approved_at"] = datetime.now(timezone.utc).isoformat()
            approval["comments"] = data.comments
            approval["approval_code"] = generate_approval_code()
            approval_found = True
            break

    if not approval_found:
        raise HTTPException(status_code=400, detail="No pending approval found for your office")

    overall_status = "pending"
    if data.action == "reject":
        overall_status = "rejected"
    else:
        if all(a["status"] == "approved" for a in approvals):
            overall_status = "approved"

    completed_at = None
    if overall_status in ["approved", "rejected"]:
        completed_at = datetime.now(timezone.utc).isoformat()

    await db.clearances.update_one(
        {"id": clearance_id},
        {"$set": {
            "approvals": approvals,
            "overall_status": overall_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": completed_at,
        }},
    )

    await write_audit(
        actor_id=user["id"], actor_email=user["email"], actor_role="faculty",
        action=f"clearance.{data.action}", resource_type="clearance", resource_id=clearance_id,
        status="success",
        details={
            "office": office,
            "student_id": clearance.get("student_id"),
            "student_name": clearance.get("student_name"),
            "overall_status": overall_status,
            "comments": data.comments,
        },
        request=request,
    )

    return {"success": True, "message": f"Clearance {data.action}d successfully"}


# ================= Stats =================
@api_router.get("/stats")
async def get_stats(user_id: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = user["role"]
    if role == "student":
        base = {"student_id": user["id"]}
        total = await db.clearances.count_documents(base)
        pending = await db.clearances.count_documents({**base, "overall_status": "pending"})
        approved = await db.clearances.count_documents({**base, "overall_status": "approved"})
        rejected = await db.clearances.count_documents({**base, "overall_status": "rejected"})
    elif role == "faculty":
        office = user.get("office")
        total = await db.clearances.count_documents({"approvals": {"$elemMatch": {"office": office}}})
        pending = await db.clearances.count_documents({"approvals": {"$elemMatch": {"office": office, "status": "pending"}}})
        approved = await db.clearances.count_documents({"approvals": {"$elemMatch": {"office": office, "status": "approved"}}})
        rejected = await db.clearances.count_documents({"approvals": {"$elemMatch": {"office": office, "status": "rejected"}}})
    else:
        total = await db.clearances.count_documents({})
        pending = await db.clearances.count_documents({"overall_status": "pending"})
        approved = await db.clearances.count_documents({"overall_status": "approved"})
        rejected = await db.clearances.count_documents({"overall_status": "rejected"})

    return {"total": total, "pending": pending, "approved": approved, "rejected": rejected}


# ================= Constants / meta =================
@api_router.get("/constants")
async def get_constants():
    return {
        "offices": OFFICES,
        "courses": COURSES,
        "year_levels": YEAR_LEVELS,
        "sections": SECTIONS,
        "campuses": CAMPUSES,
        "colleges": COLLEGES,
    }


@api_router.get("/")
async def root():
    return {"message": "MinSU Clearance System API", "version": "2.0.0"}


# ================= Admin =================
async def _require_admin(user_id: str) -> dict:
    user = await db.users.find_one({"id": user_id})
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@api_router.get("/admin/users")
async def admin_list_users(user_id: str):
    await _require_admin(user_id)
    users = await db.users.find(
        {}, {"_id": 0, "password_hash": 0, "verification_code": 0}
    ).sort("created_at", -1).to_list(1000)

    # Annotate each user with a live "is_locked" flag derived from lockout_until
    now = datetime.now(timezone.utc)
    for u in users:
        raw = u.get("lockout_until")
        locked = False
        if raw:
            try:
                locked = datetime.fromisoformat(raw) > now
            except ValueError:
                locked = False
        u["is_locked"] = locked
    return {"users": users}


@api_router.post("/admin/users/{target_user_id}/unlock")
async def admin_unlock_user(target_user_id: str, user_id: str, request: Request):
    admin = await _require_admin(user_id)
    target = await db.users.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    was_locked = bool(target.get("lockout_until"))
    await db.users.update_one(
        {"id": target_user_id},
        {"$unset": {"lockout_until": "", "last_lockout_at": ""}},
    )
    await write_audit(
        actor_id=admin["id"], actor_email=admin["email"], actor_role="admin",
        action="admin.unlock_user", resource_type="user", resource_id=target_user_id,
        status="success",
        details={"target_email": target.get("email"), "was_locked": was_locked},
        request=request,
    )
    return {"success": True, "message": "Account unlocked"}


@api_router.delete("/admin/users/{target_user_id}")
async def admin_delete_user(target_user_id: str, user_id: str, request: Request):
    admin = await _require_admin(user_id)

    # Validation: can't delete self
    if target_user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    target = await db.users.find_one({"id": target_user_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Validation: can't delete the last remaining admin
    if target.get("role") == "admin":
        admin_count = await db.users.count_documents({"role": "admin"})
        if admin_count <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last administrator. Promote another user to admin first.",
            )

    # Validation: block deletion if the target has active (pending) clearances
    if target.get("role") == "student":
        active = await db.clearances.count_documents(
            {"student_id": target_user_id, "overall_status": "pending"}
        )
        if active > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Student has {active} pending clearance(s). Resolve them before deleting.",
            )
    elif target.get("role") == "faculty":
        office = target.get("office")
        pending_for_office = await db.clearances.count_documents(
            {"approvals": {"$elemMatch": {"office": office, "status": "pending"}}}
        )
        if pending_for_office > 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Faculty office '{office}' has {pending_for_office} pending clearance(s). "
                    "Reassign or resolve before deleting."
                ),
            )

    result = await db.users.delete_one({"id": target_user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    await write_audit(
        actor_id=admin["id"], actor_email=admin["email"], actor_role="admin",
        action="admin.delete_user", resource_type="user", resource_id=target_user_id,
        status="success",
        details={"target_email": target.get("email"), "target_role": target.get("role")},
        request=request,
    )
    return {"success": True, "message": "User deleted successfully"}


@api_router.get("/admin/audit-logs")
async def admin_list_audit_logs(
    user_id: str,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    actor_email: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
):
    await _require_admin(user_id)
    q: dict = {}
    if action:
        q["action"] = action
    if resource_type:
        q["resource_type"] = resource_type
    if actor_email:
        q["actor_email"] = {"$regex": actor_email, "$options": "i"}
    if status:
        q["status"] = status

    limit = max(1, min(limit, 1000))
    logs = await db.audit_logs.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return {"logs": logs, "count": len(logs)}


@api_router.get("/admin/audit-logs/actions")
async def admin_audit_log_actions(user_id: str):
    await _require_admin(user_id)
    actions = await db.audit_logs.distinct("action")
    resources = await db.audit_logs.distinct("resource_type")
    return {"actions": sorted(actions), "resource_types": sorted(resources)}


# ================= Clearance-level audit trail =================
@api_router.get("/clearances/{clearance_id}/audit-trail")
async def clearance_audit_trail(clearance_id: str, user_id: str):
    user = await db.users.find_one({"id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    clearance = await db.clearances.find_one({"id": clearance_id})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    if user["role"] == "student" and clearance["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    logs = await db.audit_logs.find(
        {"resource_type": "clearance", "resource_id": clearance_id},
        {"_id": 0},
    ).sort("timestamp", 1).to_list(500)
    return {"trail": logs}


# ================= Startup =================
@app.on_event("startup")
async def on_startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.audit_logs.create_index("resource_id")
        await db.audit_logs.create_index("actor_id")
        await db.clearances.create_index("student_id")
        await db.clearances.create_index("overall_status")
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")

    # Seed default admin if absent (idempotent)
    admin_email = (os.environ.get("ADMIN_EMAIL") or "admin@minsu.edu.ph").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD") or "Admin@MinSU2025"
    existing_admin = await db.users.find_one({"email": admin_email})
    if existing_admin is None:
        await db.users.insert_one({
            "id": generate_uuid(),
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "full_name": "System Administrator",
            "role": "admin",
            "email_verified": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Seeded default admin: {admin_email}")
    elif not verify_password(admin_password, existing_admin["password_hash"]):
        # Keep admin in sync with env on startup
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}},
        )


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ================= App assembly =================
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
