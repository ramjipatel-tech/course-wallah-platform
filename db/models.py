import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    Float,
    Boolean,
    Text,
    DateTime,
    ForeignKey,
    Enum,
    UniqueConstraint,
    Index,
    JSON
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def generate_uuid() -> str:
    return str(uuid.uuid4())

# ==========================================
# ENUMS
# ==========================================

class PublicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PROCESSING = "PROCESSING"
    READY = "READY"
    PUBLISHED = "PUBLISHED"
    UNPUBLISHED = "UNPUBLISHED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"

class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    PROCESSING = "PROCESSING"
    WATERMARKING = "WATERMARKING"
    WATERMARKED = "WATERMARKED"
    THUMBNAIL_READY = "THUMBNAIL_READY"
    YOUTUBE_UPLOADING = "YOUTUBE_UPLOADING"
    YOUTUBE_UPLOADED = "YOUTUBE_UPLOADED"
    WAITING_FOR_YOUTUBE_ACCOUNT = "WAITING_FOR_YOUTUBE_ACCOUNT"
    PAUSED_YOUTUBE_LIMIT = "PAUSED_YOUTUBE_LIMIT"
    PDF_PROCESSING = "PDF_PROCESSING"
    B2_UPLOADING = "B2_UPLOADING"
    B2_UPLOADED = "B2_UPLOADED"
    DATABASE_SAVED = "DATABASE_SAVED"
    PLAYLIST_UPDATED = "PLAYLIST_UPDATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"

class YouTubeAccountStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    LIMIT_REACHED = "LIMIT_REACHED"
    AUTH_ERROR = "AUTH_ERROR"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class WatermarkAnimationMode(str, enum.Enum):
    SMOOTH_BOUNCE = "smooth_bounce"
    CONTINUOUS_DRIFT = "continuous_drift"
    CORNER_ROTATION = "corner_rotation"
    DIAGONAL_PAN = "diagonal_pan"
    FIXED = "fixed"

# ==========================================
# CORE CONTENT HIERARCHY
# ==========================================

