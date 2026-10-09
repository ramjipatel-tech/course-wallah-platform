import os
import logging
from typing import Optional, Dict, Any, Callable
from pathlib import Path

from config.settings import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    OWNER_ID,
    TELEGRAM_STREAM_ENABLED,
)
from storage.base import (
    BaseVideoStorageProvider,
    StorageProviderResult,
    StorageProviderStatus,
)
from storage.telegram_stream.client_pool import TelegramClientPool
from storage.telegram_stream.caption_formatter import format_telegram_channel_caption

logger = logging.getLogger(__name__)


class TelegramStreamStorageProvider(BaseVideoStorageProvider):
    """
    High-Performance Telegram Direct HTTP Streaming Storage Provider.
    Zero-Cost, Unlimited Cloud Storage with Native In-App Web Video Playback.
    """

    def __init__(
        self,
        enabled: Optional[bool] = None,
        priority: int = 1,
    ):
        super().__init__(
            name="telegram",
            enabled=TELEGRAM_STREAM_ENABLED if enabled is None else enabled,
            priority=priority,
        )
        self.pool = TelegramClientPool.get_instance()

    async def upload(
        self,
        file_path: str,
        title: str,
        metadata: Optional[Dict[str, Any]] = None,
        progress_cb: Optional[Callable[[float, int, int], Any]] = None,
    ) -> StorageProviderResult:
        if not self.enabled:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.DISABLED.value,
                provider=self.name,
                error="Telegram stream provider is disabled in configuration.",
            )

        if not BOT_TOKEN or not API_ID or not API_HASH:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error="Telegram Bot credentials (API_ID, API_HASH, BOT_TOKEN) are missing.",
            )

        if not os.path.exists(file_path):
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error=f"Local video file not found: {file_path}",
            )

        file_size = os.path.getsize(file_path)
        meta = metadata or {}
        duration = int(meta.get("duration", 0) or 0)
        thumb_path = meta.get("thumbnail_path")
        width = meta.get("width")
        height = meta.get("height")
        resolution = meta.get("resolution")

        caption_text = format_telegram_channel_caption(
            title=title,
            metadata=meta,
            width=width,
            height=height,
            resolution=resolution,
        )

        try:
            res = await self.pool.upload_video(
                file_path=file_path,
                caption=caption_text,
                duration=duration,
                width=width,
                height=height,
                thumb_path=thumb_path,
                progress_cb=progress_cb,
            )

            msg_id = str(res["message_id"])
            stream_url = f"/api/v1/stream/tg/{msg_id}"

            return StorageProviderResult(
                success=True,
                status=StorageProviderStatus.READY.value,
                provider=self.name,
                provider_video_id=msg_id,
                watch_url=stream_url,
                embed_url=None,  # Plays natively inside Course Wallah HTML5 / Plyr video player!
                hls_url=stream_url,
                playback_url=stream_url,
                remote_size=file_size,
                raw_metadata=res,
            )

        except Exception as ex:
            logger.exception(f"[STORAGE] [TELEGRAM] Upload failed for '{title}': {ex}")
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error=f"Telegram upload failed: {str(ex)}",
            )

    async def get_status(self, provider_video_id: str) -> StorageProviderResult:
        if not provider_video_id:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error="Missing Telegram message ID",
            )

        try:
            msg_id = int(provider_video_id)
            target_chat = self.pool.storage_chat_id or OWNER_ID
            media, file_size, _ = await self.pool.get_media_info(target_chat, msg_id)

            stream_url = f"/api/v1/stream/tg/{provider_video_id}"
            return StorageProviderResult(
                success=True,
                status=StorageProviderStatus.READY.value,
                provider=self.name,
                provider_video_id=provider_video_id,
                watch_url=stream_url,
                embed_url=None,
                hls_url=stream_url,
                playback_url=stream_url,
                remote_size=file_size,
            )
        except Exception as ex:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                provider_video_id=provider_video_id,
                error=str(ex),
            )

    async def verify(
        self,
        provider_video_id: str,
        upload_result: Optional[StorageProviderResult] = None,
    ) -> StorageProviderResult:
        return await self.get_status(provider_video_id)

    async def delete(self, provider_video_id: str) -> bool:
        if not provider_video_id:
            return False
        try:
            msg_id = int(provider_video_id)
            target_chat = self.pool.storage_chat_id or OWNER_ID
            client = self.pool.get_client()
            await client.delete_messages(chat_id=target_chat, message_ids=msg_id)
            return True
        except Exception:
            return False

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"provider": self.name, "status": "DISABLED", "healthy": True, "message": "Provider disabled"}
        if not BOT_TOKEN or not API_ID or not API_HASH:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "healthy": False, "message": "Bot credentials missing"}

        try:
            await self.pool.start()
            workers_count = len(self.pool.clients)
            return {
                "provider": self.name,
                "status": "ONLINE",
                "healthy": True,
                "message": f"Telegram Stream Engine Online ({workers_count} active workers)",
                "active_workers": workers_count,
            }
        except Exception as ex:
            return {"provider": self.name, "status": "UNREACHABLE", "healthy": False, "message": str(ex)}
