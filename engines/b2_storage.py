import os
import time
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None

from config.settings import (
    B2_ENDPOINT,
    B2_REGION,
    B2_BUCKET,
    B2_KEY_ID,
    B2_APPLICATION_KEY,
    DATA_DIR
)

logger = logging.getLogger(__name__)

MAX_CACHE_BYTES = 150 * 1024 * 1024  # 150 MB
TTL_SECONDS = 30 * 60  # 30 minutes


class PDFMemoryCache:
    """
    Thread-safe bounded LRU + TTL in-memory cache for PDF documents.
    Enforces a strict 150MB memory ceiling and 30-minute automatic TTL expiration.
    """
    def __init__(self, max_bytes: int = MAX_CACHE_BYTES, ttl_seconds: int = TTL_SECONDS):
        self.max_bytes = max_bytes
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: list = []
        self._total_bytes: int = 0
        self._lock = threading.Lock()
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.cache_evictions: int = 0
        self.cache_expired: int = 0

    def _cleanup_expired_unlocked(self, now: float):
        expired_keys = [
            k for k, v in self._cache.items()
            if now - v["created_at"] > self.ttl_seconds
        ]
        for k in expired_keys:
            entry = self._cache.pop(k, None)
            if entry:
                self._total_bytes -= entry["size"]
                if k in self._access_order:
                    self._access_order.remove(k)
                self.cache_expired += 1

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            now = time.time()
            if key not in self._cache:
                self.cache_misses += 1
                return None

            entry = self._cache[key]
            # Check TTL
            if now - entry["created_at"] > self.ttl_seconds:
                self._cache.pop(key, None)
                self._total_bytes -= entry["size"]
                if key in self._access_order:
                    self._access_order.remove(key)
                self.cache_expired += 1
                self.cache_misses += 1
                return None

            # LRU update: mark most recently used
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
            entry["last_accessed_at"] = now
            self.cache_hits += 1
            return entry["data"]

    def put(self, key: str, data: bytes):
        size = len(data)
        # Oversized single PDF: do not cache if larger than max capacity
        if size > self.max_bytes:
            return

        with self._lock:
            now = time.time()
            self._cleanup_expired_unlocked(now)

            # If existing key, remove old instance first
            if key in self._cache:
                old = self._cache.pop(key)
                self._total_bytes -= old["size"]
                if key in self._access_order:
                    self._access_order.remove(key)

            # LRU eviction until fits
            while self._total_bytes + size > self.max_bytes and self._access_order:
                lru_key = self._access_order.pop(0)
                old_entry = self._cache.pop(lru_key, None)
                if old_entry:
                    self._total_bytes -= old_entry["size"]
                    self.cache_evictions += 1

            self._cache[key] = {
                "data": data,
                "created_at": now,
                "last_accessed_at": now,
                "size": size
            }
            self._access_order.append(key)
            self._total_bytes += size

    @property
    def cache_bytes(self) -> int:
        with self._lock:
            return self._total_bytes

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._total_bytes = 0


