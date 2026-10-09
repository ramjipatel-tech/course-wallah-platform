import os
import re
from pathlib import Path
from typing import List, Dict, Any
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env specifically from course_wallah_platform directory first
local_env = BASE_DIR / ".env"
if local_env.exists():
    load_dotenv(dotenv_path=local_env)

parent_env = BASE_DIR.parent / ".env"
if parent_env.exists():
    load_dotenv(dotenv_path=parent_env, override=False)

# Database configuration (PostgreSQL primary, SQLite for local dev)
raw_db_url = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./data/course_wallah.db").strip()
if raw_db_url.startswith("sqlite+aiosqlite:///./") or raw_db_url.startswith("sqlite:///./"):
    rel_path = raw_db_url.split("///./")[-1]
    DATABASE_URL = f"sqlite+aiosqlite:///{(BASE_DIR / rel_path).as_posix()}"
elif raw_db_url.startswith("sqlite://./"):
    rel_path = raw_db_url.split("//./")[-1]
    DATABASE_URL = f"sqlite+aiosqlite:///{(BASE_DIR / rel_path).as_posix()}"
else:
    DATABASE_URL = raw_db_url

# Secret Keys
SECRET_KEY = os.environ.get("SECRET_KEY", "course-wallah-super-secret-key-change-in-prod")
API_SECRET = os.environ.get("API_SECRET", "cw-api-secret-key-2026")
ADMIN_SECRET_PATH = os.environ.get("ADMIN_SECRET_PATH", "mahi")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "CourseWallah@2026#Secure")

# Bot & Telegram Settings
API_ID = int(os.environ.get("API_ID", "0")) if os.environ.get("API_ID", "0").isdigit() else 0
API_HASH = os.environ.get("API_HASH", "").strip()
raw_bot_token = os.environ.get("BOT_TOKEN", "").strip()
if raw_bot_token:
    BOT_TOKEN = raw_bot_token
else:
    BOT_TOKEN = os.environ.get("BOT_1_TOKEN", "").strip()
BOT_NAME = os.environ.get("BOT_NAME", "Course wallah").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@course_wallah_officalbot").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", "0")) if os.environ.get("OWNER_ID", "0").isdigit() else 0
ADMINS_RAW = os.environ.get("ADMINS", str(OWNER_ID) if OWNER_ID else "").strip()
ADMINS = [int(x.strip()) for x in ADMINS_RAW.split(",") if x.strip().isdigit()]
if OWNER_ID and OWNER_ID not in ADMINS:
    ADMINS.append(OWNER_ID)

# Backblaze B2 S3-Compatible Settings
B2_ENDPOINT = os.environ.get("B2_ENDPOINT", "https://s3.us-east-005.backblazeb2.com").strip()
B2_REGION = os.environ.get("B2_REGION", "us-east-005").strip()
B2_BUCKET = (os.environ.get("B2_BUCKET") or os.environ.get("B2_BUCKET_NAME", "course-wallah-pdfs")).strip()
B2_KEY_ID = os.environ.get("B2_KEY_ID", "").strip()
B2_APPLICATION_KEY = os.environ.get("B2_APPLICATION_KEY", "").strip()

# YouTube Data API Settings (Default Disabled: Video hosting uses Multi-Storage VCDN/Media.cm)
YOUTUBE_ENABLED = os.environ.get("YOUTUBE_ENABLED", "false").lower() == "true"
YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "").strip()
YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "").strip()
YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "").strip()
YOUTUBE_DEFAULT_PRIVACY = os.environ.get("YOUTUBE_DEFAULT_PRIVACY", "unlisted").strip()

# Watermark & Encoding Performance Settings
WATERMARK_ENABLED = os.environ.get("WATERMARK_ENABLED", "true").lower() == "true"
WATERMARK_PRESET = os.environ.get("WATERMARK_PRESET", "ultrafast").strip()
WATERMARK_TEXT = os.environ.get("WATERMARK_TEXT", "COURSE WALLAH").strip()
WATERMARK_OPACITY = float(os.environ.get("WATERMARK_OPACITY", "0.45"))
WATERMARK_CRF = int(os.environ.get("WATERMARK_CRF", "26"))
WATERMARK_SPEED = int(os.environ.get("WATERMARK_SPEED", "8"))  # Movement speed in sec

