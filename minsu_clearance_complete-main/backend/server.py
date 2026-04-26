from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

security = HTTPBearer()
from motor.motor_asyncio import AsyncIOMotorClient
import certifi


import os
import logging
import uuid
import secrets
import string
import hashlib
import shutil
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import bcrypt
import jwt as pyjwt
import aiofiles
from fastapi import FastAPI, APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email

from sendgrid.helpers.mail import Mail, Email


# ========== CONFIG ==========
mongo_url = os.environ.get("MONGO_URL")

if not mongo_url:
    raise Exception("MONGO_URL is not set")

client = AsyncIOMotorClient(mongo_url, tlsCAFile=certifi.where())

db_name = os.environ.get("DB_NAME", "clearance_db")
db = client[db_name]

JWT_SECRET = os.environ.get('JWT_SECRET', 'dev_secret')
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'jhamairabulan77@gmail.com')
SENDER_NAME = os.environ.get('SENDER_NAME', 'MinSU Clearance System')

UPLOAD_DIR = Path(os.environ.get('UPLOAD_DIR', 'uploads'))

try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print("UPLOAD DIR ERROR:", e)

# CORS allowlist (explicit origins; supports comma-separated env)
_cors_env = os.environ.get('CORS_ORIGINS', '').strip()
if _cors_env and _cors_env != '*':
    CORS_ORIGINS = [o.strip() for o in _cors_env.split(',') if o.strip()]
else:
    CORS_ORIGINS = [
        "http://localhost:3000",
        "http://localhost:8001",
        "https://clearance-hub-18.preview.emergentagent.com"
    ]

# Password complexity
import re
def validate_password_strength(password: str) -> Optional[str]:
    if len(password) < 8:
        return "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return "Password must contain at least one digit"
    return None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MinSU Clearance System")
api_router = APIRouter(prefix="/api")

# ========== CONSTANTS ==========
OFFICES = [
    'University Librarian',
    'Guidance Counselor',
    'SAS Director/Coordinator',
    'Student Affairs/Finance',
    'College Dean/Program Chair',
    'Registrar'
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
    'BSCPE', 'BSEE', 'BSCE', 'BSME'
]
YEAR_LEVELS = ['1st Year', '2nd Year', '3rd Year', '4th Year']
SECTIONS = ['F1', 'F2', 'F3']

CLEARANCE_TYPES = [
    'End of Semester',
    'Enrollment',
    'Graduation',
    'Transfer',
    'Leave of Absence',
    'Scholarship',
    'Others'
]

# ========== MODELS ==========
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

class EmailVerification(BaseModel):
    email: EmailStr
    code: str

class ResendVerification(BaseModel):
    email: EmailStr

class ClearanceCreate(BaseModel):
    semester: str
    academic_year: str
    clearance_type: str = "End of Semester"
    purpose: Optional[str] = None

class ClearanceProcess(BaseModel):
    action: str
    comments: Optional[str] = None

class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    email: EmailStr
    code: str
    new_password: str

# ========== HELPERS ==========
def generate_uuid():
    return str(uuid.uuid4())

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    try:
        # Support legacy SHA256 hashes for migration
        if not hashed.startswith('$2'):
            return hashlib.sha256(password.encode()).hexdigest() == hashed
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
        "type": "access"
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def generate_verification_code():
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def generate_approval_code():
    timestamp = datetime.now(timezone.utc).strftime("%y%m%d")
    random_part = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"CLR-{timestamp}-{random_part}"

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:

    token = credentials.credentials

    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user = await db.users.find_one(
            {"id": payload["sub"]},
            {"_id": 0, "password_hash": 0, "verification_code": 0}
        )

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")

    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") not in ("admin", "superadmin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

async def require_superadmin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Superadmin access required")
    return user

# ========== SETTINGS (DB-backed override of env) ==========
async def get_setting(key: str, default: str = "") -> str:
    doc = await db.app_settings.find_one({"key": key}, {"_id": 0})
    if doc and doc.get("value"):
        return doc["value"]
    return default

async def get_email_settings():
    api_key = await get_setting("sendgrid_api_key", SENDGRID_API_KEY)
    sender_email = await get_setting("sender_email", SENDER_EMAIL)
    sender_name = await get_setting("sender_name", SENDER_NAME)
    return api_key, sender_email, sender_name

# ========== EMAIL ==========
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email
import asyncio

# ---------- TEMPLATE ----------
def email_template(title: str, content: str) -> str:
    return f"""
    <div style="font-family: Arial, sans-serif; max-width:600px; margin:auto;">
        <h2 style="color:#1a5f3f;">{title}</h2>
        <div style="font-size:14px; color:#333;">
            {content}
        </div>
        <hr style="margin:20px 0;">
        <p style="font-size:12px; color:#888;">
            MinSU Clearance System
        </p>
    </div>
    """


