import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any, Callable
import httpx

from config.settings import (
    MEDIA_CM_ENABLED,
    MEDIA_CM_API_KEY,
    MEDIA_CM_BASE_URL,
    STORAGE_VERIFY_TIMEOUT,
)
from storage.base import (
    BaseVideoStorageProvider,
    StorageProviderResult,
    StorageProviderStatus,
)

logger = logging.getLogger(__name__)


class MediaCmStorageProvider(BaseVideoStorageProvider):
    """
    Production implementation of Media.cm API.
    Flow:
    1. GET /api/upload/server?key=<api_key> -> get upload server
    2. POST <server_url> with multipart (key, file) -> get filecode
    3. Verify via GET /api/file/info?key=<api_key>&file_code=<filecode>
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        priority: int = 2,
    ):
        super().__init__(
            name="media_cm",
            enabled=MEDIA_CM_ENABLED if enabled is None else enabled,
            priority=priority,
        )
        self.api_key = (api_key or MEDIA_CM_API_KEY or "").strip()
        self.base_url = (base_url or MEDIA_CM_BASE_URL or "https://media.cm").strip().rstrip("/")

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
                error="Media.cm provider is disabled in configuration.",
            )

        if not self.api_key:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error="Media.cm API key is not configured.",
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

        logger.info(f"[STORAGE] [MEDIA.CM] Fetching upload server for '{title}' ({file_size} bytes)...")

        async with httpx.AsyncClient(timeout=180.0) as client:
            # Step 1: Request active upload server
            server_url_api = f"{self.base_url}/api/upload/server?key={self.api_key}"
            try:
                server_res = await client.get(server_url_api)
                if server_res.status_code != 200:
                    err_msg = f"Server lookup failed (HTTP {server_res.status_code}): {server_res.text}"
                    logger.error(f"[STORAGE] [MEDIA.CM] {err_msg}")
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=err_msg,
                    )

                server_data = server_res.json()
                upload_server = server_data.get("result")
                if not upload_server:
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=f"No upload server returned by Media.cm: {server_data}",
                    )

                logger.info(f"[STORAGE] [MEDIA.CM] Using upload server: {upload_server}")

            except Exception as ex:
                logger.exception("[STORAGE] [MEDIA.CM] Exception getting upload server: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    error=f"Network error contacting Media.cm server API: {str(ex)}",
                )

            # Step 2: Upload file via multipart POST
            try:
                if progress_cb:
                    try:
                        res_cb = progress_cb(10.0, int(file_size * 0.1), file_size)
                        if asyncio.iscoroutine(res_cb):
                            await res_cb
                    except Exception:
                        pass

                with open(file_path, "rb") as f:
                    files = {
                        "file": (filename, f, "video/mp4"),
                    }
                    data = {
                        "key": self.api_key,
                    }

                    upload_res = await client.post(
                        upload_server,
                        data=data,
                        files=files,
                        timeout=300.0,
                    )

                if upload_res.status_code != 200:
                    err_msg = f"File upload failed (HTTP {upload_res.status_code}): {upload_res.text}"
                    logger.error(f"[STORAGE] [MEDIA.CM] {err_msg}")
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=err_msg,
                    )

                upload_data = upload_res.json()
                # Parse filecode from response (list or dict)
                filecode = None
                if isinstance(upload_data, list) and len(upload_data) > 0:
                    first_item = upload_data[0]
                    if isinstance(first_item, dict):
                        filecode = first_item.get("filecode") or first_item.get("file_code") or first_item.get("code")
                elif isinstance(upload_data, dict):
                    result_obj = upload_data.get("result") or upload_data.get("files")
                    if isinstance(result_obj, list) and len(result_obj) > 0:
                        first_item = result_obj[0]
                        if isinstance(first_item, dict):
                            filecode = first_item.get("filecode") or first_item.get("file_code") or first_item.get("code")
                    elif isinstance(result_obj, dict):
                        filecode = result_obj.get("filecode") or result_obj.get("file_code") or result_obj.get("code")
                    elif isinstance(result_obj, str):
                        filecode = result_obj
                    else:
                        filecode = upload_data.get("filecode") or upload_data.get("file_code")

                if not filecode:
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=f"No filecode returned by Media.cm: {upload_data}",
                    )

                if progress_cb:
                    try:
                        res_cb = progress_cb(100.0, file_size, file_size)
                        if asyncio.iscoroutine(res_cb):
                            await res_cb
                    except Exception:
                        pass

                logger.info(f"[STORAGE] [MEDIA.CM] Upload complete, received filecode: {filecode}")

            except Exception as ex:
                logger.exception("[STORAGE] [MEDIA.CM] Exception uploading to Media.cm: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    error=f"Error uploading file to Media.cm: {str(ex)}",
                )

        preliminary_result = StorageProviderResult(
            success=True,
            status=StorageProviderStatus.VERIFYING.value,
            provider=self.name,
            provider_video_id=filecode,
            watch_url=f"https://media.cm/{filecode}",
            embed_url=f"https://media.cm/embed/{filecode}",
            remote_size=file_size,
            raw_metadata=upload_data,
        )

        return await self.verify(filecode, preliminary_result)

    async def get_status(self, provider_video_id: str) -> StorageProviderResult:
        if not self.api_key or not provider_video_id:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                provider_video_id=provider_video_id,
                error="Missing API key or filecode",
            )

        info_url = f"{self.base_url}/api/file/info?key={self.api_key}&file_code={provider_video_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.get(info_url)
                if res.status_code == 200:
                    data = res.json()
                    res_items = data.get("result", [])
                    item_info = res_items[0] if isinstance(res_items, list) and res_items else (res_items if isinstance(res_items, dict) else {})
                    
                    remote_status = item_info.get("status")
                    if remote_status == 200 or data.get("status") == 200:
                        watch_url = f"https://media.cm/{provider_video_id}"
                        embed_url = f"https://media.cm/embed/{provider_video_id}"
                        return StorageProviderResult(
                            success=True,
                            status=StorageProviderStatus.READY.value,
                            provider=self.name,
                            provider_video_id=provider_video_id,
                            watch_url=watch_url,
                            embed_url=embed_url,
                            playback_url=embed_url,
                            remote_size=int(item_info.get("size", 0) or 0),
                            raw_metadata=data,
                        )
                    else:
                        return StorageProviderResult(
                            success=False,
                            status=StorageProviderStatus.FAILED.value,
                            provider=self.name,
                            provider_video_id=provider_video_id,
                            error=f"File info status: {remote_status}",
                            raw_metadata=data,
                        )
                else:
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        provider_video_id=provider_video_id,
                        error=f"HTTP {res.status_code}: {res.text}",
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
        logger.info(f"[STORAGE] [MEDIA.CM] Verifying filecode={provider_video_id}...")
        start_time = time.time()
        timeout = 60

        while (time.time() - start_time) < timeout:
            status_res = await self.get_status(provider_video_id)
            if status_res.status == StorageProviderStatus.READY.value:
                logger.info(f"[STORAGE] [MEDIA.CM] Verified READY: {status_res.embed_url}")
                return status_res
            await asyncio.sleep(3)

        # Check final status
        final_status = await self.get_status(provider_video_id)
        if final_status.status == StorageProviderStatus.READY.value:
            return final_status

        logger.warning(f"[STORAGE] [MEDIA.CM] Filecode {provider_video_id} verification timed out after {timeout}s.")
        return StorageProviderResult(
            success=False,
            status=StorageProviderStatus.FAILED.value,
            provider=self.name,
            provider_video_id=provider_video_id,
            error=f"Verification timeout: Media.cm filecode {provider_video_id} could not be confirmed after {timeout}s",
            raw_metadata=final_status.raw_metadata,
        )

    async def delete(self, provider_video_id: str) -> bool:
        if not self.api_key or not provider_video_id:
            return False
        url = f"{self.base_url}/api/file/delete?key={self.api_key}&file_code={provider_video_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    return data.get("status") == 200
                return False
            except Exception:
                return False

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"provider": self.name, "status": "DISABLED", "healthy": True, "message": "Provider disabled"}
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "healthy": False, "message": "API key missing"}

        url = f"{self.base_url}/api/account/info?key={self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("status") == 200:
                        return {"provider": self.name, "status": "ONLINE", "healthy": True, "message": "API connection verified"}
                    else:
                        return {"provider": self.name, "status": "AUTH_ERROR", "healthy": False, "message": data.get("msg", "Auth error")}
                else:
                    return {"provider": self.name, "status": f"HTTP_{res.status_code}", "healthy": False, "message": res.text[:100]}
        except Exception as ex:
            return {"provider": self.name, "status": "UNREACHABLE", "healthy": False, "message": str(ex)}
