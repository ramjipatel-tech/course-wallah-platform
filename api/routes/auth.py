import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import Student, StudentBatchAccess, StudentActivity, Batch, Lecture
from api.auth import (
    hash_password,
    verify_password,
    create_jwt_token,
    require_student_auth,
    optional_student_auth
)

router = APIRouter(prefix="/auth", tags=["Student Authentication"])

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

@router.post("/register")
async def student_register(
    payload: dict = Body(...),
    response: Response = None,
    db: AsyncSession = Depends(get_db_dependency)
):
    """Registers a new student account, grants access to active curriculum, and sets session cookie."""
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")
    confirm_password = payload.get("confirm_password", "")

    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Please enter your full name.")

    if not email or not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    if not password or len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long.")

    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    # Check if student already exists
    existing = await db.execute(select(Student).where(Student.email == email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="An account with this email address already exists. Please log in.")

    # Create student
    student = Student(
        name=name,
        email=email,
        password_hash=hash_password(password),
        status="ACTIVE",
        created_at=datetime.utcnow(),
        last_login_at=datetime.utcnow()
    )
    db.add(student)
    await db.flush()

    # Automatically grant access to active catalog batches
    active_batches = (await db.execute(select(Batch).where(Batch.status == "ACTIVE"))).scalars().all()
    for b in active_batches:
        db.add(StudentBatchAccess(student_id=student.id, batch_id=b.id, status="ACTIVE"))
    await db.flush()

    # Generate JWT token
    token = create_jwt_token({
        "sub": student.id,
        "email": student.email,
        "name": student.name,
        "role": "STUDENT"
    }, expires_in=86400 * 30)

    if response:
        response.set_cookie(
            key="student_token",
            value=token,
            httponly=True,
            max_age=86400 * 30,
            samesite="lax",
            path="/"
        )

    return {
        "status": "success",
        "ok": True,
        "token": token,
        "student": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "created_at": student.created_at.isoformat() if student.created_at else None
        }
    }

