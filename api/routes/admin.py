import re
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Body, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import (
    App,
    Batch,
    Subject,
    Folder,
    Lecture,
    Video,
    PDF,
    Job,
    JobStatus,
    PublicationStatus,
    WatermarkProfile,
    AuditLog,
    Student,
    StudentBatchAccess,
    SupportTicket
)
from api.auth import require_admin_auth, create_jwt_token
from config.settings import ADMIN_USERNAME, ADMIN_PASSWORD, DOWNLOADS_DIR
from validators.image_validator import validate_image_url
from engines.youtube_uploader import YouTubeUploader
from engines.youtube_account_manager import YouTubeAccountManager
from engines.job_engine import ContentProcessingEngine

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/login")
async def admin_login(payload: dict = Body(...), response: Response = None):
    """Authenticates admin and returns signed JWT."""
    username = payload.get("username", "")
    password = payload.get("password", "")

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        token = create_jwt_token({"sub": username, "role": "ADMIN"}, expires_in=86400 * 7)
        if response:
            response.set_cookie(
                key="admin_token",
                value=token,
                httponly=True,
                max_age=86400 * 7,
                samesite="lax"
            )
        return {"status": "success", "token": token, "username": username}

    raise HTTPException(status_code=401, detail="Invalid admin credentials")

