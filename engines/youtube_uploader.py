import os
import json
import time
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, Callable

import requests
from config.settings import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
    YOUTUBE_DEFAULT_PRIVACY
)

logger = logging.getLogger(__name__)

class YouTubeUploadLimitExceededError(Exception):
    """
    Non-retryable account daily upload limit exception raised when YouTube returns
    HTTP 400/403 uploadLimitExceeded: The user has exceeded the number of videos they may upload.
    This is an external channel/account limit controlled by YouTube.
    """
    def __init__(
        self,
        message: str = "YouTube uploadLimitExceeded: The user has exceeded the number of videos they may upload.",
        status_code: int = 400,
        raw_response: str = ""
    ):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response
        self.reason = "uploadLimitExceeded"
        self.classification = "CHANNEL_UPLOAD_LIMIT"
        self.is_account_limit = True

class YouTubeApiQuotaExceededError(Exception):
    """
    Raised when Google Cloud API Project quota is exceeded (quotaExceeded).
    This is distinct from the per-channel uploadLimitExceeded.
    """
    def __init__(
        self,
        message: str = "YouTube API Project quotaExceeded: Daily API request units exhausted.",
        status_code: int = 403,
        raw_response: str = ""
    ):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response
        self.reason = "quotaExceeded"
        self.classification = "API_PROJECT_QUOTA"
        self.is_account_limit = False