# ---------- SYNC SENDER ----------
def _send_email_sync(
    to_email: str,
    subject: str,
    html_content: str,
    api_key: str,
    sender_email: str,
    sender_name: str
) -> bool:

    # fallback if no API key (dev mode)
    if not api_key:
        logger.warning(f"[EMAIL DEV MODE] To: {to_email} | Subject: {subject}")
        return False

    try:
        print("📧 SENDING EMAIL...")
        print("TO:", to_email)
        print("FROM:", sender_email)

        message = Mail(
            from_email=Email(sender_email.strip(), sender_name.strip()),
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )

        sg = SendGridAPIClient(api_key)
        response = sg.send(message)

        print("✅ SENDGRID STATUS:", response.status_code)

        return response.status_code in (200, 202)

    except Exception as e:
        print("❌ SENDGRID ERROR:", str(e))
        logger.error(f"SendGrid error: {e}")
        return False


# ---------- ASYNC WRAPPER ----------
async def send_email(to_email: str, subject: str, html_content: str) -> bool:
    api_key, sender_email, sender_name = await get_email_settings()

    print("🔧 EMAIL SETTINGS:")
    print("API KEY:", api_key[:10] + "..." if api_key else "NONE")
    print("SENDER:", sender_email)

    return await asyncio.to_thread(
        _send_email_sync,
        to_email,
        subject,
        html_content,
        api_key,
        sender_email,
        sender_name
    )
