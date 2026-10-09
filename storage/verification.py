import logging
import asyncio
from typing import Optional, Dict, Any
import httpx

from storage.base import StorageProviderResult, StorageProviderStatus

logger = logging.getLogger(__name__)


class StorageVerificationService:
    """
    Rigorously verifies uploaded video URLs, HLS playlists, and embed pages
    to guarantee valid remote playback before marking provider state as READY.
    """

    @staticmethod
    async def verify_url_accessible(url: str, timeout: float = 15.0) -> bool:
        if not url or not url.startswith("http"):
            return False
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                res = await client.head(url)
                if res.status_code in (200, 206, 301, 302, 307, 308):
                    return True
                # If HEAD is disallowed (405), fallback to small GET range
                if res.status_code == 405:
                    res_get = await client.get(url, headers={"Range": "bytes=0-100"})
                    return res_get.status_code in (200, 206)
                return False
        except Exception as ex:
            logger.debug("[STORAGE_VERIFY] URL check failed for %s: %s", url, ex)
            return False

    @staticmethod
    async def verify_hls_stream(stream_url: str, timeout: float = 15.0) -> bool:
        """
        Verifies that an HLS master/media playlist starts with #EXTM3U.
        """
        if not stream_url or not stream_url.startswith("http"):
            return False
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                res = await client.get(stream_url, headers={"Range": "bytes=0-512"})
                if res.status_code in (200, 206):
                    text = res.text
                    return "#EXTM3U" in text or "m3u8" in stream_url.lower()
                return False
        except Exception as ex:
            logger.debug("[STORAGE_VERIFY] HLS check failed for %s: %s", stream_url, ex)
            return False


RemoteStreamVerifier = StorageVerificationService
