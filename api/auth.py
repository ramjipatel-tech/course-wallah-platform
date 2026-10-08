import time
import hmac
import hashlib
import json
import base64
from typing import Optional, Dict, Any
from fastapi import HTTPException, Security, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config.settings import SECRET_KEY, ADMIN_USERNAME, ADMIN_PASSWORD
from db.connection import get_db_dependency
from db.models import Student

security = HTTPBearer(auto_error=False)

def hash_password(password: str) -> str:
    """Computes secure salted hash for student passwords."""
    salt = SECRET_KEY[:16]
    return hashlib.sha256(f"{salt}:{password}:{salt}".encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Constant-time verification of student passwords."""
    expected = hash_password(plain_password)
    return hmac.compare_digest(expected, hashed_password)

def create_jwt_token(payload: Dict[str, Any], expires_in: int = 86400) -> str:
    """Generates signed JWT token."""
    header = {"alg": "HS256", "typ": "JWT"}
    body = {**payload, "exp": int(time.time()) + expires_in}
    
    hdr_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    body_b64 = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    
    msg = f"{hdr_b64}.{body_b64}".encode()
    sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode().rstrip("=")
    
    return f"{hdr_b64}.{body_b64}.{sig_b64}"

def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """Verifies signature and expiration of JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        
        hdr_b64, body_b64, sig_b64 = parts
        msg = f"{hdr_b64}.{body_b64}".encode()
        
        # Verify signature
        expected_sig = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).digest()
        pad_len = 4 - (len(sig_b64) % 4) if len(sig_b64) % 4 != 0 else 0
        actual_sig = base64.urlsafe_b64decode(sig_b64 + "=" * pad_len)
        
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        
        # Decode body
        body_pad = 4 - (len(body_b64) % 4) if len(body_b64) % 4 != 0 else 0
        body = json.loads(base64.urlsafe_b64decode(body_b64 + "=" * body_pad).decode())
        
        if body.get("exp", 0) < time.time():
            return None
        return body
    except Exception:
        return None

async def require_admin_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None
) -> Dict[str, Any]:
    """Dependency for protecting admin endpoints."""
    token = None
    if credentials:
        token = credentials.credentials
    elif request and "admin_token" in request.cookies:
        token = request.cookies.get("admin_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required"
        )
    
    data = verify_jwt_token(token)
    if not data or data.get("role") != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Admin access only"
        )
    return data

async def optional_student_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    request: Request = None,
    db: AsyncSession = Depends(get_db_dependency)
) -> Optional[Student]:
    """Retrieves student from session token if present."""
    token = None
    if credentials:
        token = credentials.credentials
    elif request and "student_token" in request.cookies:
        token = request.cookies.get("student_token")

    if not token:
        return None

    data = verify_jwt_token(token)
    if not data or data.get("role") != "STUDENT":
        return None

    student_id = data.get("sub")
    if not student_id:
        return None

    student = await db.get(Student, student_id)
    if not student or student.status != "ACTIVE":
        return None

    return student

async def require_student_auth(
    student: Optional[Student] = Depends(optional_student_auth)
) -> Student:
    """Strict dependency for student-only endpoints."""
    if not student:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Student authentication required. Please login or register."
        )
    return student