class App(Base):
    __tablename__ = "apps"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False, unique=True, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    icon_url = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(32), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    batches = relationship("Batch", back_populates="app", cascade="all, delete-orphan")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    app_id = Column(String(64), ForeignKey("apps.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, index=True)
    category = Column(String(128), nullable=True) # e.g. B.Tech, SSC, UPSC
    branch = Column(String(128), nullable=True)   # e.g. CSE, ECE, Mechanical
    semester = Column(String(64), nullable=True)  # e.g. 3rd Semester, 1st Year
    academic_year = Column(String(64), nullable=True) # e.g. 2025-2026
    thumbnail_url = Column(String(512), nullable=True)
    video_quality_preference = Column(String(32), default="1080p")
    source_identifier = Column(String(255), nullable=True, index=True) # Raw batch identifier if any
    status = Column(String(32), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("app_id", "slug", name="uq_app_batch_slug"),
        Index("idx_batch_app_name", "app_id", "name"),
    )

    app = relationship("App", back_populates="batches")
    subjects = relationship("Subject", back_populates="batch", cascade="all, delete-orphan")
    playlists = relationship("Playlist", back_populates="batch", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="batch", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, index=True)
    code = Column(String(64), nullable=True)
    thumbnail_url = Column(String(512), nullable=True)
    sort_order = Column(Integer, default=0)
    status = Column(String(32), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("batch_id", "slug", name="uq_batch_subject_slug"),
    )

    batch = relationship("Batch", back_populates="subjects")
    folders = relationship("Folder", back_populates="subject", cascade="all, delete-orphan")
    playlists = relationship("Playlist", back_populates="subject", cascade="all, delete-orphan")


class Folder(Base):
    __tablename__ = "folders"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    subject_id = Column(String(64), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id = Column(String(64), ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, index=True)
    unit_number = Column(String(64), nullable=True) # e.g. "Unit 01", "Module 2"
    sort_order = Column(Integer, default=0)
    status = Column(String(32), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("subject_id", "parent_id", "slug", name="uq_folder_parent_slug"),
    )

    subject = relationship("Subject", back_populates="folders")
    parent = relationship("Folder", remote_side=[id], backref="subfolders")
    lectures = relationship("Lecture", back_populates="folder", cascade="all, delete-orphan")


class Lecture(Base):
    __tablename__ = "lectures"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    folder_id = Column(String(64), ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id = Column(String(64), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, index=True)
    lecture_index = Column(Integer, nullable=False, index=True) # e.g. 148
    source_url = Column(Text, nullable=True) # Normalized source video URL
    source_pdf_url = Column(Text, nullable=True) # Normalized source PDF URL
    provider = Column(String(64), nullable=True) # appx, spayee, youtube, etc.
    raw_reference = Column(Text, nullable=True) # Original line in TXT
    duration_seconds = Column(Integer, default=0)
    thumbnail_url = Column(String(512), nullable=True)
    has_video = Column(Boolean, default=False)
    has_pdf = Column(Boolean, default=False)
    publication_status = Column(Enum(PublicationStatus), default=PublicationStatus.DRAFT, index=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("folder_id", "lecture_index", name="uq_folder_lecture_index"),
        Index("idx_lecture_batch_idx", "batch_id", "lecture_index"),
    )

    folder = relationship("Folder", back_populates="lectures")
    subject = relationship("Subject")
    batch = relationship("Batch")
    video = relationship("Video", back_populates="lecture", uselist=False, cascade="all, delete-orphan")
    pdf = relationship("PDF", back_populates="lecture", uselist=False, cascade="all, delete-orphan")
    playlist_items = relationship("PlaylistItem", back_populates="lecture", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="lecture", cascade="all, delete-orphan")


# ==========================================
# MEDIA ASSETS
# ==========================================

class Video(Base):
    __tablename__ = "videos"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    lecture_id = Column(String(64), ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    youtube_video_id = Column(String(64), nullable=True, index=True) # YouTube Video ID
    youtube_channel_id = Column(String(64), nullable=True, index=True)
    youtube_account_id = Column(String(64), ForeignKey("youtube_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    youtube_url = Column(String(512), nullable=True)
    youtube_privacy = Column(String(32), default="unlisted")
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    duration = Column(Float, default=0.0)
    resolution = Column(String(32), nullable=True) # 1080p, 720p, etc.
    file_size = Column(BigInteger, default=0)
    is_split = Column(Boolean, default=False)
    watermarked = Column(Boolean, default=True)
    storage_type = Column(String(32), default="YOUTUBE")
    status = Column(String(32), default="READY")
    upload_completed_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lecture = relationship("Lecture", back_populates="video")
    parts = relationship("VideoPart", back_populates="video", cascade="all, delete-orphan")
    account = relationship("YouTubeAccount", backref="videos")



class VideoPart(Base):
    __tablename__ = "video_parts"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    video_id = Column(String(64), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    part_number = Column(Integer, nullable=False)
    youtube_video_id = Column(String(64), nullable=True)
    duration = Column(Float, default=0.0)
    file_size = Column(BigInteger, default=0)
    status = Column(String(32), default="READY")
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("video_id", "part_number", name="uq_video_part_num"),
    )

    video = relationship("Video", back_populates="parts")


class PDF(Base):
    __tablename__ = "pdfs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    lecture_id = Column(String(64), ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    b2_object_key = Column(String(512), nullable=False, unique=True, index=True)
    b2_bucket = Column(String(128), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(BigInteger, default=0)
    page_count = Column(Integer, default=0)
    watermarked = Column(Boolean, default=True)
    status = Column(String(32), default="READY")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lecture = relationship("Lecture", back_populates="pdf")


# ==========================================
# PLAYLISTS
# ==========================================

class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    subject_id = Column(String(64), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    total_lectures = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("subject_id", "slug", name="uq_subject_playlist_slug"),
    )

    subject = relationship("Subject", back_populates="playlists")
    batch = relationship("Batch", back_populates="playlists")
    items = relationship("PlaylistItem", back_populates="playlist", order_by="PlaylistItem.position", cascade="all, delete-orphan")


class PlaylistItem(Base):
    __tablename__ = "playlist_items"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    playlist_id = Column(String(64), ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False, index=True)
    lecture_id = Column(String(64), ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True)
    position = Column(Integer, nullable=False) # 1-based order in playlist
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("playlist_id", "lecture_id", name="uq_playlist_lecture"),
        UniqueConstraint("playlist_id", "position", name="uq_playlist_position"),
    )

    playlist = relationship("Playlist", back_populates="items")
    lecture = relationship("Lecture", back_populates="playlist_items")


# ==========================================
# WATERMARK PROFILES
# ==========================================

class WatermarkProfile(Base):
    __tablename__ = "watermark_profiles"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False, unique=True)
    is_default = Column(Boolean, default=False)
    enabled = Column(Boolean, default=True)
    text = Column(String(255), default="COURSE WALLAH")
    logo_path = Column(String(512), nullable=True)
    opacity = Column(Float, default=0.45)
    size_percent = Column(Float, default=0.15) # watermark relative scale
    animation_mode = Column(Enum(WatermarkAnimationMode), default=WatermarkAnimationMode.CONTINUOUS_DRIFT)
    movement_interval = Column(Integer, default=8) # seconds per cycle
    crf = Column(Integer, default=26)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==========================================
# JOB ENGINE & EXECUTION TRACKING
# ==========================================

class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    bot_id = Column(String(64), nullable=False, default="bot_1", index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    lecture_id = Column(String(64), ForeignKey("lectures.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(64), nullable=True)
    job_type = Column(String(64), default="LECTURE_INGESTION")
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED, index=True)
    current_step = Column(String(64), default="QUEUED")
    progress_percent = Column(Float, default=0.0)
    download_progress = Column(Float, default=0.0)
    watermark_progress = Column(Float, default=0.0)
    youtube_progress = Column(Float, default=0.0)
    pdf_progress = Column(Float, default=0.0)
    b2_progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    step_data = Column(JSON, default=dict)
    telegram_message_id = Column(Integer, nullable=True)
    telegram_chat_id = Column(BigInteger, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    batch = relationship("Batch", back_populates="jobs")
    lecture = relationship("Lecture", back_populates="jobs")
    steps = relationship("JobStep", back_populates="job", cascade="all, delete-orphan")


class JobStep(Base):
    __tablename__ = "job_steps"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    job_id = Column(String(64), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_name = Column(String(64), nullable=False)
    status = Column(String(32), default="PENDING")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    log_output = Column(Text, nullable=True)

    job = relationship("Job", back_populates="steps")


# ==========================================
# YOUTUBE UPLOADS & ACCOUNTS
# ==========================================

class YouTubeAccount(Base):
    __tablename__ = "youtube_accounts"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(128), nullable=False, default="YouTube Account", index=True)
    account_name = Column(String(128), nullable=True, default="YouTube Account")
    client_id = Column(String(255), nullable=True)
    client_secret = Column(String(255), nullable=True)
    refresh_token = Column(Text, nullable=True)
    channel_id = Column(String(64), nullable=True, index=True)
    channel_title = Column(String(255), nullable=True)
    status = Column(String(32), default=YouTubeAccountStatus.ACTIVE.value, index=True)
    is_active = Column(Boolean, default=True)
    uploads_today = Column(Integer, default=0)
    upload_count_today = Column(Integer, default=0)
    last_upload_at = Column(DateTime, nullable=True)
    limit_detected_at = Column(DateTime, nullable=True)
    cooldown_until = Column(DateTime, nullable=True)
    priority = Column(Integer, default=1, index=True)
    last_error = Column(Text, nullable=True)
    last_error_type = Column(String(64), nullable=True)
    quota_reset_date = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    uploads = relationship("YouTubeUpload", back_populates="account", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        if "name" in kwargs and "account_name" not in kwargs:
            kwargs["account_name"] = kwargs["name"]
        elif "account_name" in kwargs and "name" not in kwargs:
            kwargs["name"] = kwargs["account_name"]
        if "uploads_today" in kwargs and "upload_count_today" not in kwargs:
            kwargs["upload_count_today"] = kwargs["uploads_today"]
        super().__init__(**kwargs)


class YouTubeUpload(Base):
    __tablename__ = "youtube_uploads"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    job_id = Column(String(64), nullable=True, index=True)
    lecture_id = Column(String(64), ForeignKey("lectures.id", ondelete="SET NULL"), nullable=True, index=True)
    video_id = Column(String(64), ForeignKey("videos.id", ondelete="SET NULL"), nullable=True, index=True)
    account_id = Column(String(64), ForeignKey("youtube_accounts.id", ondelete="SET NULL"), nullable=True, index=True)
    channel_id = Column(String(64), nullable=True)
    youtube_video_id = Column(String(64), nullable=True, index=True)
    youtube_url = Column(String(512), nullable=True)
    privacy_status = Column(String(32), default="unlisted")
    upload_status = Column(String(32), default="PENDING")
    error_message = Column(Text, nullable=True)
    upload_completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("YouTubeAccount", back_populates="uploads")
    batch = relationship("Batch")




# ==========================================
# ADMIN & SECURITY
# ==========================================

class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    username = Column(String(128), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(64), default="ADMIN")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    actor_type = Column(String(32), default="BOT") # BOT, ADMIN, SYSTEM
    actor_id = Column(String(128), nullable=True)
    action = Column(String(128), nullable=False, index=True)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(String(64), nullable=True)
    details = Column(JSON, default=dict)
    ip_address = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(128), primary_key=True)
    value = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ==========================================
# STUDENT IDENTITY & ACCESS CONTROL
# ==========================================

class Student(Base):
    __tablename__ = "students"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    status = Column(String(32), default="ACTIVE") # ACTIVE, SUSPENDED, PENDING
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)

    batch_accesses = relationship("StudentBatchAccess", back_populates="student", cascade="all, delete-orphan")
    activities = relationship("StudentActivity", back_populates="student", cascade="all, delete-orphan")


class StudentBatchAccess(Base):
    __tablename__ = "student_batch_access"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(32), default="ACTIVE") # ACTIVE, PENDING, EXPIRED, REVOKED
    granted_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("student_id", "batch_id", name="uq_student_batch_access"),
    )

    student = relationship("Student", back_populates="batch_accesses")
    batch = relationship("Batch")


class StudentActivity(Base):
    __tablename__ = "student_activity"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    lecture_id = Column(String(64), ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True)
    playback_seconds = Column(Float, default=0.0)
    completed = Column(Boolean, default=False)
    last_accessed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("student_id", "lecture_id", name="uq_student_lecture_activity"),
    )

    student = relationship("Student", back_populates="activities")
    lecture = relationship("Lecture")


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(String(64), primary_key=True, default=generate_uuid)
    student_id = Column(String(64), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    student_name = Column(String(255), nullable=False)
    student_contact = Column(String(255), nullable=False) # Email or Phone
    batch_id = Column(String(64), ForeignKey("batches.id", ondelete="SET NULL"), nullable=True, index=True)
    subject = Column(String(255), nullable=False)
    category = Column(String(64), default="GENERAL") # ACCESS_ISSUE, VIDEO_PLAYBACK, PDF_NOTES, OTHER
    description = Column(Text, nullable=False)
    admin_note = Column(Text, nullable=True)
    status = Column(String(32), default="PENDING", index=True) # PENDING, IN_PROGRESS, RESOLVED, CLOSED
    priority = Column(String(32), default="MEDIUM") # LOW, MEDIUM, HIGH, URGENT
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    student = relationship("Student", backref="tickets")
    batch = relationship("Batch")

