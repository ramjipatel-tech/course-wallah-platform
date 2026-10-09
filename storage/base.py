import enum
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Callable

logger = logging.getLogger(__name__)


class StorageProviderStatus(str, enum.Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    PROCESSING = "PROCESSING"
    VERIFYING = "VERIFYING"
    READY = "READY"
    RETRYING = "RETRYING"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


class StorageReplicationError(Exception):
    """Base exception for storage replication failures."""
    pass


class StorageReplicationProcessingError(StorageReplicationError):
    """Raised when a required storage provider is still transcoding/processing asynchronously."""
    def __init__(self, message: str, provider: str, provider_video_id: Optional[str] = None):
        super().__init__(message)
        self.provider = provider
        self.provider_video_id = provider_video_id


class StorageReplicationFailedError(StorageReplicationError):
    """Raised when one or more required storage providers permanently fail."""
    def __init__(self, message: str, failed_providers: Optional[list] = None):
        super().__init__(message)
        self.failed_providers = failed_providers or []



@dataclass
class StorageProviderResult:
    success: bool
    status: str
    provider: str
    provider_video_id: Optional[str] = None
    watch_url: Optional[str] = None
    embed_url: Optional[str] = None
    hls_url: Optional[str] = None
    playback_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    delete_url: Optional[str] = None
    remote_size: int = 0
    remote_duration: float = 0.0
    error: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status,
            "provider": self.provider,
            "provider_video_id": self.provider_video_id,
            "watch_url": self.watch_url,
            "embed_url": self.embed_url,
            "hls_url": self.hls_url,
            "playback_url": self.playback_url,
            "thumbnail_url": self.thumbnail_url,
            "delete_url": self.delete_url,
            "remote_size": self.remote_size,
            "remote_duration": self.remote_duration,
            "error": self.error,
            "raw_metadata": self.raw_metadata,
        }


class BaseVideoStorageProvider(ABC):
    """
    Abstract base class for all cloud video replication storage providers.
    Enforces strict isolated implementation for upload, status check, verification,
    deletion, and health checks.
    """

    def __init__(self, name: str, enabled: bool = True, priority: int = 1):
        self.name = name
        self.enabled = enabled
        self.priority = priority

    @abstractmethod
    async def upload(
        self,
        file_path: str,
        title: str,
        metadata: Optional[Dict[str, Any]] = None,
        progress_cb: Optional[Callable[[float, int, int], Any]] = None,
    ) -> StorageProviderResult:
        """
        Uploads the video file to the remote provider with progress reporting.
        """
        pass

    @abstractmethod
    async def get_status(self, provider_video_id: str) -> StorageProviderResult:
        """
        Fetches current status & metadata of the video from provider API.
        """
        pass

    @abstractmethod
    async def verify(
        self,
        provider_video_id: str,
        upload_result: Optional[StorageProviderResult] = None,
    ) -> StorageProviderResult:
        """
        Rigorously verifies that video is uploaded, processed, and playable/embeddable.
        """
        pass

    async def delete(self, provider_video_id: str) -> bool:
        """
        Deletes the video from provider storage if supported.
        """
        return False

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """
        Tests API connectivity and authentication without exposing credentials.
        """
        pass