# Storage & Temporary Dirs
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DOWNLOADS_DIR = BASE_DIR / "downloads"
ASSETS_DIR = BASE_DIR / "assets"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"

for p in [DATA_DIR, TEMP_DIR, DOWNLOADS_DIR, ASSETS_DIR, THUMBNAILS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Processing Limits
MAX_UPLOAD_SIZE_BYTES = int(os.environ.get("MAX_UPLOAD_SIZE_BYTES", str(1950 * 1024 * 1024)))
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "3"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "5"))

# Security Test Mode
SECURITY_TEST_MODE = os.environ.get("SECURITY_TEST_MODE", "true").lower() == "true"
SITE_URL = os.environ.get("SITE_URL", "http://localhost:3000")
API_URL = os.environ.get("API_URL", "http://localhost:8000")

# ==========================================
# MULTI-STORAGE REPLICATION PROVIDERS
# ==========================================

# 1. VCDN Provider Settings
VCDN_ENABLED = os.environ.get("VCDN_ENABLED", "true").lower() == "true"
# 1. VCDN Provider Settings
VCDN_ENABLED = os.environ.get("VCDN_ENABLED", "true").lower() == "true"
VCDN_API_KEY = re.sub(r"[\r\n\t\s]+", "", os.environ.get("VCDN_API_KEY", ""))
VCDN_BASE_URL = re.sub(r"[\r\n\t\s]+", "", os.environ.get("VCDN_BASE_URL", "https://cdn.vcdn.me")).rstrip("/")
VCDN_LADDER_PROFILE = os.environ.get("VCDN_LADDER_PROFILE", "standard").strip()

# 2. Media.cm Provider Settings
MEDIA_CM_ENABLED = os.environ.get("MEDIA_CM_ENABLED", "true").lower() == "true"
MEDIA_CM_API_KEY = re.sub(r"[\r\n\t\s]+", "", os.environ.get("MEDIA_CM_API_KEY", ""))
MEDIA_CM_BASE_URL = re.sub(r"[\r\n\t\s]+", "", os.environ.get("MEDIA_CM_BASE_URL", "https://media.cm")).rstrip("/")

# 3. AnonMP4 Provider Settings
ANONMP4_ENABLED = os.environ.get("ANONMP4_ENABLED", "true").lower() == "true"
ANONMP4_API_URL = re.sub(r"[\r\n\t\s]+", "", os.environ.get("ANONMP4_API_URL", "https://anonmp4api.xyz/upload"))

# 4. Vevocloud Provider Settings
VEVOCLOUD_ENABLED = os.environ.get("VEVOCLOUD_ENABLED", "true").lower() == "true"
VEVOCLOUD_API_KEY = re.sub(r"[\r\n\t\s]+", "", os.environ.get("VEVOCLOUD_API_KEY", ""))
VEVOCLOUD_BASE_URL = re.sub(r"[\r\n\t\s]+", "", os.environ.get("VEVOCLOUD_BASE_URL", "https://www.vevocloud.com")).rstrip("/")

# Storage General Policies
STORAGE_MAX_RETRIES = int(os.environ.get("STORAGE_MAX_RETRIES", "3"))
STORAGE_RETRY_DELAY = int(os.environ.get("STORAGE_RETRY_DELAY", "5"))
STORAGE_VERIFY_TIMEOUT = int(os.environ.get("STORAGE_VERIFY_TIMEOUT", "60"))
STORAGE_CHUNK_SIZE_BYTES = int(os.environ.get("STORAGE_CHUNK_SIZE_BYTES", str(8 * 1024 * 1024))) # 8MB default chunk
STORAGE_REQUIRED_PROVIDERS = [
    x.strip().lower() for x in os.environ.get("STORAGE_REQUIRED_PROVIDERS", "media_cm").split(",") if x.strip()
]
