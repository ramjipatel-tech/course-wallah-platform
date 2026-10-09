import os
import re
import time
import logging
import asyncio
from typing import Optional, Dict, Any, Callable
import httpx

from config.settings import (
    VCDN_ENABLED,
    VCDN_API_KEY,
    VCDN_BASE_URL,
    VCDN_LADDER_PROFILE,
    STORAGE_CHUNK_SIZE_BYTES,
    STORAGE_VERIFY_TIMEOUT,
)
from storage.base import (
    BaseVideoStorageProvider,
    StorageProviderResult,
    StorageProviderStatus,
)

logger = logging.getLogger(__name__)


class VcdnStorageProvider(BaseVideoStorageProvider):
    """
    Production implementation of VCDN Developer API (v1.4.0).
    Implements MP4 chunked multipart ingest, status polling, playback-token minting,
    and rigorous verification.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        enabled: Optional[bool] = None,
        priority: int = 1,
        verify_timeout: Optional[int] = None,
    ):
        super().__init__(
            name="vcdn",
            enabled=VCDN_ENABLED if enabled is None else enabled,
            priority=priority,
        )
        self.api_key = re.sub(r"[\r\n\t\s]+", "", str(api_key or VCDN_API_KEY or ""))
        self.base_url = re.sub(r"[\r\n\t\s]+", "", str(base_url or VCDN_BASE_URL or "https://cdn.vcdn.me")).rstrip("/")
        self.ladder_profile = VCDN_LADDER_PROFILE or "standard"
        self.verify_timeout = verify_timeout or STORAGE_VERIFY_TIMEOUT or 60

    def _get_headers(self, content_type: str = "application/json") -> Dict[str, str]:
        headers = {
            "X-API-Key": self.api_key,
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
                error="VCDN provider is disabled in configuration.",
            )

        if not self.api_key:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error="VCDN API key is not configured.",
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

        logger.info(f"[STORAGE] [VCDN] Initiating upload for '{title}' ({file_size} bytes)...")

        async with httpx.AsyncClient(timeout=120.0) as client:
            # Step 1: POST /api/v1/upload/init
            init_url = f"{self.base_url}/api/v1/upload/init"
            init_payload = {
                "filename": filename,
                "size": file_size,
                "contentType": "video/mp4",
                "title": title,
                "ladderProfile": self.ladder_profile,
            }

            try:
                init_res = await client.post(
                    init_url,
                    json=init_payload,
                    headers=self._get_headers("application/json"),
                )
                if init_res.status_code not in (200, 201):
                    err_text = f"Init failed (HTTP {init_res.status_code}): {init_res.text}"
                    logger.error(f"[STORAGE] [VCDN] {err_text}")
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=err_text,
                    )

                init_data = init_res.json()
                upload_id = init_data.get("uploadId") or init_data.get("videoId")
                video_id = init_data.get("videoId") or upload_id
                upload_url_rel = init_data.get("uploadUrl") or f"/api/v1/upload/{upload_id}/chunk"

                if not upload_id or not video_id:
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        error=f"VCDN init response missing uploadId/videoId: {init_data}",
                    )

                logger.info(f"[STORAGE] [VCDN] Session created: uploadId={upload_id} videoId={video_id}")

            except Exception as ex:
                logger.exception("[STORAGE] [VCDN] Exception during upload init: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    error=f"Network error during VCDN upload init: {str(ex)}",
                )

            # Step 2: Upload raw chunks sequentially
            chunk_url = f"{self.base_url}{upload_url_rel}" if upload_url_rel.startswith("/") else upload_url_rel
            bytes_uploaded = 0

            try:
                with open(file_path, "rb") as f:
                    while bytes_uploaded < file_size:
                        chunk_data = f.read(chunk_size)
                        if not chunk_data:
                            break

                        chunk_len = len(chunk_data)
                        chunk_headers = {
                            "X-API-Key": self.api_key,
                            "Content-Type": "application/octet-stream",
                            "Content-Length": str(chunk_len),
                        }

                        # Send chunk with retry on 503
                        chunk_res = None
                        for chunk_attempt in range(1, 4):
                            try:
                                chunk_res = await client.post(
                                    chunk_url,
                                    content=chunk_data,
                                    headers=chunk_headers,
                                    timeout=180.0,
                                )
                                if chunk_res.status_code == 200:
                                    break
                                elif chunk_res.status_code in (502, 503, 504, 409) and chunk_attempt < 3:
                                    await asyncio.sleep(2 * chunk_attempt)
                                else:
                                    break
                            except (httpx.TimeoutException, httpx.NetworkError) as net_err:
                                if chunk_attempt < 3:
                                    await asyncio.sleep(2 * chunk_attempt)
                                else:
                                    raise net_err

                        if not chunk_res or chunk_res.status_code != 200:
                            err_msg = (
                                f"Chunk append failed at offset {bytes_uploaded} "
                                f"(HTTP {chunk_res.status_code if chunk_res else 'No response'}): "
                                f"{chunk_res.text if chunk_res else 'timeout'}"
                            )
                            logger.error(f"[STORAGE] [VCDN] {err_msg}")
                            return StorageProviderResult(
                                success=False,
                                status=StorageProviderStatus.FAILED.value,
                                provider=self.name,
                                provider_video_id=video_id,
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
                logger.exception("[STORAGE] [VCDN] Exception during chunk stream: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    provider_video_id=video_id,
                    error=f"Error streaming chunks: {str(ex)}",
                )

            # Step 3: POST /api/v1/upload/complete
            complete_url = f"{self.base_url}/api/v1/upload/complete"
            try:
                comp_res = await client.post(
                    complete_url,
                    json={"uploadId": upload_id},
                    headers=self._get_headers("application/json"),
                )
                if comp_res.status_code not in (200, 201):
                    err_msg = f"Complete request failed (HTTP {comp_res.status_code}): {comp_res.text}"
                    logger.error(f"[STORAGE] [VCDN] {err_msg}")
                    return StorageProviderResult(
                        success=False,
                        status=StorageProviderStatus.FAILED.value,
                        provider=self.name,
                        provider_video_id=video_id,
                        error=err_msg,
                    )

                comp_data = comp_res.json()
                logger.info(f"[STORAGE] [VCDN] Upload finalized successfully: videoId={video_id}")

            except Exception as ex:
                logger.exception("[STORAGE] [VCDN] Exception during complete request: %s", ex)
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    provider_video_id=video_id,
                    error=f"Error finalizing upload: {str(ex)}",
                )

        # Build preliminary result and proceed to verify
        preliminary_result = StorageProviderResult(
            success=True,
            status=StorageProviderStatus.PROCESSING.value,
            provider=self.name,
            provider_video_id=video_id,
            embed_url=f"https://embed.vcdn.me/embed/{video_id}",
            watch_url=f"https://embed.vcdn.me/embed/{video_id}",
            remote_size=file_size,
            raw_metadata=comp_data if 'comp_data' in locals() else {},
        )

        return await self.verify(video_id, preliminary_result)

    async def get_status(self, provider_video_id: str) -> StorageProviderResult:
        if not self.api_key or not provider_video_id:
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                provider_video_id=provider_video_id,
                error="Missing API key or provider video ID",
            )

        url = f"{self.base_url}/api/v1/videos/{provider_video_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.get(url, headers=self._get_headers())
                if res.status_code == 200:
                    data = res.json()
                    raw_status = (data.get("status") or "").lower()
                    embed_url = data.get("embed_url") or f"https://embed.vcdn.me/embed/{provider_video_id}"
                    
                    status_map = {
                        "ready": StorageProviderStatus.READY.value,
                        "processing": StorageProviderStatus.PROCESSING.value,
                        "transcoding": StorageProviderStatus.PROCESSING.value,
                        "uploading": StorageProviderStatus.UPLOADING.value,
                        "uploaded": StorageProviderStatus.PROCESSING.value,
                        "failed": StorageProviderStatus.FAILED.value,
                    }
                    mapped_status = status_map.get(raw_status, StorageProviderStatus.PROCESSING.value)

                    return StorageProviderResult(
                        success=(mapped_status == StorageProviderStatus.READY.value),
                        status=mapped_status,
                        provider=self.name,
                        provider_video_id=provider_video_id,
                        embed_url=embed_url,
                        watch_url=embed_url,
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
        """
        Polls VCDN with bounded backoff until the video status is READY or timeout.
        Also attempts to fetch playback token to obtain direct HLS stream URL.
        """
        logger.info(f"[STORAGE] [VCDN] Starting verification for videoId={provider_video_id}...")
        start_time = time.time()
        timeout = self.verify_timeout or STORAGE_VERIFY_TIMEOUT or 60
        poll_interval = 3
        max_interval = 8

        while (time.time() - start_time) < timeout:
            status_res = await self.get_status(provider_video_id)
            if status_res.status == StorageProviderStatus.READY.value:
                # Video is ready in VCDN! Now mint playback token to get streamUrl if available
                stream_url = None
                try:
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        tok_url = f"{self.base_url}/api/v1/videos/{provider_video_id}/playback-token"
                        tok_res = await client.post(
                            tok_url,
                            json={"ttlSeconds": 86400},
                            headers=self._get_headers(),
                        )
                        if tok_res.status_code == 200:
                            tok_data = tok_res.json()
                            stream_url = tok_data.get("streamUrl")
                except Exception as tok_err:
                    logger.debug(f"[STORAGE] [VCDN] Playback token notice: {tok_err}")

                embed_url = status_res.embed_url or f"https://embed.vcdn.me/embed/{provider_video_id}"
                logger.info(f"[STORAGE] [VCDN] Video verified READY: embed={embed_url} hls={stream_url}")

                return StorageProviderResult(
                    success=True,
                    status=StorageProviderStatus.READY.value,
                    provider=self.name,
                    provider_video_id=provider_video_id,
                    embed_url=embed_url,
                    watch_url=embed_url,
                    hls_url=stream_url,
                    playback_url=stream_url or embed_url,
                    remote_size=upload_result.remote_size if upload_result else 0,
                    raw_metadata=status_res.raw_metadata,
                )

            elif status_res.status == StorageProviderStatus.FAILED.value:
                logger.error(f"[STORAGE] [VCDN] Verification failed: {status_res.error}")
                return StorageProviderResult(
                    success=False,
                    status=StorageProviderStatus.FAILED.value,
                    provider=self.name,
                    provider_video_id=provider_video_id,
                    error=status_res.error or "Transcoding failed on remote provider",
                    raw_metadata=status_res.raw_metadata,
                )

            await asyncio.sleep(poll_interval)
            poll_interval = min(poll_interval + 1, max_interval)

        # If verification timeout expired, check current status one last time
        final_status = await self.get_status(provider_video_id)
        if final_status.status == StorageProviderStatus.READY.value:
            return final_status
        elif final_status.status in (StorageProviderStatus.PROCESSING.value, StorageProviderStatus.UPLOADING.value):
            logger.info(f"[STORAGE] [VCDN] Video {provider_video_id} is still transcoding remotely (status={final_status.status}). Returning PROCESSING.")
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.PROCESSING.value,
                provider=self.name,
                provider_video_id=provider_video_id,
                embed_url=final_status.embed_url or f"https://embed.vcdn.me/embed/{provider_video_id}",
                watch_url=final_status.watch_url or f"https://embed.vcdn.me/embed/{provider_video_id}",
                error=f"VCDN video {provider_video_id} is transcoding asynchronously on remote server (status: {final_status.status})",
                raw_metadata=final_status.raw_metadata,
            )

        logger.warning(f"[STORAGE] [VCDN] Video {provider_video_id} did not reach READY within {timeout}s timeout (status={final_status.status}).")
        return StorageProviderResult(
            success=False,
            status=StorageProviderStatus.FAILED.value,
            provider=self.name,
            provider_video_id=provider_video_id,
            error=f"Verification timeout: VCDN video {provider_video_id} is in status '{final_status.status}' after {timeout}s",
            raw_metadata=final_status.raw_metadata,
        )

    async def delete(self, provider_video_id: str) -> bool:
        if not self.api_key or not provider_video_id:
            return False
        url = f"{self.base_url}/api/v1/videos/{provider_video_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                res = await client.delete(url, headers=self._get_headers())
                return res.status_code in (200, 204)
            except Exception:
                return False

    async def health_check(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"provider": self.name, "status": "DISABLED", "healthy": True, "message": "Provider disabled"}
        if not self.api_key:
            return {"provider": self.name, "status": "NOT_CONFIGURED", "healthy": False, "message": "API key missing"}

        url = f"{self.base_url}/api/v1/videos?limit=1"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.get(url, headers=self._get_headers())
                if res.status_code == 200:
                    return {"provider": self.name, "status": "ONLINE", "healthy": True, "message": "API connection verified"}
                elif res.status_code in (401, 403):
                    return {"provider": self.name, "status": "AUTH_ERROR", "healthy": False, "message": "Invalid API Key"}
                else:
                    return {"provider": self.name, "status": f"HTTP_{res.status_code}", "healthy": False, "message": res.text[:100]}
        except Exception as ex:
            return {"provider": self.name, "status": "UNREACHABLE", "healthy": False, "message": str(ex)}