# ========== AUDIT LOG ==========
async def log_audit(actor_id: Optional[str], actor_email: Optional[str], actor_role: Optional[str],
                    action: str, target_type: Optional[str] = None, target_id: Optional[str] = None,
                    details: Optional[dict] = None, ip: Optional[str] = None):
    entry = {
        "id": generate_uuid(),
        "actor_id": actor_id,
        "actor_email": actor_email,
        "actor_role": actor_role,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "details": details or {},
        "ip": ip,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await db.audit_logs.insert_one(entry)

def get_client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", request.client.host if request.client else "unknown").split(",")[0].strip()

# ========== STARTUP ==========
@app.on_event("startup")
async def startup():
    try:
        await db.users.create_index("email", unique=True)
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.clearances.create_index("student_id")

        # Seed Superadmin (highest privilege)
        sa_email = os.environ.get('SUPERADMIN_EMAIL', 'superadmin@minsu.edu.ph')
        sa_password = os.environ.get('SUPERADMIN_PASSWORD', 'Sup3rAdmin#2026')
        sa_existing = await db.users.find_one({"email": sa_email})
        if not sa_existing:
            await db.users.insert_one({
                "id": generate_uuid(),
                "email": sa_email,
                "password_hash": hash_password(sa_password),
                "full_name": "Super Administrator",
                "role": "superadmin",
                "email_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"Seeded superadmin: {sa_email}")
        elif sa_existing.get("role") != "superadmin":
            await db.users.update_one({"email": sa_email}, {"$set": {"role": "superadmin"}})

        # Seed admin
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@minsu.edu.ph')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'Admin@123')
        existing = await db.users.find_one({"email": admin_email})
        if not existing:
            await db.users.insert_one({
                "id": generate_uuid(),
                "email": admin_email,
                "password_hash": hash_password(admin_password),
                "full_name": "System Administrator",
                "role": "admin",
                "email_verified": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            logger.info(f"Seeded admin: {admin_email}")
        elif not verify_password(admin_password, existing.get("password_hash", "")):
            await db.users.update_one(
                {"email": admin_email},
                {"$set": {"password_hash": hash_password(admin_password), "email_verified": True}}
            )
            logger.info("Admin password updated")

        # Seed faculty accounts (one per office) if missing
        default_faculty_password = os.environ.get('DEFAULT_FACULTY_PASSWORD', 'Faculty@2026')
        for office in OFFICES:
            slug = office.lower().replace(' ', '').replace('/', '_').replace('-', '')
            faculty_email = f"{slug}@minsu.edu.ph"
            if not await db.users.find_one({"email": faculty_email}):
                await db.users.insert_one({
                    "id": generate_uuid(),
                    "email": faculty_email,
                    "password_hash": hash_password(default_faculty_password),
                    "full_name": f"{office} Office",
                    "role": "faculty",
                    "office": office,
                    "email_verified": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "seeded": True
                })
                logger.info(f"Seeded faculty: {faculty_email} ({office})")
        logger.info("Startup complete")
    except Exception as e:
        logger.error(f"Startup error: {e}")

# ========== AUTH ROUTES ==========
@api_router.post("/auth/register")
async def register(user_data: UserCreate, request: Request):
    if user_data.role != "student":
        raise HTTPException(status_code=403, detail="Only student registration is allowed publicly")

    email = user_data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    if not user_data.student_id or not user_data.course or not user_data.year_level \
       or not user_data.section or not user_data.campus or not user_data.college:
        raise HTTPException(status_code=400, detail="All student fields are required")

    pw_err = validate_password_strength(user_data.password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    verification_code = generate_verification_code()
    user_id = generate_uuid()

    user_doc = {
        "id": user_id,
        "email": email,
        "password_hash": hash_password(user_data.password),
        "full_name": user_data.full_name,
        "role": "student",
        "student_id": user_data.student_id,
        "office": None,
        "course": user_data.course,
        "year_level": user_data.year_level,
        "section": user_data.section,
        "campus": user_data.campus,
        "college": user_data.college,
        "email_verified": False,
        "verification_code": verification_code,
        "verification_expires": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.users.insert_one(user_doc)

    # Send verification email
    body = f"""
    <p>Hello <strong>{user_data.full_name}</strong>,</p>
    <p>Thank you for registering with the MinSU Clearance System. To complete your registration, please use the verification code below:</p>
    <div style="background:#f0f7f0;border:2px dashed #1a5f3f;padding:24px;text-align:center;margin:24px 0;border-radius:8px;">
        <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#1a5f3f;">{verification_code}</div>
    </div>
    <p style="color:#666;"><strong>Note:</strong> This code expires in 30 minutes.</p>
    <p>If you did not create this account, please ignore this email.</p>
    """
    asyncio.create_task(send_email(email, "Verify Your MinSU Clearance Account", email_template("Email Verification", body)))

    await log_audit(user_id, email, "student", "USER_REGISTERED", "user", user_id, {"full_name": user_data.full_name}, get_client_ip(request))

    return {
        "success": True,
        "message": "Registration successful! Check your email for the 6-digit verification code.",
        "email": email,
        "dev_code": verification_code if not SENDGRID_API_KEY else None
    }

@api_router.post("/auth/verify-email")
async def verify_email(data: EmailVerification, request: Request):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("email_verified"):
        return {"success": True, "message": "Email already verified"}
    if user.get("verification_code") != data.code:
        raise HTTPException(status_code=400, detail="Invalid verification code")
    expires = user.get("verification_expires")
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Verification code expired. Please request a new one.")

    await db.users.update_one(
        {"email": email},
        {"$set": {"email_verified": True}, "$unset": {"verification_code": "", "verification_expires": ""}}
    )
    await log_audit(user["id"], email, user.get("role"), "EMAIL_VERIFIED", "user", user["id"], None, get_client_ip(request))
    return {"success": True, "message": "Email verified successfully! You can now log in."}

@api_router.post("/auth/resend-verification")
async def resend_verification(data: ResendVerification):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.get("email_verified"):
        return {"success": True, "message": "Email already verified"}

    code = generate_verification_code()
    await db.users.update_one(
        {"email": email},
        {"$set": {
            "verification_code": code,
            "verification_expires": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
        }}
    )
    body = f"""
    <p>Hello,</p>
    <p>Here is your new verification code:</p>
    <div style="background:#f0f7f0;border:2px dashed #1a5f3f;padding:24px;text-align:center;margin:24px 0;border-radius:8px;">
        <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#1a5f3f;">{code}</div>
    </div>
    <p style="color:#666;">This code expires in 30 minutes.</p>
    """
    asyncio.create_task(send_email(email, "Your New Verification Code - MinSU", email_template("Verification Code", body)))
    return {"success": True, "message": "A new verification code has been sent to your email.",
            "dev_code": code if not SENDGRID_API_KEY else None}

@api_router.post("/auth/login")
async def login(credentials: UserLogin, request: Request):
    email = credentials.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        await log_audit(None, email, None, "LOGIN_FAILED", "user", None, {"reason": "invalid_credentials"}, get_client_ip(request))
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.get("email_verified", False):
        raise HTTPException(status_code=403, detail="Please verify your email first. Check your inbox for the code.")

    token = create_access_token(user["id"], user["email"], user["role"])
    await log_audit(user["id"], email, user.get("role"), "LOGIN_SUCCESS", "user", user["id"], None, get_client_ip(request))

    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {
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
            "email_verified": user.get("email_verified", False)
        }
    }

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user": user}

@api_router.post("/auth/logout")
async def logout(request: Request, user: dict = Depends(get_current_user)):
    await log_audit(user["id"], user["email"], user.get("role"), "LOGOUT", "user", user["id"], None, get_client_ip(request))
    return {"success": True}

@api_router.post("/auth/forgot-password")
async def forgot_password(data: ForgotPassword, request: Request):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user:
        return {"success": True, "message": "If that email exists, a code has been sent."}

    code = generate_verification_code()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=15)
    await db.users.update_one(
        {"email": email},
        {"$set": {"reset_code": code, "reset_code_expiry": expiry.isoformat()}}
    )
    body = f"""
    <p>Hello <strong>{user.get('full_name','User')}</strong>,</p>
    <p>You requested a password reset. Use the code below to reset your password:</p>
    <div style="background:#fff8e6;border:2px dashed #d97706;padding:24px;text-align:center;margin:24px 0;border-radius:8px;">
        <div style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#92400e;">{code}</div>
    </div>
    <p style="color:#666;"><strong>This code expires in 15 minutes.</strong></p>
    <p>If you didn't request this, please ignore this email.</p>
    """
    asyncio.create_task(send_email(email, "Password Reset Code - MinSU Clearance", email_template("Password Reset", body)))
    await log_audit(user["id"], email, user.get("role"), "PASSWORD_RESET_REQUESTED", "user", user["id"], None, get_client_ip(request))
    return {"success": True, "message": "If that email exists, a code has been sent.",
            "dev_code": code if not SENDGRID_API_KEY else None}

@api_router.post("/auth/reset-password")
async def reset_password(data: ResetPassword, request: Request):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or "reset_code" not in user:
        raise HTTPException(status_code=400, detail="Invalid reset request")
    if user["reset_code"] != data.code:
        raise HTTPException(status_code=400, detail="Invalid reset code")
    expiry = datetime.fromisoformat(user["reset_code_expiry"])
    if datetime.now(timezone.utc) > expiry:
        raise HTTPException(status_code=400, detail="Reset code has expired")

    pw_err = validate_password_strength(data.new_password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    await db.users.update_one(
        {"email": email},
        {"$set": {"password_hash": hash_password(data.new_password)},
         "$unset": {"reset_code": "", "reset_code_expiry": ""}}
    )
    await log_audit(user["id"], email, user.get("role"), "PASSWORD_RESET_SUCCESS", "user", user["id"], None, get_client_ip(request))
    return {"success": True, "message": "Password reset successfully"}

# ========== CLEARANCE ROUTES ==========
@api_router.post("/clearances/create")
async def create_clearance(data: ClearanceCreate, request: Request, user: dict = Depends(get_current_user)):
    if user["role"] != "student":
        raise HTTPException(status_code=403, detail="Only students can create clearances")
    if data.clearance_type not in CLEARANCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid clearance type. Must be one of: {CLEARANCE_TYPES}")

    clearance_id = generate_uuid()
    approvals = [{
        "office": office, "status": "pending",
        "approved_by": None, "approved_by_name": None,
        "approved_at": None, "comments": None, "approval_code": None
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
        "clearance_type": data.clearance_type,
        "purpose": data.purpose,
        "overall_status": "pending",
        "approvals": approvals,
        "attachments": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None
    }
    await db.clearances.insert_one(clearance_doc)
    await log_audit(user["id"], user["email"], user["role"], "CLEARANCE_CREATED", "clearance", clearance_id,
                    {"type": data.clearance_type, "semester": data.semester}, get_client_ip(request))
    return {"success": True, "clearance_id": clearance_id}

@api_router.get("/clearances/list")
async def list_clearances(
    status: Optional[str] = None,
    course: Optional[str] = None,
    year_level: Optional[str] = None,
    section: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    user: dict = Depends(get_current_user)
):
    query = {}
    if user["role"] == "student":
        query["student_id"] = user["id"]
    elif user["role"] == "faculty":
        query["approvals"] = {"$elemMatch": {"office": user.get("office"), "status": "pending"}}

    if course: query["course"] = course
    if year_level: query["year_level"] = year_level
    if section: query["section"] = section
    if status: query["overall_status"] = status

    page = max(1, page)
    page_size = max(1, min(100, page_size))
    skip = (page - 1) * page_size
    total = await db.clearances.count_documents(query)
    clearances = await db.clearances.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)

    return {
        "clearances": clearances,
        "pagination": {
            "page": page, "page_size": page_size, "total_count": total,
            "total_pages": (total + page_size - 1) // page_size,
            "has_next": page * page_size < total,
            "has_prev": page > 1
        }
    }

@api_router.get("/clearances/{clearance_id}")
async def get_clearance(clearance_id: str, user: dict = Depends(get_current_user)):
    clearance = await db.clearances.find_one({"id": clearance_id}, {"_id": 0})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    if user["role"] == "student" and clearance["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    return {"clearance": clearance}

@api_router.post("/clearances/{clearance_id}/process")
async def process_clearance(clearance_id: str, data: ClearanceProcess, request: Request, user: dict = Depends(get_current_user)):
    if user["role"] != "faculty":
        raise HTTPException(status_code=403, detail="Only faculty can process clearances")
    clearance = await db.clearances.find_one({"id": clearance_id})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    office = user.get("office")
    if not office:
        raise HTTPException(status_code=400, detail="Faculty must have an assigned office")

    approvals = clearance.get("approvals", [])
    if office == "Registrar":
        non_reg = [a for a in approvals if a["office"] != "Registrar"]
        pending = sum(1 for a in non_reg if a["status"] != "approved")
        if pending > 0:
            raise HTTPException(status_code=400, detail=f"Registrar can only approve after all other offices ({pending} still pending)")

    found = False
    for a in approvals:
        if a["office"] == office:
            if a["status"] != "pending":
                raise HTTPException(status_code=400, detail="Already processed by your office")
            a["status"] = "approved" if data.action == "approve" else "rejected"
            a["approved_by"] = user["id"]
            a["approved_by_name"] = user["full_name"]
            a["approved_at"] = datetime.now(timezone.utc).isoformat()
            a["comments"] = data.comments
            a["approval_code"] = generate_approval_code()
            found = True
            break
    if not found:
        raise HTTPException(status_code=400, detail="No pending approval for your office")

    overall = "pending"
    if data.action == "reject":
        overall = "rejected"
    elif all(x["status"] == "approved" for x in approvals):
        overall = "approved"

    completed_at = datetime.now(timezone.utc).isoformat() if overall in ("approved", "rejected") else None
    await db.clearances.update_one(
        {"id": clearance_id},
        {"$set": {"approvals": approvals, "overall_status": overall,
                  "updated_at": datetime.now(timezone.utc).isoformat(), "completed_at": completed_at}}
    )
    await log_audit(user["id"], user["email"], user["role"], f"CLEARANCE_{data.action.upper()}D",
                    "clearance", clearance_id, {"office": office, "comments": data.comments}, get_client_ip(request))

    # Notify student when fully approved
    if overall == "approved":
        student_email = clearance.get("student_email")
        student_name = clearance.get("student_name")
        ctype = clearance.get("clearance_type", "Clearance")
        rows = "".join([
            f"<tr><td style='padding:8px;border-bottom:1px solid #eee;'>{a['office']}</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;color:#1a5f3f;font-weight:600;'>✓ Approved</td>"
            f"<td style='padding:8px;border-bottom:1px solid #eee;font-family:monospace;font-size:11px;'>{a.get('approval_code','')}</td></tr>"
            for a in approvals
        ])
        body = f"""
        <p>Hello <strong>{student_name}</strong>,</p>
        <p>Great news! Your <strong>{ctype}</strong> clearance has been fully signed and approved by all offices.</p>
        <p><strong>Semester:</strong> {clearance.get('semester')} {clearance.get('academic_year')}</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
            <thead><tr style="background:#1a5f3f;color:white;">
                <th style="padding:10px;text-align:left;">Office</th>
                <th style="padding:10px;text-align:left;">Status</th>
                <th style="padding:10px;text-align:left;">Approval Code</th>
            </tr></thead><tbody>{rows}</tbody>
        </table>
        <p>You may now proceed to the Registrar's office to claim your clearance slip.</p>
        <p>Congratulations and best regards!</p>
        """
        asyncio.create_task(send_email(student_email, f"✓ Your {ctype} Clearance is Fully Approved", email_template("Clearance Fully Signed", body)))
    elif data.action == "reject":
        student_email = clearance.get("student_email")
        body = f"""
        <p>Hello <strong>{clearance.get('student_name')}</strong>,</p>
        <p>Your clearance was <strong style="color:#dc2626;">rejected</strong> by the <strong>{office}</strong>.</p>
        <p><strong>Comments:</strong> {data.comments or 'No comments provided.'}</p>
        <p>Please address the issue and create a new clearance request, or contact the office directly.</p>
        """
        asyncio.create_task(send_email(student_email, "Clearance Rejected - Action Required", email_template("Clearance Rejected", body)))

    return {"success": True, "message": f"Clearance {data.action}d", "overall_status": overall}

class BulkProcess(BaseModel):
    clearance_ids: List[str]
    action: str  # approve or reject
    comments: Optional[str] = None

@api_router.post("/clearances/bulk-process")
async def bulk_process(data: BulkProcess, request: Request, user: dict = Depends(get_current_user)):
    """Faculty: approve/reject many clearances at once for their office."""
    if user["role"] != "faculty":
        raise HTTPException(status_code=403, detail="Only faculty can process clearances")
    office = user.get("office")
    if not office:
        raise HTTPException(status_code=400, detail="Faculty must have an assigned office")
    if data.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="Invalid action")
    if not data.clearance_ids:
        raise HTTPException(status_code=400, detail="No clearances selected")

    results = {"processed": [], "skipped": [], "fully_approved": []}
    for cid in data.clearance_ids:
        clearance = await db.clearances.find_one({"id": cid})
        if not clearance:
            results["skipped"].append({"id": cid, "reason": "not_found"})
            continue

        approvals = clearance.get("approvals", [])
        if office == "Registrar":
            non_reg = [a for a in approvals if a["office"] != "Registrar"]
            pending = sum(1 for a in non_reg if a["status"] != "approved")
            if pending > 0:
                results["skipped"].append({"id": cid, "reason": f"others_pending:{pending}"})
                continue

        target = next((a for a in approvals if a["office"] == office), None)
        if not target or target["status"] != "pending":
            results["skipped"].append({"id": cid, "reason": "already_processed"})
            continue

        target["status"] = "approved" if data.action == "approve" else "rejected"
        target["approved_by"] = user["id"]
        target["approved_by_name"] = user["full_name"]
        target["approved_at"] = datetime.now(timezone.utc).isoformat()
        target["comments"] = data.comments
        target["approval_code"] = generate_approval_code()

        overall = "pending"
        if data.action == "reject":
            overall = "rejected"
        elif all(a["status"] == "approved" for a in approvals):
            overall = "approved"
        completed_at = datetime.now(timezone.utc).isoformat() if overall in ("approved", "rejected") else None

        await db.clearances.update_one(
            {"id": cid},
            {"$set": {"approvals": approvals, "overall_status": overall,
                      "updated_at": datetime.now(timezone.utc).isoformat(), "completed_at": completed_at}}
        )
        await log_audit(user["id"], user["email"], user["role"], f"CLEARANCE_BULK_{data.action.upper()}D",
                        "clearance", cid, {"office": office, "comments": data.comments}, get_client_ip(request))
        results["processed"].append(cid)

        if overall == "approved":
            results["fully_approved"].append(cid)
            student_email = clearance.get("student_email")
            student_name = clearance.get("student_name")
            ctype = clearance.get("clearance_type", "Clearance")
            rows = "".join([
                f"<tr><td style='padding:8px;border-bottom:1px solid #eee;'>{a['office']}</td>"
                f"<td style='padding:8px;border-bottom:1px solid #eee;color:#1a5f3f;font-weight:600;'>✓ Approved</td>"
                f"<td style='padding:8px;border-bottom:1px solid #eee;font-family:monospace;font-size:11px;'>{a.get('approval_code','')}</td></tr>"
                for a in approvals
            ])
            body = f"""
            <p>Hello <strong>{student_name}</strong>,</p>
            <p>Your <strong>{ctype}</strong> clearance is fully signed and approved.</p>
            <table style="width:100%;border-collapse:collapse;margin:20px 0;">
                <thead><tr style="background:#1a5f3f;color:white;">
                    <th style="padding:10px;text-align:left;">Office</th>
                    <th style="padding:10px;text-align:left;">Status</th>
                    <th style="padding:10px;text-align:left;">Code</th>
                </tr></thead><tbody>{rows}</tbody>
            </table>
            <p>You may proceed to the Registrar's office to claim your clearance slip.</p>
            """
            asyncio.create_task(send_email(student_email, f"✓ Your {ctype} Clearance is Fully Approved", email_template("Clearance Fully Signed", body)))

    return {"success": True, "results": results,
            "summary": {"total": len(data.clearance_ids), "processed": len(results["processed"]),
                        "skipped": len(results["skipped"]), "fully_approved": len(results["fully_approved"])}}

# ========== FILE UPLOADS ==========
@api_router.post("/clearances/{clearance_id}/upload")
async def upload_attachment(
    clearance_id: str,
    request: Request,
    file: UploadFile = File(...),
    description: str = Form(""),
    office: str = Form(""),
    user: dict = Depends(get_current_user)
):
    clearance = await db.clearances.find_one({"id": clearance_id})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    if user["role"] == "student" and clearance["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")

    # Limit size to 10MB
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 10MB")

    allowed_ext = {'.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.xlsx', '.txt'}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_ext:
        raise HTTPException(status_code=400, detail=f"File type not allowed. Allowed: {sorted(allowed_ext)}")

    file_id = generate_uuid()
    safe_name = f"{file_id}{ext}"
    file_path = UPLOAD_DIR / safe_name
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(contents)

    attachment = {
        "id": file_id,
        "original_name": file.filename,
        "stored_name": safe_name,
        "size": len(contents),
        "content_type": file.content_type,
        "description": description,
        "office": office,
        "uploaded_by": user["id"],
        "uploaded_by_name": user["full_name"],
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }
    await db.clearances.update_one(
        {"id": clearance_id},
        {"$push": {"attachments": attachment}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await log_audit(user["id"], user["email"], user["role"], "FILE_UPLOADED", "clearance", clearance_id,
                    {"file": file.filename, "size": len(contents)}, get_client_ip(request))
    return {"success": True, "attachment": attachment}

@api_router.get("/clearances/{clearance_id}/attachments/{attachment_id}/download")
async def download_attachment(clearance_id: str, attachment_id: str, user: dict = Depends(get_current_user)):
    clearance = await db.clearances.find_one({"id": clearance_id})
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    if user["role"] == "student" and clearance["student_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    attachment = next((a for a in clearance.get("attachments", []) if a["id"] == attachment_id), None)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    file_path = UPLOAD_DIR / attachment["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File missing on server")
    return FileResponse(file_path, filename=attachment["original_name"], media_type=attachment.get("content_type"))

# ========== STATS ==========
@api_router.get("/stats")
async def stats(user: dict = Depends(get_current_user)):
    if user["role"] == "student":
        match = {"student_id": user["id"]}
    elif user["role"] == "faculty":
        match = {"approvals": {"$elemMatch": {"office": user.get("office")}}}
    else:
        match = {}
    total = await db.clearances.count_documents(match)
    pending = await db.clearances.count_documents({**match, "overall_status": "pending"})
    approved = await db.clearances.count_documents({**match, "overall_status": "approved"})
    rejected = await db.clearances.count_documents({**match, "overall_status": "rejected"})
    return {"total": total, "pending": pending, "approved": approved, "rejected": rejected}

# ========== ADMIN ==========
@api_router.get("/admin/users")
async def admin_users(page: int = 1, page_size: int = 50, search: Optional[str] = None,
                      user: dict = Depends(require_admin)):
    query = {}
    if search:
        query["$or"] = [
            {"full_name": {"$regex": search, "$options": "i"}},
            {"email": {"$regex": search, "$options": "i"}},
            {"student_id": {"$regex": search, "$options": "i"}}
        ]
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    skip = (page - 1) * page_size
    total = await db.users.count_documents(query)
    users = await db.users.find(query, {"_id": 0, "password_hash": 0, "verification_code": 0,
                                         "reset_code": 0, "reset_code_expiry": 0}).skip(skip).limit(page_size).to_list(page_size)
    return {"users": users, "pagination": {"page": page, "page_size": page_size, "total_count": total,
                                            "total_pages": (total + page_size - 1) // page_size}}

@api_router.delete("/admin/users/{target_id}")
async def admin_delete_user(target_id: str, request: Request, user: dict = Depends(require_admin)):
    if target_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    target = await db.users.find_one({"id": target_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Only superadmin can delete admins or superadmins
    if target.get("role") in ("admin", "superadmin") and user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can delete admin accounts")
    # Protect the last superadmin from being deleted
    if target.get("role") == "superadmin":
        sa_count = await db.users.count_documents({"role": "superadmin"})
        if sa_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last superadmin")
    result = await db.users.delete_one({"id": target_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    await log_audit(user["id"], user["email"], user["role"], "USER_DELETED", "user", target_id,
                    {"target_email": target.get("email"), "target_role": target.get("role")}, get_client_ip(request))
    return {"success": True}

@api_router.post("/admin/create-user")
async def admin_create_user(data: UserCreate, request: Request, user: dict = Depends(require_admin)):
    if data.role not in ["faculty", "admin", "superadmin"]:
        raise HTTPException(status_code=400, detail="Use public registration for student accounts")
    # Only superadmin can create admin or superadmin accounts
    if data.role in ("admin", "superadmin") and user.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail="Only superadmin can create admin accounts")
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    if data.role == "faculty" and (not data.office or data.office not in OFFICES):
        raise HTTPException(status_code=400, detail="Valid office is required for faculty")

    pw_err = validate_password_strength(data.password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    new_id = generate_uuid()
    await db.users.insert_one({
        "id": new_id,
        "email": email,
        "password_hash": hash_password(data.password),
        "full_name": data.full_name,
        "role": data.role,
        "office": data.office if data.role == "faculty" else None,
        "campus": data.campus,
        "email_verified": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": user["id"]
    })
    await log_audit(user["id"], user["email"], user["role"], "USER_CREATED", "user", new_id,
                    {"role": data.role, "email": email}, get_client_ip(request))
    return {"success": True, "user_id": new_id}

@api_router.get("/admin/audit-logs")
async def admin_audit_logs(
    page: int = 1, page_size: int = 50,
    action: Optional[str] = None, actor_email: Optional[str] = None,
    cursor: Optional[str] = None,
    user: dict = Depends(require_admin)
):
    query = {}
    if action: query["action"] = {"$regex": action, "$options": "i"}
    if actor_email: query["actor_email"] = {"$regex": actor_email, "$options": "i"}

    page_size = max(1, min(200, page_size))

    # Cursor mode (preferred for large datasets) — cursor is the timestamp of the last seen entry
    if cursor:
        query["timestamp"] = {"$lt": cursor}
        logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(page_size + 1).to_list(page_size + 1)
        has_next = len(logs) > page_size
        logs = logs[:page_size]
        next_cursor = logs[-1]["timestamp"] if has_next and logs else None
        return {"logs": logs, "cursor": next_cursor, "has_next": has_next, "mode": "cursor"}

    # Page mode (legacy)
    page = max(1, page)
    skip = (page - 1) * page_size
    total = await db.audit_logs.count_documents(query)
    logs = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).limit(page_size).to_list(page_size)
    return {"logs": logs, "pagination": {"page": page, "page_size": page_size, "total_count": total,
                                          "total_pages": (total + page_size - 1) // page_size}, "mode": "page"}

# ========== ADMIN: APP SETTINGS (SendGrid override) ==========
class SettingsUpdate(BaseModel):
    sendgrid_api_key: Optional[str] = None
    sender_email: Optional[str] = None
    sender_name: Optional[str] = None

@api_router.get("/admin/settings")
async def admin_get_settings(user: dict = Depends(require_admin)):
    """Return current effective email settings (DB override or env). API key is masked."""
    api_key, sender_email, sender_name = await get_email_settings()
    masked = (api_key[:6] + "..." + api_key[-4:]) if api_key and len(api_key) > 10 else (api_key or "")
    return {
        "sendgrid_api_key_masked": masked,
        "sendgrid_api_key_set": bool(api_key),
        "sender_email": sender_email,
        "sender_name": sender_name,
        "source": {
            "sendgrid_api_key": "db" if (await db.app_settings.find_one({"key": "sendgrid_api_key"})) else "env",
            "sender_email": "db" if (await db.app_settings.find_one({"key": "sender_email"})) else "env",
            "sender_name": "db" if (await db.app_settings.find_one({"key": "sender_name"})) else "env",
        }
    }

@api_router.post("/admin/settings")
async def admin_update_settings(data: SettingsUpdate, request: Request, user: dict = Depends(require_admin)):
    updates = []
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None:
            continue
        if value == "":
            # Empty string clears DB override (revert to env)
            await db.app_settings.delete_one({"key": field})
            updates.append(f"{field}=cleared")
        else:
            await db.app_settings.update_one(
                {"key": field},
                {"$set": {"key": field, "value": value, "updated_at": datetime.now(timezone.utc).isoformat(),
                          "updated_by": user["email"]}},
                upsert=True
            )
            updates.append(f"{field}=updated")
    await log_audit(user["id"], user["email"], user["role"], "SETTINGS_UPDATED", "settings", None,
                    {"changes": updates}, get_client_ip(request))
    return {"success": True, "message": "Settings saved", "changes": updates}

class TestEmailRequest(BaseModel):
    to_email: EmailStr

@api_router.post("/admin/settings/test-email")
async def admin_test_email(data: TestEmailRequest, user: dict = Depends(require_admin)):
    """Send a test email using the current effective settings."""
    api_key, sender_email, sender_name = await get_email_settings()
    if not api_key:
        raise HTTPException(status_code=400, detail="No SendGrid API key configured")
    body = f"""
    <p>Hello,</p>
    <p>This is a test email from the <strong>MinSU Clearance System</strong>. If you're reading this, your SendGrid configuration is working correctly!</p>
    <p style="color:#666;font-size:13px;">Sent by: {user.get('email')} on behalf of {sender_name} &lt;{sender_email}&gt;</p>
    """
    sent = await send_email(data.to_email, "MinSU Clearance — Test Email", email_template("Test Email", body))
    if sent:
        return {"success": True, "message": f"Test email sent to {data.to_email}"}
    raise HTTPException(status_code=500, detail="Failed to send test email. Check server logs (the SendGrid sender may not be verified yet).")

# ========== ADMIN: RESET USER PASSWORD ==========
class AdminResetPassword(BaseModel):
    new_password: str

def generate_strong_password(length: int = 14) -> str:
    """Generate a strong password meeting the complexity policy."""
    import string as _s
    chars = _s.ascii_uppercase + _s.ascii_lowercase + _s.digits + "!@#$%&*"
    while True:
        pw = ''.join(secrets.choice(chars) for _ in range(length))
        if validate_password_strength(pw) is None:
            return pw

@api_router.get("/admin/users/{target_id}/suggest-password")
async def admin_suggest_password(target_id: str, user: dict = Depends(require_admin)):
    return {"suggestion": generate_strong_password()}

@api_router.post("/admin/users/{target_id}/reset-password")
async def admin_reset_user_password(target_id: str, data: AdminResetPassword, request: Request, user: dict = Depends(require_admin)):
    target = await db.users.find_one({"id": target_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    # Only superadmin can reset another admin/superadmin's password
    if target.get("role") in ("admin", "superadmin") and user.get("role") != "superadmin" and target_id != user["id"]:
        raise HTTPException(status_code=403, detail="Only superadmin can reset admin passwords")
    err = validate_password_strength(data.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    await db.users.update_one(
        {"id": target_id},
        {"$set": {"password_hash": hash_password(data.new_password)}}
    )
    await log_audit(user["id"], user["email"], user["role"], "PASSWORD_RESET_BY_ADMIN", "user", target_id,
                    {"target_email": target.get("email")}, get_client_ip(request))
    return {"success": True, "message": f"Password reset for {target.get('email')}"}

# ========== CHANGE OWN PASSWORD ==========
class ChangeOwnPassword(BaseModel):
    current_password: str
    new_password: str

@api_router.post("/auth/change-password")
async def change_own_password(data: ChangeOwnPassword, request: Request, user: dict = Depends(get_current_user)):
    full_user = await db.users.find_one({"id": user["id"]})
    if not verify_password(data.current_password, full_user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    err = validate_password_strength(data.new_password)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if data.current_password == data.new_password:
        raise HTTPException(status_code=400, detail="New password must be different from current password")
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"password_hash": hash_password(data.new_password)}}
    )
    await log_audit(user["id"], user["email"], user.get("role"), "PASSWORD_CHANGED", "user", user["id"], None, get_client_ip(request))
    return {"success": True, "message": "Password changed successfully"}

# ========== UTILITY ==========
@api_router.get("/constants")
async def get_constants():
    return {
        "offices": OFFICES, "courses": COURSES, "year_levels": YEAR_LEVELS,
        "sections": SECTIONS, "campuses": CAMPUSES, "colleges": COLLEGES,
        "clearance_types": CLEARANCE_TYPES
    }

@api_router.get("/")
async def api_root():
    return {"message": "MinSU Clearance System API", "version": "2.0.0"}

# ========== APP CONFIG ==========
app.include_router(api_router)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown():
    client.close()
