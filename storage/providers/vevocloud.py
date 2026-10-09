import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any, Callable
import httpx

from config.settings import (
    VEVOCLOUD_ENABLED,
    VEVOCLOUD_API_KEY,
    VEVOCLOUD_BASE_URL,
    STORAGE_CHUNK_SIZE_BYTES,
    STORAGE_VERIFY_TIMEOUT,
)
from storage.base import (
    BaseVideoStorageProvider,
    StorageProviderResult,
    StorageProviderStatus,
)

logger = logging.getLogger(__name__)


class VevocloudStorageProvider(BaseVideoStorageProvider):
    """
    Production implementation of Vevocloud Developer API.
    Implements chunked upload session (/api/uploads/init, /api/uploads/{id}/chunks, /api/uploads/{id}/complete),
    metadata retrieval via /videos/{id}, and HLS stream verification.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        priority: int = 4,
    ):
        super().__init__(
            name="vevocloud",
            enabled=VEVOCLOUD_ENABLED if enabled is None else enabled,
            priority=priority,
        )
        self.api_key = (api_key or VEVOCLOUD_API_KEY or "").strip()
        self.base_url = (base_url or VEVOCLOUD_BASE_URL or "https://www.vevocloud.com").strip().rstrip("/")

    def _get_headers(self, content_type: Optional[str] = "application/json") -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

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
                error="Vevocloud provider is disabled in configuration.",
            )

        if not self.api_key:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error="Vevocloud API key is not configured.",
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
        chunk_size = STORAGE_CHUNK_SIZE_BYTES or (8 * 1024 * 1024)

        logger.info(f"[STORAGE] [VEVOCLOUD] Initiating chunked upload for '{title}' ({file_size} bytes)...")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: POST /api/uploads/init
            init_url = f"{self.base_url}/api/uploads/init"
            init_payload = {
                "title": title,
                "size": file_size,
                "filename": filename,
            }

            try:
                init_res = await client.post(
                    init_url,
                    json=init_payload,
                    headers=self._get_headers("application/json"),
                )

                if init_res.status_code not in (200, 201):
                    # Check if API is directly on base URL without /api
                    alt_init_url = f"{self.base_url}/uploads/init"
                    alt_res = await client.post(
                        alt_init_url,
                        json=init_payload,
                        headers=self._get_headers("application/json"),
                    )
                    if alt_res.status_code in (200, 201):
                        init_res = alt_res
                        init_url = alt_init_url
                    else:
                        err_msg = f"Vevocloud upload init failed (HTTP {init_res.status_code}): {init_res.text}"
                        logger.error(f"[STORAGE] [VEVOCLOUD] {err_msg}")
                        return StorageProviderResult(
                            success=False,
                            status=StorageProviderStatus.FAILED.value,
                            provider=self.name,
                            error=err_msg,
                        )

                init_data = init_res.json()
                session_id = init_data.get("sessionId") or init_data.get("session_id") or init_data.get("id")
                video_id = init_data.get("videoId") or init_data.get("video_id") or session_id

                if not session_id:
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=f"No sessionId returned by Vevocloud: {init_data}",
                    )

                logger.info(f"[STORAGE] [VEVOCLOUD] Upload session created: sessionId={session_id} videoId={video_id}")

            except Exception as ex:
                logger.exception("[STORAGE] [VEVOCLOUD] Exception initializing upload: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    error=f"Network error initiating Vevocloud upload: {str(ex)}",
                )

            # Step 2: Upload chunks
            chunk_base_url = (
                f"{self.base_url}/api/uploads/{session_id}/chunks"
                if "/api/" in init_url
                else f"{self.base_url}/uploads/{session_id}/chunks"
            )

            bytes_uploaded = 0
            chunk_idx = 0

            try:
                with open(file_path, "rb") as f:
                    while bytes_uploaded < file_size:
                        chunk_data = f.read(chunk_size)
                        if not chunk_data:
                            break

                        chunk_len = len(chunk_data)
                        chunk_idx += 1
                        files = {
                            "chunk": (f"chunk_{chunk_idx}.bin", chunk_data, "application/octet-stream"),
                        }

                        chunk_res = None
                        for attempt in range(1, 4):
                            try:
                                chunk_res = await client.post(
                                    chunk_base_url,
                                    files=files,
                                    headers={"Authorization": f"Bearer {self.api_key}"},
                                    timeout=180.0,
                                )
                                if chunk_res.status_code in (200, 201):
                                    break
                                elif chunk_res.status_code in (502, 503, 504) and attempt < 3:
                                    await asyncio.sleep(2 * attempt)
                                else:
                                    break
                            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                                if attempt < 3:
                                    await asyncio.sleep(2 * attempt)
                                else:
                                    raise net_err

                        if not chunk_res or chunk_res.status_code not in (200, 201):
                            err_msg = (
                                f"Chunk #{chunk_idx} failed (HTTP {chunk_res.status_code if chunk_res else 'timeout'}): "
                                f"{chunk_res.text if chunk_res else 'no response'}"
                            )
                            logger.error(f"[STORAGE] [VEVOCLOUD] {err_msg}")
                            return StorageProviderResult(
                                success=False,
                                status=StorageProviderStatus.FAILED.value,
                                provider=self.name,
                                provider_video_id=str(video_id),
                                error=err_msg,
                            )

                        bytes_uploaded += chunk_len
                        pct = min(99.0, (bytes_uploaded / file_size) * 100.0)

                        if progress_cb:
                            try:
                                res_cb = progress_cb(pct, bytes_uploaded, file_size)
                                if asyncio.iscoroutine(res_cb):
                                    await res_cb
                            except Exception:
                                pass

            except Exception as ex:
                logger.exception("[STORAGE] [VEVOCLOUD] Exception uploading chunks: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    provider_video_id=str(video_id),
                    error=f"Error uploading chunks: {str(ex)}",
                )

            # Step 3: Complete upload session
            complete_url = (
                f"{self.base_url}/api/uploads/{session_id}/complete"
                if "/api/" in init_url
                else f"{self.base_url}/uploads/{session_id}/complete"
            )

            try:
                comp_res = await client.post(
                    complete_url,
                    headers=self._get_headers("application/json"),
                    json={},
                )
                if comp_res.status_code not in (200, 201, 202):
                    err_msg = f"Complete request failed (HTTP {comp_res.status_code}): {comp_res.text}"
                    logger.error(f"[STORAGE] [VEVOCLOUD] {err_msg}")
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        provider_video_id=str(video_id),
                        error=err_msg,
                    )

                comp_data = comp_res.json()
                logger.info(f"[STORAGE] [VEVOCLOUD] Upload finalized: {comp_data}")

            except Exception as ex:
                logger.exception("[STORAGE] [VEVOCLOUD] Exception completing upload: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    provider_video_id=str(video_id),
                    error=f"Error finalizing upload: {str(ex)}",
                )

        preliminary_result = StorageProviderResult(
            success=True,
            status=StorageProviderStatus.PROCESSING.value,
            provider=self.name,
            provider_video_id=str(video_id),
            remote_size=file_size,
            raw_metadata=comp_data if 'comp_data' in locals() else {},
        )

        return await self.verify(str(video_id), preliminary_result)

    async def get_status(self, provider_video_id: str) -> StorageProviderResult:
        if not self.api_key or not provider_video_id:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                provider_video_id=provider_video_id,
                error="Missing API key or video ID",
            )

        url = f"{self.base_url}/videos/{provider_video_id}"
        alt_url = f"{self.base_url}/api/videos/{provider_video_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.get(url, headers=self._get_headers(None))
                if res.status_code != 200:
                    res = await client.get(alt_url, headers=self._get_headers(None))

                if res.status_code == 200:
                    data = res.json()
                    hls_link = data.get("hls_link") or data.get("hls_url")
                    embed_link = data.get("embedded_link") or data.get("embed_url")
                    thumbnail_url = data.get("thumbnail_url")
                    title = data.get("title")

                    is_ready = bool(hls_link or embed_link)
                    status_str = StorageProviderStatus.READY.value if is_ready else StorageProviderStatus.PROCESSING.value

                    return StorageProviderResult(
                        success=is_ready,
                        status=status_str,
                        provider=self.name,
                        provider_video_id=provider_video_id,
                        hls_url=hls_link,
                        embed_url=embed_link or hls_link,
                        playback_url=hls_link or embed_link,
                        thumbnail_url=thumbnail_url,
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
        logger.info(f"[STORAGE] [VEVOCLOUD] Verifying videoId={provider_video_id}...")
        start_time = time.time()
        timeout = 60

        while (time.time() - start_time) < timeout:
            status_res = await self.get_status(provider_video_id)
            if status_res.status == StorageProviderStatus.READY.value and (status_res.hls_url or status_res.embed_url):
                logger.info(f"[STORAGE] [VEVOCLOUD] Verified READY: hls={status_res.hls_url} embed={status_res.embed_url}")
                return status_res
            await asyncio.sleep(4)

        # Check final status
        final_status = await self.get_status(provider_video_id)
        if final_status.status == StorageProviderStatus.READY.value and (final_status.hls_url or final_status.embed_url):
            return final_status

        logger.warning(f"[STORAGE] [VEVOCLOUD] Video {provider_video_id} verification timed out after {timeout}s.")
        return StorageProviderResult(
            success=False,
            status=StorageProviderStatus.FAILED.value,
            provider=self.name,
            provider_video_id=provider_video_id,
            error=f"Verification timeout: Vevocloud video {provider_video_id} stream not confirmed ready after {timeout}s",
            raw_metadata=final_status.raw_metadata,
        )

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"provider": self.name, "status": "DISABLED", "healthy": True, "message": "Provider disabled"}
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "healthy": False, "message": "API key missing"}

        url = f"{self.base_url}/categories"
        alt_url = f"{self.base_url}/api/categories"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._get_headers(None))
                if res.status_code != 200:
                    res = await client.get(alt_url, headers=self._get_headers(None))

                if res.status_code == 200:
                    return {"provider": self.name, "status": "ONLINE", "healthy": True, "message": "API connection verified"}
                elif res.status_code in (401, 403):
                    return {"provider": self.name, "status": "AUTH_ERROR", "healthy": False, "message": "Invalid API Key"}
                else:
                    return {"provider": self.name, "status": f"HTTP_{res.status_code}", "healthy": False, "message": res.text[:100]}
        except Exception as ex:
            return {"provider": self.name, "status": "UNREACHABLE", "healthy": False, "message": str(ex)}