@router.post("/login")
async def student_login(
    payload: dict = Body(...),
    response: Response = None,
    db: AsyncSession = Depends(get_db_dependency)
):
    """Authenticates student and issues session token."""
    email = payload.get("email", "").strip().lower()
    password = payload.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    res = await db.execute(select(Student).where(Student.email == email))
    student = res.scalar_one_or_none()

    if not student or not verify_password(password, student.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if student.status != "ACTIVE":
        raise HTTPException(status_code=403, detail="Your account has been deactivated. Please contact support.")

    # Update last login
    student.last_login_at = datetime.utcnow()
    await db.flush()

    token = create_jwt_token({
        "sub": student.id,
        "email": student.email,
        "name": student.name,
        "role": "STUDENT"
    }, expires_in=86400 * 30)

    if response:
        response.set_cookie(
            key="student_token",
            value=token,
            httponly=True,
            max_age=86400 * 30,
            samesite="lax",
            path="/"
        )

    return {
        "status": "success",
        "token": token,
        "student": {
            "id": student.id,
            "name": student.name,
            "email": student.email,
            "created_at": student.created_at.isoformat() if student.created_at else None
        }
    }

@router.get("/me")
async def get_current_student_profile(
    student: Student = Depends(require_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Returns profile and enrolled batch identifiers for the authenticated student."""
    access_stmt = select(StudentBatchAccess).where(
        and_(
            StudentBatchAccess.student_id == student.id,
            StudentBatchAccess.status == "ACTIVE"
        )
    )
    access_res = await db.execute(access_stmt)
    enrolled_batch_ids = [a.batch_id for a in access_res.scalars().all()]

    return {
        "id": student.id,
        "name": student.name,
        "email": student.email,
        "status": student.status,
        "created_at": student.created_at.isoformat() if student.created_at else None,
        "last_login_at": student.last_login_at.isoformat() if student.last_login_at else None,
        "enrolled_batches_count": len(enrolled_batch_ids),
        "enrolled_batch_ids": enrolled_batch_ids
    }

@router.post("/logout")
async def student_logout(response: Response = None):
    """Clears student session cookie."""
    if response:
        response.delete_cookie(key="student_token", path="/")
    return {"status": "success", "message": "Logged out successfully"}

@router.post("/change-password")
async def change_password(
    payload: dict = Body(...),
    student: Student = Depends(require_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Updates password for authenticated student."""
    old_password = payload.get("old_password", "")
    new_password = payload.get("new_password", "")

    if not verify_password(old_password, student.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters.")

    student.password_hash = hash_password(new_password)
    await db.flush()
    return {"status": "success", "message": "Password updated successfully"}

@router.get("/my-batches")
async def get_my_batches(
    student: Student = Depends(require_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Lists batches enrolled by the authenticated student."""
    stmt = (
        select(Batch)
        .join(StudentBatchAccess, StudentBatchAccess.batch_id == Batch.id)
        .options(selectinload(Batch.app), selectinload(Batch.subjects))
        .where(
            and_(
                StudentBatchAccess.student_id == student.id,
                StudentBatchAccess.status == "ACTIVE",
                Batch.status == "ACTIVE"
            )
        )
    )
    res = await db.execute(stmt)
    batches = res.scalars().all()

    return [
        {
            "id": b.id,
            "name": b.name,
            "slug": b.slug,
            "category": b.category,
            "branch": b.branch,
            "semester": b.semester,
            "academic_year": b.academic_year,
            "thumbnail_url": b.thumbnail_url,
            "app_name": b.app.name if b.app else "Course Wallah",
            "app_slug": b.app.slug if b.app else "courses",
            "subject_count": len(b.subjects) if b.subjects else 0
        }
        for b in batches
    ]

@router.post("/enroll/{batch_identifier}")
async def enroll_in_batch(
    batch_identifier: str,
    student: Student = Depends(require_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Enrolls the student into a batch by slug or UUID."""
    # Lookup batch
    stmt = select(Batch).where(
        and_(
            (Batch.id == batch_identifier) | (Batch.slug == batch_identifier),
            Batch.status == "ACTIVE"
        )
    )
    res = await db.execute(stmt)
    batch = res.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    access_stmt = select(StudentBatchAccess).where(
        and_(
            StudentBatchAccess.student_id == student.id,
            StudentBatchAccess.batch_id == batch.id
        )
    )
    access = (await db.execute(access_stmt)).scalar_one_or_none()
    if not access:
        access = StudentBatchAccess(
            student_id=student.id,
            batch_id=batch.id,
            status="ACTIVE",
            granted_at=datetime.utcnow()
        )
        db.add(access)
    else:
        access.status = "ACTIVE"

    await db.flush()
    return {"status": "success", "message": f"Successfully enrolled in {batch.name}", "batch_slug": batch.slug}

@router.post("/progress")
async def update_learning_progress(
    payload: dict = Body(...),
    student: Student = Depends(require_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Records video playback progress or lecture completion."""
    lecture_id = payload.get("lecture_id")
    playback_seconds = float(payload.get("playback_seconds", 0.0))
    completed = bool(payload.get("completed", False))

    if not lecture_id:
        raise HTTPException(status_code=400, detail="lecture_id is required")

    stmt = select(StudentActivity).where(
        and_(
            StudentActivity.student_id == student.id,
            StudentActivity.lecture_id == lecture_id
        )
    )
    activity = (await db.execute(stmt)).scalar_one_or_none()
    if not activity:
        activity = StudentActivity(
            student_id=student.id,
            lecture_id=lecture_id,
            playback_seconds=playback_seconds,
            completed=completed,
            last_accessed_at=datetime.utcnow()
        )
        db.add(activity)
    else:
        activity.playback_seconds = playback_seconds
        activity.completed = activity.completed or completed
        activity.last_accessed_at = datetime.utcnow()

    await db.flush()
    return {"status": "success"}

@router.get("/progress")
async def get_learning_progress(
    student: Student = Depends(require_student_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Retrieves recent lecture activities for the student."""
    stmt = (
        select(StudentActivity)
        .options(selectinload(StudentActivity.lecture).selectinload(Lecture.batch))
        .where(StudentActivity.student_id == student.id)
        .order_by(StudentActivity.last_accessed_at.desc())
        .limit(20)
    )
    res = await db.execute(stmt)
    activities = res.scalars().all()

    return [
        {
            "lecture_id": a.lecture_id,
            "lecture_title": a.lecture.title if a.lecture else "",
            "lecture_index": a.lecture.lecture_index if a.lecture else 0,
            "batch_name": a.lecture.batch.name if a.lecture and a.lecture.batch else "",
            "batch_slug": a.lecture.batch.slug if a.lecture and a.lecture.batch else "",
            "playback_seconds": a.playback_seconds,
            "completed": a.completed,
            "last_accessed_at": a.last_accessed_at.isoformat() if a.last_accessed_at else None
        }
        for a in activities
    ]