@router.get("/stats")
async def get_admin_stats(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """Returns platform summary metrics for Admin Dashboard."""
    total_apps = (await db.execute(select(func.count(App.id)))).scalar() or 0
    total_batches = (await db.execute(select(func.count(Batch.id)))).scalar() or 0
    total_subjects = (await db.execute(select(func.count(Subject.id)))).scalar() or 0
    total_lectures = (await db.execute(select(func.count(Lecture.id)))).scalar() or 0
    total_videos = (await db.execute(select(func.count(Video.id)))).scalar() or 0
    total_pdfs = (await db.execute(select(func.count(PDF.id)))).scalar() or 0
    
    published_lectures = (
        await db.execute(select(func.count(Lecture.id)).where(Lecture.publication_status == PublicationStatus.PUBLISHED))
    ).scalar() or 0

    active_jobs = (
        await db.execute(select(func.count(Job.id)).where(Job.status.in_([JobStatus.DOWNLOADING, JobStatus.WATERMARKING, JobStatus.YOUTUBE_UPLOADING, JobStatus.B2_UPLOADING])))
    ).scalar() or 0

    failed_jobs = (
        await db.execute(select(func.count(Job.id)).where(Job.status == JobStatus.FAILED))
    ).scalar() or 0

    return {
        "apps": total_apps,
        "batches": total_batches,
        "subjects": total_subjects,
        "lectures": total_lectures,
        "published_lectures": published_lectures,
        "videos": total_videos,
        "pdfs": total_pdfs,
        "active_jobs": active_jobs,
        "failed_jobs": failed_jobs
    }

@router.get("/apps")
async def list_admin_apps(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(App).order_by(App.name)
    res = await db.execute(stmt)
    apps = res.scalars().all()
    return [
        {
            "id": a.id,
            "name": a.name,
            "slug": a.slug,
            "description": a.description,
            "icon_url": a.icon_url,
            "status": a.status
        }
        for a in apps
    ]

@router.post("/apps")
async def create_admin_app(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="App name is required")
    
    icon_url = payload.get("icon_url")
    if icon_url:
        is_valid, reason, ct = validate_image_url(icon_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid image URL: {reason}")

    slug = slugify(name)
    app = App(
        name=name,
        slug=slug,
        description=payload.get("description"),
        icon_url=icon_url,
        status=payload.get("status", "ACTIVE")
    )
    db.add(app)
    await db.flush()
    return {"status": "success", "message": "App created", "app_id": app.id, "app": {"id": app.id, "name": app.name, "slug": app.slug, "icon_url": app.icon_url}}

@router.put("/apps/{app_id}")
async def update_admin_app(
    app_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    app = await db.get(App, app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    if "name" in payload:
        app.name = payload["name"]
        app.slug = slugify(payload["name"])
    if "description" in payload:
        app.description = payload["description"]
    if "icon_url" in payload:
        icon_url = payload["icon_url"]
        if icon_url:
            is_valid, reason, ct = validate_image_url(icon_url)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid image URL: {reason}")
        app.icon_url = icon_url
    if "status" in payload:
        app.status = payload["status"]

    await db.flush()
    return {"status": "success", "message": "App updated", "app_id": app.id}

@router.get("/batches")
async def list_admin_batches(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(Batch).options(selectinload(Batch.app), selectinload(Batch.subjects)).order_by(Batch.created_at.desc())
    res = await db.execute(stmt)
    batches = res.scalars().all()
    return [
        {
            "id": b.id,
            "name": b.name,
            "slug": b.slug,
            "app_name": b.app.name if b.app else "Unknown",
            "category": b.category,
            "branch": b.branch,
            "semester": b.semester,
            "academic_year": b.academic_year,
            "thumbnail_url": b.thumbnail_url,
            "status": b.status,
            "subject_count": len(b.subjects)
        }
        for b in batches
    ]

@router.post("/batches")
async def create_admin_batch(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Batch name is required")

    app_id = payload.get("app_id")
    if not app_id:
        first_app = (await db.execute(select(App).limit(1))).scalar_one_or_none()
        if not first_app:
            first_app = App(name="Course Wallah Engineering", slug="course-wallah-engineering")
            db.add(first_app)
            await db.flush()
        app_id = first_app.id

    thumb_url = payload.get("thumbnail_url")
    if thumb_url:
        is_valid, reason, ct = validate_image_url(thumb_url)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid thumbnail URL: {reason}")

    slug_base = re.sub(r'[^a-zA-Z0-9]+', '-', name.lower()).strip('-')
    if not slug_base:
        slug_base = f"batch-{int(time.time())}"
    slug = slug_base

    existing = (await db.execute(select(Batch).where(Batch.slug == slug))).scalar_one_or_none()
    if existing:
        slug = f"{slug_base}-{int(time.time())}"

    batch = Batch(
        app_id=app_id,
        name=name,
        slug=slug,
        category=payload.get("category", "Semester"),
        branch=payload.get("branch", "General"),
        semester=payload.get("semester", "Semester 1"),
        academic_year=payload.get("academic_year", "2026"),
        thumbnail_url=thumb_url,
        status=payload.get("status", "ACTIVE")
    )
    db.add(batch)
    await db.flush()
    return {
        "status": "success",
        "message": "Batch created successfully",
        "id": batch.id,
        "batch_id": batch.id,
        "name": batch.name,
        "slug": batch.slug,
        "thumbnail_url": batch.thumbnail_url
    }

@router.delete("/batches/{batch_id}")
async def delete_admin_batch(
    batch_id: str,
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    await db.delete(batch)
    await db.flush()
    return {"status": "success", "message": f"Batch '{batch.name}' deleted"}

@router.put("/batches/{batch_id}")
async def update_batch(
    batch_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    if "name" in payload:
        batch.name = payload["name"]
    if "category" in payload:
        batch.category = payload["category"]
    if "branch" in payload:
        batch.branch = payload["branch"]
    if "semester" in payload:
        batch.semester = payload["semester"]
    if "academic_year" in payload:
        batch.academic_year = payload["academic_year"]
    if "thumbnail_url" in payload:
        thumb_url = payload["thumbnail_url"]
        if thumb_url:
            is_valid, reason, ct = validate_image_url(thumb_url)
            if not is_valid:
                raise HTTPException(status_code=400, detail=f"Invalid thumbnail URL: {reason}")
        batch.thumbnail_url = thumb_url
    if "status" in payload:
        batch.status = payload["status"]
    
    await db.flush()
    return {
        "status": "success",
        "message": "Batch updated",
        "id": batch.id,
        "batch_id": batch.id,
        "name": batch.name,
        "thumbnail_url": batch.thumbnail_url,
        "status": batch.status
    }

@router.put("/subjects/{subject_id}")
async def update_subject(
    subject_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    if "name" in payload:
        subject.name = payload["name"]
    if "code" in payload:
        subject.code = payload["code"]
    if "sort_order" in payload:
        subject.sort_order = int(payload["sort_order"])
    if "status" in payload:
        subject.status = payload["status"]
    
    await db.flush()
    return {"status": "success", "message": "Subject updated", "subject_id": subject.id}

@router.put("/folders/{folder_id}")
async def update_folder(
    folder_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    folder = await db.get(Folder, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    
    if "name" in payload:
        folder.name = payload["name"]
    if "unit_number" in payload:
        folder.unit_number = payload["unit_number"]
    if "sort_order" in payload:
        folder.sort_order = int(payload["sort_order"])
    if "status" in payload:
        folder.status = payload["status"]
    
    await db.flush()
    return {"status": "success", "message": "Folder updated", "folder_id": folder.id}

@router.put("/lectures/{lecture_id}")
async def update_lecture(
    lecture_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    lecture = await db.get(Lecture, lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    
    if "title" in payload:
        lecture.title = payload["title"]
    if "lecture_index" in payload:
        lecture.lecture_index = int(payload["lecture_index"])
    if "sort_order" in payload:
        lecture.sort_order = int(payload["sort_order"])
    if "publication_status" in payload:
        lecture.publication_status = PublicationStatus(payload["publication_status"])
    
    await db.flush()
    return {"status": "success", "message": "Lecture updated", "lecture_id": lecture.id}

@router.post("/lectures/{lecture_id}/pdf")
async def attach_or_replace_pdf(
    lecture_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    lecture = await db.get(Lecture, lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    
    b2_key = payload.get("b2_object_key")
    file_name = payload.get("file_name", "lecture.pdf")
    file_size = payload.get("file_size", 0)
    page_count = payload.get("page_count", 0)
    b2_bucket = payload.get("b2_bucket", "course-wallah-pdfs")

    if not b2_key:
        raise HTTPException(status_code=400, detail="b2_object_key is required")

    stmt = select(PDF).where(PDF.lecture_id == lecture_id)
    res = await db.execute(stmt)
    pdf = res.scalar_one_or_none()
    if not pdf:
        pdf = PDF(
            lecture_id=lecture_id,
            b2_object_key=b2_key,
            b2_bucket=b2_bucket,
            file_name=file_name,
            file_size=file_size,
            page_count=page_count
        )
        db.add(pdf)
    else:
        pdf.b2_object_key = b2_key
        pdf.b2_bucket = b2_bucket
        pdf.file_name = file_name
        pdf.file_size = file_size
        pdf.page_count = page_count

    lecture.has_pdf = True
    await db.flush()
    return {"status": "success", "message": "PDF attached/replaced successfully", "pdf_id": pdf.id}

@router.get("/jobs")
async def list_jobs(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(Job).order_by(Job.created_at.desc()).limit(50)
    res = await db.execute(stmt)
    jobs = res.scalars().all()
    return [
        {
            "id": j.id,
            "bot_id": j.bot_id,
            "batch_id": j.batch_id,
            "lecture_id": j.lecture_id,
            "provider": j.provider,
            "status": j.status.value if hasattr(j.status, "value") else str(j.status),
            "progress_percent": j.progress_percent,
            "current_step": j.current_step,
            "error_message": j.error_message,
            "created_at": j.created_at.isoformat() if j.created_at else None
        }
        for j in jobs
    ]

@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job.status = JobStatus.QUEUED
    job.error_message = None
    job.retry_count = (job.retry_count or 0) + 1
    job.progress_percent = 0.0
    await db.flush()
    return {"status": "success", "message": f"Job {job_id} queued for retry", "retry_count": job.retry_count}

@router.get("/watermark")
async def get_watermark_profile(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(WatermarkProfile).where(WatermarkProfile.is_default == True)
    res = await db.execute(stmt)
    prof = res.scalar_one_or_none()
    if not prof:
        prof = WatermarkProfile(
            name="Default Moving Watermark",
            text="COURSE WALLAH",
            opacity=0.45,
            is_default=True
        )
        db.add(prof)
        await db.flush()

    return {
        "id": prof.id,
        "name": prof.name,
        "text": prof.text,
        "opacity": prof.opacity,
        "animation_mode": prof.animation_mode.value if hasattr(prof.animation_mode, "value") else str(prof.animation_mode),
        "movement_interval": prof.movement_interval,
        "crf": prof.crf,
        "enabled": prof.enabled
    }

@router.put("/watermark")
async def update_watermark_profile(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(WatermarkProfile).where(WatermarkProfile.is_default == True)
    res = await db.execute(stmt)
    prof = res.scalar_one_or_none()
    if not prof:
        prof = WatermarkProfile(name="Default Moving Watermark", is_default=True)
        db.add(prof)

    if "text" in payload:
        prof.text = payload["text"]
    if "opacity" in payload:
        prof.opacity = float(payload["opacity"])
    if "movement_interval" in payload:
        prof.movement_interval = int(payload["movement_interval"])
    if "crf" in payload:
        prof.crf = int(payload["crf"])
    if "enabled" in payload:
        prof.enabled = bool(payload["enabled"])

    await db.flush()
    return {"status": "success", "message": "Watermark configuration updated"}

@router.post("/lectures/{lecture_id}/toggle-publish")
async def toggle_lecture_publish(
    lecture_id: str,
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    lecture = await db.get(Lecture, lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    if lecture.publication_status == PublicationStatus.PUBLISHED:
        lecture.publication_status = PublicationStatus.UNPUBLISHED
    else:
        lecture.publication_status = PublicationStatus.PUBLISHED

    await db.flush()
    return {
        "lecture_id": lecture.id,
        "new_status": lecture.publication_status.value
    }

@router.get("/youtube")
async def get_youtube_diagnostics(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    """
    Returns complete diagnostics for YouTube publishing channel,
    including official API channel health, DB upload history,
    failed upload counts, and blocked checkpoints queue.
    """
    # 1. Fetch channel diagnostics from official API (or TTL cache)
    channel_diag = await YouTubeUploader.get_channel_diagnostics(force_refresh=False)

    # 2. Query Platform DB Upload History
    now = datetime.utcnow()
    t_24h = now - timedelta(days=1)
    t_7d = now - timedelta(days=7)
    t_30d = now - timedelta(days=30)

    total_uploads = (await db.execute(select(func.count(Video.id)))).scalar() or 0
    uploads_24h = (await db.execute(select(func.count(Video.id)).where(Video.created_at >= t_24h))).scalar() or 0
    uploads_7d = (await db.execute(select(func.count(Video.id)).where(Video.created_at >= t_7d))).scalar() or 0
    uploads_30d = (await db.execute(select(func.count(Video.id)).where(Video.created_at >= t_30d))).scalar() or 0

    latest_video_stmt = select(Video.created_at).order_by(desc(Video.created_at)).limit(1)
    latest_video_time = (await db.execute(latest_video_stmt)).scalar_one_or_none()

    # Query Failed Upload Attempts from Jobs
    failed_jobs_count = (await db.execute(
        select(func.count(Job.id)).where(Job.status == JobStatus.FAILED)
    )).scalar() or 0

    latest_failed_job_stmt = select(Job).where(Job.error_message.isnot(None)).order_by(desc(Job.updated_at)).limit(1)
    latest_failed_job = (await db.execute(latest_failed_job_stmt)).scalar_one_or_none()
    last_yt_error = latest_failed_job.error_message if latest_failed_job else None

    # 3. Inspect Disk Checkpoint Directory for Blocked Queues
    checkpoint_base = Path(DOWNLOADS_DIR) / "checkpoints"
    blocked_checkpoints = []
    last_limit_timestamp = None

    if checkpoint_base.exists():
        for b_dir in checkpoint_base.iterdir():
            if b_dir.is_dir():
                batch_id_str = b_dir.name
                batch_obj = await db.get(Batch, batch_id_str)
                batch_name_display = batch_obj.name if batch_obj else f"Batch {batch_id_str[:8]}"

                for lec_dir in b_dir.iterdir():
                    if lec_dir.is_dir():
                        ckpt_file = lec_dir / "checkpoint.json"
                        if ckpt_file.exists():
                            try:
                                ckpt_json = json.loads(ckpt_file.read_text("utf-8"))
                                ts = ckpt_json.get("timestamp")
                                if ts and (last_limit_timestamp is None or ts > last_limit_timestamp):
                                    last_limit_timestamp = ts

                                blocked_checkpoints.append({
                                    "batch_id": batch_id_str,
                                    "batch_name": batch_name_display,
                                    "lecture_index": ckpt_json.get("index"),
                                    "lecture_title": ckpt_json.get("title"),
                                    "stage": ckpt_json.get("stage", "WATERMARKED_READY_FOR_UPLOAD"),
                                    "reason": ckpt_json.get("reason", "uploadLimitExceeded"),
                                    "size_mb": round((ckpt_json.get("size", 0)) / (1024 * 1024), 2),
                                    "duration_sec": round(ckpt_json.get("duration", 0), 1),
                                    "created_at": datetime.utcfromtimestamp(ts).isoformat() if ts else None
                                })
                            except Exception:
                                pass

    # 4. Current Publishing / Active Queue Count
    active_publishing_queue = (await db.execute(
        select(func.count(Job.id)).where(
            Job.status.in_([JobStatus.QUEUED, JobStatus.DOWNLOADING, JobStatus.WATERMARKING, JobStatus.YOUTUBE_UPLOADING])
        )
    )).scalar() or 0

    # 5. Multi-Account Manager Diagnostics
    account_mgr_diag = await YouTubeAccountManager.get_diagnostics()

    return {
        "channel": channel_diag,
        "accounts_manager": account_mgr_diag,
        "platform_upload_history": {
            "label": "Platform upload history (Tracked in database)",
            "total_recorded_uploads": total_uploads,
            "uploads_last_24h": uploads_24h,
            "uploads_last_7d": uploads_7d,
            "uploads_last_30d": uploads_30d,
            "last_successful_upload_at": latest_video_time.isoformat() if latest_video_time else None,
            "failed_upload_attempts": failed_jobs_count,
            "last_youtube_error": last_yt_error,
            "last_upload_limit_exceeded_at": (
                datetime.utcfromtimestamp(last_limit_timestamp).isoformat() if last_limit_timestamp else None
            )
        },
        "queues": {
            "publishing_queue_count": active_publishing_queue,
            "blocked_checkpoints_count": len(blocked_checkpoints),
            "blocked_checkpoints": blocked_checkpoints
        },
        "limits_policy": {
            "label": "YouTube's actual channel upload limit (External Google Enforced)",
            "error_classification": {
                "uploadLimitExceeded": "CHANNEL_UPLOAD_LIMIT (Gracefully blocked & checkpointed without retry loop)",
                "quotaExceeded": "API_PROJECT_QUOTA (Daily project API units exhausted)",
                "AUTH_ERROR": "AUTH_ERROR (OAuth invalid_grant / unauthorized_client)",
                "TEMPORARY": "TEMPORARY (429 / 5xx / transient network retryable)",
                "PERMANENT": "PERMANENT (Non-retryable invalid media or request format)"
            },
            "disclaimer": "DB count is our record of uploaded videos and does NOT represent YouTube's remaining allowance."
        }
    }

@router.get("/youtube/accounts")
async def get_admin_youtube_accounts(
    admin: dict = Depends(require_admin_auth)
):
    """Returns sanitized list of configured YouTube accounts (without secrets/tokens)."""
    return await YouTubeAccountManager.get_diagnostics()

@router.post("/youtube/refresh")
async def refresh_youtube_diagnostics(
    admin: dict = Depends(require_admin_auth)
):
    """Manually forces a fresh YouTube Channel API call, bypassing the 60s TTL cache."""
    refreshed = await YouTubeUploader.get_channel_diagnostics(force_refresh=True)
    return {"status": "success", "channel": refreshed}

@router.post("/youtube/pause")
async def pause_all_youtube_uploads(
    admin: dict = Depends(require_admin_auth)
):
    """Pauses all active batch upload controllers."""
    paused = 0
    for ctrl in ContentProcessingEngine._active_batch_controllers.values():
        if not ctrl.is_paused:
            ctrl.pause()
            paused += 1
    return {"status": "success", "paused_controllers": paused}

@router.post("/youtube/resume/{batch_id}")
async def resume_blocked_batch(
    batch_id: str,
    admin: dict = Depends(require_admin_auth)
):
    """Signals any active or paused controller to resume publishing checkpointed lectures."""
    resumed_jobs = []
    for job_id, controller in ContentProcessingEngine._active_batch_controllers.items():
        if controller.batch_id == batch_id or batch_id == "all":
            controller.resume()
            resumed_jobs.append(job_id)

    return {
        "status": "success",
        "batch_id": batch_id,
        "resumed_controllers": resumed_jobs,
        "message": f"Resumed {len(resumed_jobs)} active batch controller(s)."
    }


# ==========================================
# STUDENT IDENTITY & BATCH ENROLLMENTS
# ==========================================

@router.get("/students")
async def list_admin_students(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(Student).options(selectinload(Student.batch_accesses).selectinload(StudentBatchAccess.batch)).order_by(Student.created_at.desc())
    res = await db.execute(stmt)
    students = res.scalars().all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "email": s.email,
            "status": s.status,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "enrolled_batches": [
                {
                    "batch_id": ba.batch_id,
                    "batch_name": ba.batch.name if ba.batch else "Unknown Batch",
                    "status": ba.status,
                    "granted_at": ba.granted_at.isoformat() if ba.granted_at else None
                }
                for ba in s.batch_accesses
            ]
        }
        for s in students
    ]

@router.post("/students")
async def create_admin_student(
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    name = payload.get("name", "").strip()
    email = payload.get("email", "").strip()
    batch_id = payload.get("batch_id")

    if not name or not email:
        raise HTTPException(status_code=400, detail="Name and Email/Phone are required")

    existing = (await db.execute(select(Student).where(Student.email == email))).scalar_one_or_none()
    if existing:
        student = existing
    else:
        student = Student(
            name=name,
            email=email,
            password_hash="student_default_pass",
            status="ACTIVE"
        )
        db.add(student)
        await db.flush()

    if batch_id:
        existing_acc = (await db.execute(
            select(StudentBatchAccess).where(
                and_(StudentBatchAccess.student_id == student.id, StudentBatchAccess.batch_id == batch_id)
            )
        )).scalar_one_or_none()
        if not existing_acc:
            acc = StudentBatchAccess(
                student_id=student.id,
                batch_id=batch_id,
                status="ACTIVE"
            )
            db.add(acc)
            await db.flush()

    return {
        "status": "success",
        "message": f"Student '{name}' added successfully",
        "id": student.id,
        "student_id": student.id,
        "name": student.name,
        "email": student.email
    }

@router.post("/students/{student_id}/enroll")
async def enroll_student(
    student_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    batch_id = payload.get("batch_id")
    if not batch_id:
        raise HTTPException(status_code=400, detail="batch_id is required")

    student = await db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    existing_acc = (await db.execute(
        select(StudentBatchAccess).where(
            and_(StudentBatchAccess.student_id == student_id, StudentBatchAccess.batch_id == batch_id)
        )
    )).scalar_one_or_none()

    if not existing_acc:
        acc = StudentBatchAccess(student_id=student_id, batch_id=batch_id, status="ACTIVE")
        db.add(acc)
    else:
        existing_acc.status = "ACTIVE"

    await db.flush()
    return {"status": "success", "message": f"Student enrolled in '{batch.name}'", "student_id": student_id, "batch_id": batch_id}

@router.delete("/students/{student_id}/batches/{batch_id}")
async def unenroll_student(
    student_id: str,
    batch_id: str,
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    acc = (await db.execute(
        select(StudentBatchAccess).where(
            and_(StudentBatchAccess.student_id == student_id, StudentBatchAccess.batch_id == batch_id)
        )
    )).scalar_one_or_none()

    if acc:
        await db.delete(acc)
        await db.flush()

    return {"status": "success", "message": "Student unenrolled from batch"}

@router.put("/students/{student_id}/status")
async def toggle_student_status(
    student_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    student = await db.get(Student, student_id)
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    status = payload.get("status", "ACTIVE")
    student.status = status
    await db.flush()
    return {"status": "success", "message": f"Student status updated to {status}", "id": student.id, "student_id": student.id, "status": status}


# ==========================================
# STUDENT PROBLEMS & SUPPORT DESK
# ==========================================

@router.get("/tickets")
async def list_support_tickets(
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    stmt = select(SupportTicket).options(selectinload(SupportTicket.batch)).order_by(SupportTicket.created_at.desc())
    res = await db.execute(stmt)
    tickets = res.scalars().all()
    return [
        {
            "id": t.id,
            "ticket_id": t.id,
            "student_name": t.student_name,
            "student_contact": t.student_contact,
            "batch_name": t.batch.name if t.batch else "General",
            "subject": t.subject,
            "category": t.category,
            "description": t.description,
            "admin_note": t.admin_note,
            "status": t.status,
            "priority": t.priority,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None
        }
        for t in tickets
    ]

@router.post("/tickets")
async def create_support_ticket(
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db_dependency)
):
    name = payload.get("student_name") or payload.get("name", "Student")
    contact = payload.get("student_contact") or payload.get("email", "N/A")
    subject = payload.get("subject", "General Inquiry")
    description = payload.get("description") or payload.get("message", "")
    category = payload.get("category", "GENERAL")
    batch_id = payload.get("batch_id")

    ticket = SupportTicket(
        student_name=name,
        student_contact=contact,
        batch_id=batch_id,
        subject=subject,
        category=category,
        description=description,
        status="PENDING",
        priority=payload.get("priority", "MEDIUM")
    )
    db.add(ticket)
    await db.flush()
    return {
        "status": "success",
        "message": "Ticket created",
        "id": ticket.id,
        "ticket_id": ticket.id,
        "subject": ticket.subject,
        "priority": ticket.priority
    }

@router.put("/tickets/{ticket_id}")
async def update_support_ticket(
    ticket_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    if "status" in payload:
        ticket.status = payload["status"]
        if payload["status"] == "RESOLVED":
            ticket.resolved_at = datetime.utcnow()
    if "admin_note" in payload:
        ticket.admin_note = payload["admin_note"]
    if "priority" in payload:
        ticket.priority = payload["priority"]

    await db.flush()
    return {
        "status": "success",
        "message": "Ticket updated",
        "id": ticket.id,
        "ticket_id": ticket.id,
        "status": ticket.status,
        "admin_note": ticket.admin_note,
        "priority": ticket.priority
    }

@router.delete("/tickets/{ticket_id}")
async def delete_support_ticket(
    ticket_id: str,
    admin: dict = Depends(require_admin_auth),
    db: AsyncSession = Depends(get_db_dependency)
):
    ticket = await db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await db.delete(ticket)
    await db.flush()
    return {"status": "success", "message": "Ticket deleted"}


