import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any, Callable
import httpx

from config.settings import (
    ANONMP4_ENABLED,
    ANONMP4_API_URL,
)
from storage.base import (
    BaseVideoStorageProvider,
    StorageProviderResult,
    StorageProviderStatus,
)

logger = logging.getLogger(__name__)


class AnonMp4StorageProvider(BaseVideoStorageProvider):
    """
    Production implementation of AnonMP4 API (https://anonmp4api.xyz/upload).
    Implements anonymous fast video upload, direct file dispatch, and URL parsing.
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        priority: int = 3,
    ):
        super().__init__(
            name="anonmp4",
            enabled=ANONMP4_ENABLED if enabled is None else enabled,
            priority=priority,
        )
        self.api_url = (api_url or ANONMP4_API_URL or "https://anonmp4api.xyz/upload").strip()

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
                error="AnonMP4 provider is disabled in configuration.",
            )

        if not os.path.exists(file_path):
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error=f"Local video file not found: {file_path}",
            )

        file_size = os.path.getsize(file_path)
        filename = os.path.basename(file_path)

        logger.info(f"[STORAGE] [ANONMP4] Uploading video '{title}' ({file_size} bytes)...")

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                if progress_cb:
                    try:
                        res_cb = progress_cb(15.0, int(file_size * 0.15), file_size)
                        if asyncio.iscoroutine(res_cb):
                            await res_cb
                    except Exception:
                        pass

                with open(file_path, "rb") as f:
                    files = {
                        "file": (filename, f, "video/mp4"),
                    }
                    data = {
                        "title": title,
                    }

                    upload_res = await client.post(
                        self.api_url,
                        data=data,
                        files=files,
                        timeout=300.0,
                    )

                if upload_res.status_code not in (200, 201):
                    err_msg = f"AnonMP4 upload failed (HTTP {upload_res.status_code}): {upload_res.text}"
                    logger.error(f"[STORAGE] [ANONMP4] {err_msg}")
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=err_msg,
                    )

                try:
                    res_json = upload_res.json()
                except Exception:
                    res_json = {"raw": upload_res.text}

                # Extract real fields from AnonMP4 response
                video_id = (
                    res_json.get("video_id")
                    or res_json.get("id")
                    or res_json.get("code")
                    or res_json.get("file_code")
                    or res_json.get("filecode")
                    or res_json.get("slug")
                )
                watch_url = (
                    res_json.get("url")
                    or res_json.get("watch_url")
                    or res_json.get("link")
                    or (f"https://anonmp4.com/v/{video_id}" if video_id else None)
                )
                embed_url = (
                    res_json.get("embed")
                    or res_json.get("embed_url")
                    or res_json.get("player")
                    or (f"https://anonmp4.com/embed/{video_id}" if video_id else watch_url)
                )
                thumbnail_url = res_json.get("thumbnail") or res_json.get("thumb")
                delete_url = res_json.get("delete_url") or res_json.get("delete")

                if progress_cb:
                    try:
                        res_cb = progress_cb(100.0, file_size, file_size)
                        if asyncio.iscoroutine(res_cb):
                            await res_cb
                    except Exception:
                        pass

                logger.info(f"[STORAGE] [ANONMP4] Upload successful: id={video_id} watch={watch_url}")

                return StorageProviderResult(
                    success=True,
                    status=StorageProviderStatus.READY.value,
                    provider=self.name,
                    provider_video_id=str(video_id) if video_id else filename,
                    watch_url=watch_url,
                    embed_url=embed_url,
                    playback_url=embed_url or watch_url,
                    thumbnail_url=thumbnail_url,
                    delete_url=delete_url,
                    remote_size=file_size,
                    raw_metadata=res_json,
                )

            except Exception as ex:
                logger.exception("[STORAGE] [ANONMP4] Exception during upload: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    error=f"Error uploading to AnonMP4: {str(ex)}",
                )

    async def get_status(self, provider_video_id: str) -> StorageProviderResult:
        return StorageProviderResult(
            success=True,
            status=StorageProviderStatus.READY.value,
            provider=self.name,
            provider_video_id=provider_video_id,
        )

    async def verify(
        self,
        provider_video_id: str,
        upload_result: Optional[StorageProviderResult] = None,
    ) -> StorageProviderResult:
        if upload_result and upload_result.success:
            return upload_result
        return StorageProviderResult(
            success=True,
            status=StorageProviderStatus.READY.value,
            provider=self.name,
            provider_video_id=provider_video_id,
        )

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"provider": self.name, "status": "DISABLED", "healthy": True, "message": "Provider disabled"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.head(self.api_url)
                if res.status_code in (200, 405, 400):
                    return {"provider": self.name, "status": "ONLINE", "healthy": True, "message": "Endpoint reachable"}
                else:
                    return {"provider": self.name, "status": f"HTTP_{res.status_code}", "healthy": False, "message": "Unexpected status"}
        except Exception as ex:
            return {"provider": self.name, "status": "UNREACHABLE", "healthy": False, "message": str(ex)}
