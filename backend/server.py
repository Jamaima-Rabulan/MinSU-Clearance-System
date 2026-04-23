from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone
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

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ClearanceCreate(BaseModel):
    semester: str
    academic_year: str

class ClearanceProcess(BaseModel):
    action: str
    comments: Optional[str] = None
    signature_data: Optional[str] = None

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

    if user_data.role == "student":
        if not user_data.student_id:
            raise HTTPException(status_code=400, detail="Student ID is required")
        if not user_data.course:
            raise HTTPException(status_code=400, detail="Course is required")
        if not user_data.year_level:
            raise HTTPException(status_code=400, detail="Year level is required")
        if not user_data.section:
            raise HTTPException(status_code=400, detail="Section is required")
    elif user_data.role == "faculty":
        if not user_data.office or user_data.office not in OFFICES:
            raise HTTPException(status_code=400, detail="Valid office is required for faculty")

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


@api_router.post("/auth/login")
async def login(credentials: UserLogin, request: Request):
    email = credentials.email.lower()
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
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Upgrade legacy hashes on successful login
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
    return {"users": users}


@api_router.delete("/admin/users/{target_user_id}")
async def admin_delete_user(target_user_id: str, user_id: str, request: Request):
    admin = await _require_admin(user_id)
    target = await db.users.find_one({"id": target_user_id})
    result = await db.users.delete_one({"id": target_user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    await write_audit(
        actor_id=admin["id"], actor_email=admin["email"], actor_role="admin",
        action="admin.delete_user", resource_type="user", resource_id=target_user_id,
        status="success",
        details={"target_email": target.get("email") if target else None,
                 "target_role": target.get("role") if target else None},
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