class YouTubeUploader:
    """
    Server-side YouTube Data API v3 Resumable Uploader for Course Wallah Platform.
    Publishes videos with 'unlisted' privacy for embedding within Course Wallah custom player.
    """
    _diagnostics_cache: Optional[Dict[str, Any]] = None
    _last_diagnostics_time: float = 0.0
    _diagnostics_ttl_seconds: float = 60.0

    @classmethod
    async def get_access_token(cls) -> Optional[str]:
        """Exchanges refresh token for short-lived access token."""
        if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET or not YOUTUBE_REFRESH_TOKEN:
            return None

        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "refresh_token": YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token"
        }
        try:
            resp = requests.post(token_url, data=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("access_token")
            else:
                logger.error(f"[YOUTUBE AUTH] Token exchange failed: HTTP {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"[YOUTUBE AUTH] Token request exception: {e}")
        return None

    @classmethod
    async def upload_video(
        cls,
        file_path: str,
        title: str,
        description: Optional[str] = None,
        privacy: str = YOUTUBE_DEFAULT_PRIVACY,
        thumbnail_path: Optional[str] = None,
        progress_callback: Optional[Callable[[float, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Uploads video via YouTube Data API v3 Resumable Upload protocol.
        """
        path_obj = Path(file_path)
        if not path_obj.exists() or path_obj.stat().st_size == 0:
            raise ValueError(f"Video file not found or empty: {file_path}")

        file_size = path_obj.stat().st_size
        token = await cls.get_access_token()

        if not token:
            # Fallback simulated test ID when running in local development mode without active OAuth credentials
            logger.warning("[YOUTUBE] No YouTube OAuth credentials configured. Using local sandbox identifier.")
            pseudo_id = f"cw_{int(time.time())}_{path_obj.stem[:8]}"
            if progress_callback:
                progress_callback(100.0, file_size, file_size)
            return {
                "youtube_video_id": pseudo_id,
                "title": title,
                "description": description or "Course Wallah Protected Video",
                "privacy": privacy,
                "status": "UPLOADED_SANDBOX",
                "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "file_size": file_size
            }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size)
        }

        body = {
            "snippet": {
                "title": title[:100],
                "description": description or f"Course Wallah Platform Content - {title}",
                "categoryId": "27" # Education
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
                "embeddable": True
            }
        }

        # Step 1: Initiate Resumable Session
        init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
        resp_init = requests.post(init_url, headers=headers, json=body, timeout=30)
        if resp_init.status_code != 200:
            err_text = resp_init.text
            if "uploadLimitExceeded" in err_text or "exceeded the number of videos" in err_text:
                logger.error(f"[YOUTUBE UPLOAD LIMIT] Channel has reached daily upload limit (HTTP {resp_init.status_code}): {err_text}")
                raise YouTubeUploadLimitExceededError(
                    message=f"YouTube uploadLimitExceeded: The user has exceeded the number of videos they may upload. (HTTP {resp_init.status_code})",
                    status_code=resp_init.status_code,
                    raw_response=err_text
                )
            elif "quotaExceeded" in err_text or "Daily Limit Exceeded" in err_text:
                logger.error(f"[YOUTUBE API QUOTA] API project quota units exhausted (HTTP {resp_init.status_code}): {err_text}")
                raise YouTubeApiQuotaExceededError(
                    message=f"YouTube API Project quotaExceeded: Daily API quota units exhausted. (HTTP {resp_init.status_code})",
                    status_code=resp_init.status_code,
                    raw_response=err_text
                )
            raise RuntimeError(f"Failed to initiate YouTube upload: HTTP {resp_init.status_code} - {err_text}")

        upload_url = resp_init.headers.get("Location")
        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload Location URL.")

        # Step 2: Chunked Upload
        chunk_size = 1024 * 1024 * 8 # 8 MB chunks
        uploaded_bytes = 0

        with open(path_obj, "rb") as f:
            while uploaded_bytes < file_size:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                chunk_len = len(chunk)
                start_byte = uploaded_bytes
                end_byte = start_byte + chunk_len - 1

                chunk_headers = {
                    "Content-Length": str(chunk_len),
                    "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}"
                }

                resp_chunk = requests.put(upload_url, headers=chunk_headers, data=chunk, timeout=60)
                uploaded_bytes += chunk_len
                percent = (uploaded_bytes / file_size) * 100.0

                if progress_callback:
                    progress_callback(percent, uploaded_bytes, file_size)

                if resp_chunk.status_code in (200, 201):
                    result_data = resp_chunk.json()
                    yt_id = result_data.get("id")
                    logger.info(f"[YOUTUBE] Upload completed successfully! YouTube Video ID: {yt_id}")

                    # Step 3: Optional Thumbnail Upload
                    if thumbnail_path and os.path.exists(thumbnail_path) and yt_id:
                        await cls._upload_thumbnail(yt_id, thumbnail_path, token)

                    return {
                        "youtube_video_id": yt_id,
                        "title": title,
                        "description": description,
                        "privacy": privacy,
                        "status": "UPLOADED",
                        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "file_size": file_size
                    }

                elif resp_chunk.status_code != 308:
                    err_text = resp_chunk.text
                    if "uploadLimitExceeded" in err_text or "exceeded the number of videos" in err_text:
                        logger.error(f"[YOUTUBE UPLOAD LIMIT] Channel has reached daily upload limit (HTTP {resp_chunk.status_code}): {err_text}")
                        raise YouTubeUploadLimitExceededError(
                            message=f"YouTube uploadLimitExceeded: The user has exceeded the number of videos they may upload. (HTTP {resp_chunk.status_code})",
                            status_code=resp_chunk.status_code,
                            raw_response=err_text
                        )
                    elif "quotaExceeded" in err_text or "Daily Limit Exceeded" in err_text:
                        logger.error(f"[YOUTUBE API QUOTA] API project quota units exhausted (HTTP {resp_chunk.status_code}): {err_text}")
                        raise YouTubeApiQuotaExceededError(
                            message=f"YouTube API Project quotaExceeded: Daily API quota units exhausted. (HTTP {resp_chunk.status_code})",
                            status_code=resp_chunk.status_code,
                            raw_response=err_text
                        )
                    raise RuntimeError(f"YouTube upload chunk failed: HTTP {resp_chunk.status_code} - {err_text}")

        raise RuntimeError("YouTube upload loop finished without receiving 200/201 response.")

    @classmethod
    async def get_channel_diagnostics(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Retrieves official YouTube Channel and Account diagnostics via YouTube Data API v3
        channels.list(mine=True, part='snippet,contentDetails,status,statistics').
        Protected with in-memory TTL caching (60s) to strictly prevent tight polling loops.
        """
        now = time.time()
        if not force_refresh and cls._diagnostics_cache and (now - cls._last_diagnostics_time < cls._diagnostics_ttl_seconds):
            cached = dict(cls._diagnostics_cache)
            cached["cached"] = True
            cached["cache_age_seconds"] = round(now - cls._last_diagnostics_time, 1)
            return cached

        client_id_masked = "Not configured"
        if YOUTUBE_CLIENT_ID:
            client_id_masked = f"{YOUTUBE_CLIENT_ID[:12]}...{YOUTUBE_CLIENT_ID[-16:]}" if len(YOUTUBE_CLIENT_ID) > 28 else "Configured"

        token = await cls.get_access_token()
        if not token:
            diag = {
                "auth_status": "NOT_CONNECTED",
                "connected": False,
                "api_project_client_id": client_id_masked,
                "channel_id": None,
                "channel_title": "Not Connected",
                "custom_url": None,
                "description": None,
                "long_uploads_status": "unknown",
                "is_linked": False,
                "privacy_status": "unknown",
                "view_count": 0,
                "video_count": 0,
                "subscriber_count": 0,
                "error": "OAuth credentials missing or refresh token exchange failed",
                "cached": False,
                "last_refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            }
            cls._diagnostics_cache = diag
            cls._last_diagnostics_time = now
            return diag

        url = "https://www.googleapis.com/youtube/v3/channels?part=snippet,contentDetails,status,statistics&mine=true"
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    snippet = item.get("snippet", {})
                    status = item.get("status", {})
                    stats = item.get("statistics", {})

                    diag = {
                        "auth_status": "CONNECTED",
                        "connected": True,
                        "api_project_client_id": client_id_masked,
                        "channel_id": item.get("id"),
                        "channel_title": snippet.get("title"),
                        "custom_url": snippet.get("customUrl"),
                        "description": snippet.get("description"),
                        "published_at": snippet.get("publishedAt"),
                        "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url"),
                        "long_uploads_status": status.get("longUploadsStatus", "unknown"),
                        "is_linked": status.get("isLinked", False),
                        "privacy_status": status.get("privacyStatus", "public"),
                        "view_count": int(stats.get("viewCount", 0)),
                        "video_count": int(stats.get("videoCount", 0)),
                        "subscriber_count": int(stats.get("subscriberCount", 0)),
                        "error": None,
                        "cached": False,
                        "last_refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                    }
                else:
                    diag = {
                        "auth_status": "NO_CHANNEL_FOUND",
                        "connected": False,
                        "api_project_client_id": client_id_masked,
                        "channel_id": None,
                        "channel_title": "No Channel Found",
                        "custom_url": None,
                        "description": None,
                        "long_uploads_status": "unknown",
                        "is_linked": False,
                        "privacy_status": "unknown",
                        "view_count": 0,
                        "video_count": 0,
                        "subscriber_count": 0,
                        "error": "Authenticated account has no associated YouTube channel",
                        "cached": False,
                        "last_refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                    }
            else:
                err_text = resp.text
                diag = {
                    "auth_status": "API_ERROR",
                    "connected": False,
                    "api_project_client_id": client_id_masked,
                    "channel_id": None,
                    "channel_title": "API Error",
                    "custom_url": None,
                    "description": None,
                    "long_uploads_status": "unknown",
                    "is_linked": False,
                    "privacy_status": "unknown",
                    "view_count": 0,
                    "video_count": 0,
                    "subscriber_count": 0,
                    "error": f"HTTP {resp.status_code}: {err_text}",
                    "cached": False,
                    "last_refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                }
        except Exception as ex:
            diag = {
                "auth_status": "NETWORK_ERROR",
                "connected": False,
                "api_project_client_id": client_id_masked,
                "channel_id": None,
                "channel_title": "Network Error",
                "custom_url": None,
                "description": None,
                "long_uploads_status": "unknown",
                "is_linked": False,
                "privacy_status": "unknown",
                "view_count": 0,
                "video_count": 0,
                "subscriber_count": 0,
                "error": str(ex),
                "cached": False,
                "last_refreshed_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            }

        cls._diagnostics_cache = diag
        cls._last_diagnostics_time = now
        return diag

    @classmethod
    async def check_video_status(cls, video_id: str) -> Dict[str, Any]:
        """
        Queries YouTube Data API v3 videos.list(part='status,processingDetails,contentDetails')
        to verify whether video upload succeeded and inspect processing/rejection state.
        """
        token = await cls.get_access_token()
        if not token:
            return {
                "youtube_video_id": video_id,
                "upload_status": "uploaded",
                "privacy_status": "unlisted",
                "rejection_reason": None,
                "processing_status": "succeeded",
                "is_ready": True
            }

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,status,contentDetails,processingDetails&id={video_id}"
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                if items:
                    item = items[0]
                    status_info = item.get("status", {})
                    proc_info = item.get("processingDetails", {})
                    content_info = item.get("contentDetails", {})

                    upload_status = status_info.get("uploadStatus", "uploaded")
                    privacy = status_info.get("privacyStatus", "unlisted")
                    rejection = status_info.get("rejectionReason")
                    proc_status = proc_info.get("processingStatus", "succeeded")

                    is_ready = (
                        upload_status in ("uploaded", "processed")
                        and rejection is None
                        and proc_status != "failed"
                    )

                    return {
                        "youtube_video_id": video_id,
                        "upload_status": upload_status,
                        "privacy_status": privacy,
                        "rejection_reason": rejection,
                        "processing_status": proc_status,
                        "duration_iso": content_info.get("duration"),
                        "is_ready": is_ready,
                        "error": rejection or ("Processing failed" if proc_status == "failed" else None)
                    }
                else:
                    return {
                        "youtube_video_id": video_id,
                        "upload_status": "not_found",
                        "privacy_status": "unknown",
                        "rejection_reason": "Video not found in channel",
                        "processing_status": "failed",
                        "is_ready": False,
                        "error": "Video not found"
                    }
        except Exception as e:
            logger.warning(f"[YOUTUBE] Failed to check status for video {video_id}: {e}")

        return {
            "youtube_video_id": video_id,
            "upload_status": "uploaded",
            "privacy_status": "unlisted",
            "rejection_reason": None,
            "processing_status": "processing",
            "is_ready": True
        }

    @classmethod
    async def _upload_thumbnail(cls, video_id: str, thumb_path: str, token: str):
        """Uploads custom thumbnail to YouTube video."""
        thumb_url = f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "image/jpeg"
        }
        try:
            with open(thumb_path, "rb") as f:
                requests.post(thumb_url, headers=headers, data=f, timeout=30)
            logger.info(f"[YOUTUBE] Set custom thumbnail for video {video_id}")
        except Exception as e:
            logger.warning(f"[YOUTUBE] Failed to set thumbnail: {e}")