class B2StorageManager:
    """
    Backblaze B2 S3-Compatible Storage Adapter for Course Wallah Platform.
    Stores PDFs in a private bucket and generates short-lived presigned URLs for authenticated students.
    """

    _s3_client = None
    pdf_cache = PDFMemoryCache()

    @classmethod
    def get_client(cls):
        if cls._s3_client is not None:
            return cls._s3_client

        if not boto3 or not B2_KEY_ID or not B2_APPLICATION_KEY:
            logger.warning("[B2 STORAGE] B2 credentials or boto3 not configured. Operating in local filesystem storage mode.")
            return None

        cls._s3_client = boto3.client(
            "s3",
            endpoint_url=B2_ENDPOINT,
            aws_access_key_id=B2_KEY_ID,
            aws_secret_access_key=B2_APPLICATION_KEY,
            region_name=B2_REGION,
            config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
        )
        return cls._s3_client

    @classmethod
    def build_object_key(
        cls,
        app_slug: str,
        batch_slug: str,
        folder_slug: str,
        lecture_slug: str,
        filename: str = "lecture.pdf"
    ) -> str:
        """Standardized structured object path in private B2 bucket."""
        return f"courses/{app_slug}/{batch_slug}/{folder_slug}/{lecture_slug}/{filename}"

    @classmethod
    async def upload_pdf(
        cls,
        local_pdf_path: str,
        object_key: str,
        bucket_name: str = B2_BUCKET,
        content_type: str = "application/pdf"
    ) -> Dict[str, Any]:
        """Uploads local PDF file to private B2 bucket."""
        p = Path(local_pdf_path)
        if not p.exists() or p.stat().st_size == 0:
            raise ValueError(f"PDF file does not exist or is empty: {local_pdf_path}")

        file_size = p.stat().st_size
        client = cls.get_client()

        if client is None:
            # Local development fallback: store in DATA_DIR / "b2_mock" / object_key
            mock_dest = Path(DATA_DIR) / "b2_mock" / object_key
            mock_dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(p, mock_dest)
            logger.info(f"[B2 STORAGE MOCK] Stored {object_key} locally ({file_size} bytes)")
            return {
                "b2_object_key": object_key,
                "b2_bucket": bucket_name,
                "file_name": p.name,
                "file_size": file_size,
                "storage_type": "LOCAL_MOCK",
                "status": "UPLOADED"
            }

        try:
            logger.info(f"[B2 STORAGE] Uploading {p.name} to {bucket_name}/{object_key}...")
            client.upload_file(
                Filename=str(p),
                Bucket=bucket_name,
                Key=object_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": {
                        "uploaded_by": "CourseWallahPlatform",
                        "timestamp": str(int(time.time()))
                    }
                }
            )
            logger.info(f"[B2 STORAGE] Successfully uploaded {object_key} ({file_size / (1024*1024):.2f} MB)")
            return {
                "b2_object_key": object_key,
                "b2_bucket": bucket_name,
                "file_name": p.name,
                "file_size": file_size,
                "storage_type": "B2_S3",
                "status": "UPLOADED"
            }
        except Exception as e:
            logger.error(f"[B2 STORAGE] Upload failed: {e}")
            raise RuntimeError(f"B2 upload failed: {e}")

    @classmethod
    def generate_presigned_url(
        cls,
        object_key: str,
        bucket_name: str = B2_BUCKET,
        expires_in_seconds: int = 900 # 15 minutes
    ) -> str:
        """
        Generates a short-lived temporary presigned URL for authorized students to view/download PDF.
        Permanent private storage keys are NEVER exposed.
        """
        client = cls.get_client()
        if client is None:
            # Local fallback URL
            return f"/api/v1/pdfs/stream?key={object_key}&token=sandbox_{int(time.time())}"

        try:
            url = client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": bucket_name,
                    "Key": object_key
                },
                ExpiresIn=expires_in_seconds
            )
            return url
        except Exception as e:
            logger.error(f"[B2 STORAGE] Failed to generate presigned URL: {e}")
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

    @classmethod
    def get_pdf_bytes(cls, object_key: str, bucket_name: str = B2_BUCKET) -> Optional[bytes]:
        """Fetches raw PDF bytes directly from Backblaze B2 private storage with bounded LRU+TTL in-memory caching."""
        cache_key = f"{bucket_name}:{object_key}"
        cached_data = cls.pdf_cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        client = cls.get_client()
        if client is None:
            mock_dest = Path(DATA_DIR) / "b2_mock" / object_key
            if mock_dest.exists():
                data = mock_dest.read_bytes()
                cls.pdf_cache.put(cache_key, data)
                return data
            return None

        try:
            resp = client.get_object(Bucket=bucket_name, Key=object_key)
            data = resp["Body"].read()
            cls.pdf_cache.put(cache_key, data)
            return data
        except Exception as e:
            logger.error(f"[B2 STORAGE] Failed to get object {object_key}: {e}")
            return None
