import os
import json
import time
import shutil
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

from config.settings import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
    YOUTUBE_DEFAULT_PRIVACY,
    DOWNLOADS_DIR,
    MAX_RETRIES,
    RETRY_DELAY
)
from db.connection import get_db_session
from db.models import YouTubeAccount, YouTubeAccountStatus, YouTubeUpload, Video, Lecture, JobStatus
from db.repository import ContentRepository
from engines.youtube_uploader import (
    YouTubeUploader,
    YouTubeUploadLimitExceededError,
    YouTubeApiQuotaExceededError
)

logger = logging.getLogger(__name__)

# Default estimated daily limit per channel (Standard YouTube channels typically allow 10 to 100 uploads/day depending on verification level)
DEFAULT_ESTIMATED_DAILY_LIMIT = 20


class YouTubeAccountAuthError(Exception):
    """Raised when YouTube authentication fails permanently (invalid_grant, revoked token, unauthorized_client)."""
    def __init__(self, message: str, status_code: int = 401, raw_response: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response
        self.classification = "AUTH_ERROR"
        self.is_account_limit = False


class YouTubeTemporaryUploadError(Exception):
    """Raised for transient 429 / 5xx / network errors that can be retried on the same account."""
    def __init__(self, message: str, status_code: int = 500, raw_response: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response
        self.classification = "TEMPORARY"
        self.is_account_limit = False


class YouTubePermanentUploadError(Exception):
    """Raised for non-retryable metadata, format, or bad request errors."""
    def __init__(self, message: str, status_code: int = 400, raw_response: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.raw_response = raw_response
        self.classification = "PERMANENT"
        self.is_account_limit = False


class YouTubeAccountManager:
    """
    Production-Grade Multi-Account Failover & Limit-Aware Orchestrator for YouTube Uploads.
    
    Responsibilities:
    - Sync primary account from environment configuration
    - Deterministic account selection based on ACTIVE status, priority, and load
    - Accurate error classification (CHANNEL_UPLOAD_LIMIT vs API_QUOTA vs AUTH_ERROR vs TEMPORARY vs PERMANENT)
    - Automatic account rotation upon daily uploadLimitExceeded without redownloading/reprocessing
    - Durable disk + database checkpoint management
    - Zero duplicate upload protection
    - Server disk cleanup after successful YouTube upload
    - Sanitized diagnostic reporting for Telegram & Admin API
    """

    @classmethod
    def classify_error(
        cls,
        status_code: int,
        response_text: str = "",
        exc: Optional[Exception] = None
    ) -> str:
        """
        Classifies an API/network error into:
        - CHANNEL_UPLOAD_LIMIT
        - API_PROJECT_QUOTA
        - AUTH_ERROR
        - TEMPORARY
        - PERMANENT
        """
        lower_text = (response_text or "").lower()
        if exc:
            lower_text += " " + str(exc).lower()

        # 1. CHANNEL DAILY UPLOAD LIMIT (External Google Per-Channel Restriction)
        if (
            "uploadlimitexceeded" in lower_text
            or "exceeded the number of videos" in lower_text
            or "daily upload limit" in lower_text
            or "user has exceeded the upload limit" in lower_text
            or isinstance(exc, YouTubeUploadLimitExceededError)
        ):
            return "CHANNEL_UPLOAD_LIMIT"

        # 2. API PROJECT QUOTA (GCP Quota Units)
        if (
            "quotaexceeded" in lower_text
            or "daily limit exceeded" in lower_text
            or isinstance(exc, YouTubeApiQuotaExceededError)
        ):
            return "API_PROJECT_QUOTA"

        # 3. AUTHENTICATION ERRORS
        if (
            "invalid_grant" in lower_text
            or "unauthorized_client" in lower_text
            or "unauthorized" in lower_text
            or "invalid_client" in lower_text
            or "invalid credentials" in lower_text
            or "token has been expired or revoked" in lower_text
            or status_code in (401, 403) and ("auth" in lower_text or "token" in lower_text or "credentials" in lower_text)
            or isinstance(exc, YouTubeAccountAuthError)
        ):
            return "AUTH_ERROR"

        # 4. TEMPORARY (Transient HTTP 429, 5xx, or network issues)
        if (
            status_code in (429, 500, 502, 503, 504)
            or "timeout" in lower_text
            or "connection reset" in lower_text
            or "connection error" in lower_text
            or "broken pipe" in lower_text
            or isinstance(exc, (YouTubeTemporaryUploadError, TimeoutError, ConnectionError))
        ):
            return "TEMPORARY"

        # 5. PERMANENT (Bad request, invalid metadata, corrupted media)
        return "PERMANENT"

    @classmethod
    async def sync_primary_from_env(cls) -> Optional[YouTubeAccount]:
        """
        Ensures the YouTube configuration from .env is synced into the database
        as the primary (priority=1) active account.
        """
        if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET or not YOUTUBE_REFRESH_TOKEN:
            return None

        async with get_db_session() as session:
            repo = ContentRepository(session)
            await repo.reset_account_quotas_if_needed()

            # Check if an account already exists with these credentials
            accounts = await repo.get_all_youtube_accounts()
            primary_acc = None
            for acc in accounts:
                if acc.client_id == YOUTUBE_CLIENT_ID and acc.refresh_token == YOUTUBE_REFRESH_TOKEN:
                    primary_acc = acc
                    break

            if not primary_acc:
                # Create primary account
                primary_acc = await repo.create_or_update_youtube_account(
                    name="TECHNICAL CLASSES (Primary)",
                    client_id=YOUTUBE_CLIENT_ID,
                    client_secret=YOUTUBE_CLIENT_SECRET,
                    refresh_token=YOUTUBE_REFRESH_TOKEN,
                    status=YouTubeAccountStatus.ACTIVE.value,
                    priority=1
                )
                logger.info(f"[YOUTUBE_MANAGER] Synced primary YouTube account from .env (ID: {primary_acc.id})")
            else:
                # Ensure priority is 1 and status is ACTIVE if it was disabled by tests
                changed = False
                if primary_acc.priority != 1:
                    primary_acc.priority = 1
                    changed = True
                if primary_acc.status != YouTubeAccountStatus.ACTIVE.value and primary_acc.status != YouTubeAccountStatus.LIMIT_REACHED.value:
                    primary_acc.status = YouTubeAccountStatus.ACTIVE.value
                    changed = True
                if primary_acc.client_secret != YOUTUBE_CLIENT_SECRET:
                    primary_acc.client_secret = YOUTUBE_CLIENT_SECRET
                    changed = True
                if changed:
                    await session.flush()

            return primary_acc

    @classmethod
    async def select_youtube_account(cls, exclude_account_ids: Optional[List[str]] = None) -> Optional[YouTubeAccount]:
        """
        Selects the next eligible YouTube account:
        - Only ACTIVE accounts
        - Excludes accounts currently LIMIT_REACHED or in cooldown
        - Deterministically ordered by priority ASC, uploads_today ASC, created_at ASC
        """
        # First ensure .env primary account exists
        await cls.sync_primary_from_env()

        async with get_db_session() as session:
            repo = ContentRepository(session)
            await repo.reset_account_quotas_if_needed()

            accounts = await repo.get_all_youtube_accounts()
            now = datetime.utcnow()
            eligible = []
            excludes = set(exclude_account_ids or [])

            for acc in accounts:
                if acc.id in excludes:
                    continue

                # Check status
                if acc.status != YouTubeAccountStatus.ACTIVE.value:
                    continue

                # Check cooldown
                if acc.cooldown_until and acc.cooldown_until > now:
                    continue

                eligible.append(acc)

            if not eligible:
                logger.warning("[YOUTUBE_MANAGER] No eligible ACTIVE YouTube accounts available.")
                return None

            # Deterministic sorting: priority ASC (1 is highest), uploads_today ASC (least loaded), created_at ASC
            eligible.sort(key=lambda a: (a.priority or 99, a.uploads_today or 0, a.created_at or datetime.min))
            selected = eligible[0]
            logger.info(f"[YOUTUBE_MANAGER] Selected account '{selected.name}' (ID: {selected.id}, Uploads today: {selected.uploads_today}, Priority: {selected.priority})")
            return selected

    @classmethod
    def get_checkpoint_dir(cls, batch_id: str, lecture_index: int) -> Path:
        """Returns the durable checkpoint directory for a lecture."""
        ckpt_dir = Path(DOWNLOADS_DIR) / "checkpoints" / str(batch_id) / f"lec_{lecture_index:04d}"
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        return ckpt_dir

    @classmethod
    def save_checkpoint(
        cls,
        batch_id: str,
        lecture_id: Optional[str],
        lecture_index: int,
        title: str,
        prepared_video_path: str,
        thumbnail_path: Optional[str] = None,
        selected_account_id: Optional[str] = None,
        stage: str = "WATERMARKED_READY_FOR_UPLOAD",
        reason: str = "uploadLimitExceeded",
        duration: float = 0.0,
        resolution: str = "1080p",
        file_size: int = 0,
        last_error: Optional[str] = None
    ) -> Path:
        """
        Saves durable checkpoint on disk and preserves prepared video and thumbnail artifacts.
        """
        ckpt_dir = cls.get_checkpoint_dir(batch_id, lecture_index)
        ckpt_file = ckpt_dir / "youtube_upload_checkpoint.json"

        # Copy watermarked video to durable checkpoint location if not already inside it
        dest_wm = ckpt_dir / "wm_video.mp4"
        if os.path.exists(prepared_video_path):
            src_p = Path(prepared_video_path).resolve()
            dst_p = dest_wm.resolve()
            if src_p != dst_p:
                shutil.copy2(prepared_video_path, dest_wm)
            if file_size == 0:
                file_size = dest_wm.stat().st_size

        dest_thumb = None
        if thumbnail_path and os.path.exists(thumbnail_path):
            thumb_dest = ckpt_dir / "thumb.jpg"
            src_t = Path(thumbnail_path).resolve()
            dst_t = thumb_dest.resolve()
            if src_t != dst_t:
                shutil.copy2(thumbnail_path, thumb_dest)
            dest_thumb = "thumb.jpg"

        payload = {
            "job_id": f"batch_{str(batch_id)[:8]}_lec_{lecture_index:04d}",
            "lecture_id": lecture_id,
            "lecture_index": lecture_index,
            "title": title,
            "prepared_video_path": str(dest_wm),
            "wm_file": "wm_video.mp4",
            "thumbnail_path": str(ckpt_dir / "thumb.jpg") if dest_thumb else None,
            "thumb_file": dest_thumb,
            "selected_account_id": selected_account_id,
            "status": "WAITING_FOR_YOUTUBE_ACCOUNT",
            "stage": stage,
            "reason": reason,
            "duration": duration,
            "resolution": resolution,
            "file_size": file_size,
            "last_error": last_error,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        ckpt_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Also write legacy checkpoint.json for backwards compatibility
        (ckpt_dir / "checkpoint.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"[CHECKPOINT_SAVED] lecture_index=#{lecture_index} reason='{reason}' path={ckpt_file}")
        return ckpt_file

    @classmethod
    def load_checkpoint(cls, batch_id: str, lecture_index: int) -> Optional[Dict[str, Any]]:
        """Loads durable checkpoint if present and valid."""
        ckpt_dir = Path(DOWNLOADS_DIR) / "checkpoints" / str(batch_id) / f"lec_{lecture_index:04d}"
        for filename in ["youtube_upload_checkpoint.json", "checkpoint.json"]:
            fpath = ckpt_dir / filename
            if fpath.exists():
                try:
                    data = json.loads(fpath.read_text("utf-8"))
                    wm_candidate = ckpt_dir / data.get("wm_file", "wm_video.mp4")
                    if wm_candidate.exists() and wm_candidate.stat().st_size > 1024:
                        data["prepared_video_path"] = str(wm_candidate)
                        thumb_cand = (ckpt_dir / data["thumb_file"]) if data.get("thumb_file") else None
                        if thumb_cand and thumb_cand.exists():
                            data["thumbnail_path"] = str(thumb_cand)
                        return data
                except Exception as e:
                    logger.debug(f"[CHECKPOINT_LOAD_ERROR] {e}")
        return None

    @classmethod
    def clear_checkpoint(cls, batch_id: str, lecture_index: int):
        """Cleans up checkpoint directory after successful upload."""
        ckpt_dir = Path(DOWNLOADS_DIR) / "checkpoints" / str(batch_id) / f"lec_{lecture_index:04d}"
        if ckpt_dir.exists():
            shutil.rmtree(ckpt_dir, ignore_errors=True)
            logger.info(f"[CHECKPOINT_CLEARED] lecture_index=#{lecture_index}")

    @classmethod
    async def upload_with_multi_account_failover(
        cls,
        file_path: str,
        title: str,
        description: Optional[str] = None,
        privacy: str = YOUTUBE_DEFAULT_PRIVACY,
        thumbnail_path: Optional[str] = None,
        batch_id: Optional[str] = None,
        lecture_id: Optional[str] = None,
        lecture_index: int = 1,
        duration: float = 0.0,
        resolution: str = "1080p",
        progress_callback: Optional[Callable[[float, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes YouTube upload with automatic account rotation and failover.
        
        1. Checks duplicate protection (DB video_id check).
        2. Selects an active account.
        3. Attempts upload.
        4. If account hits limit (uploadLimitExceeded):
           - Checkpoints prepared artifact.
           - Marks account LIMIT_REACHED with cooldown.
           - Rotates to next active account.
           - Continues seamlessly with the exact same prepared artifact.
        5. If all accounts exhausted:
           - Saves durable checkpoint.
           - Raises YouTubeUploadLimitExceededError so batch pauses gracefully.
        6. On success:
           - Immediately records DB relations.
           - Cleans up server disk video file.
           - Clears checkpoint.
        """
        # DUPLICATE PROTECTION: Check if lecture is already uploaded in DB
        if lecture_id:
            async with get_db_session() as session:
                repo = ContentRepository(session)
                existing_lec = await repo.get_lecture_by_id(lecture_id)
                if existing_lec and existing_lec.video and existing_lec.video.youtube_video_id:
                    v_id = existing_lec.video.youtube_video_id
                    logger.info(f"[DUPLICATE_PROTECTION] Lecture #{lecture_index} already has YouTube video ID {v_id}. Skipping upload.")
                    return {
                        "youtube_video_id": v_id,
                        "title": title,
                        "description": description,
                        "privacy": privacy,
                        "status": "ALREADY_UPLOADED",
                        "youtube_account_id": existing_lec.video.youtube_account_id,
                        "youtube_channel_id": existing_lec.video.youtube_channel_id,
                        "account_id": existing_lec.video.youtube_account_id,
                        "channel_id": existing_lec.video.youtube_channel_id,
                        "uploaded_at": existing_lec.video.upload_completed_at.isoformat() if existing_lec.video.upload_completed_at else None,
                        "file_size": existing_lec.video.file_size
                    }

        tried_account_ids: List[str] = []

        while True:
            account = await cls.select_youtube_account(exclude_account_ids=tried_account_ids)

            if not account:
                # No eligible accounts available
                err_msg = (
                    f"All configured YouTube accounts are currently unavailable, limit reached, or in cooldown. "
                    f"Tried {len(tried_account_ids)} accounts."
                )
                logger.warning(f"[YOUTUBE_NO_ACCOUNT_AVAILABLE] batch_id={batch_id} lec=#{lecture_index}: {err_msg}")
                
                # Save durable checkpoint
                if batch_id:
                    cls.save_checkpoint(
                        batch_id=str(batch_id),
                        lecture_id=lecture_id,
                        lecture_index=lecture_index,
                        title=title,
                        prepared_video_path=file_path,
                        thumbnail_path=thumbnail_path,
                        stage="WAITING_FOR_YOUTUBE_ACCOUNT",
                        reason="No active YouTube account available or all accounts limit reached",
                        duration=duration,
                        resolution=resolution,
                        last_error=err_msg
                    )

                raise YouTubeUploadLimitExceededError(
                    message=f"YouTube daily upload limit reached across all accounts. Prepared video is checkpointed. {err_msg}",
                    status_code=400,
                    raw_response="uploadLimitExceeded: No active account available"
                )

            account_id = account.id
            account_name = account.name
            client_id = account.client_id
            client_secret = account.client_secret
            refresh_token = account.refresh_token

            logger.info(f"[YOUTUBE_UPLOAD_ATTEMPT] Using account '{account_name}' (ID: {account_id}) for lecture #{lecture_index} '{title}'")

            try:
                # Exchange token for this account
                token = await cls._get_account_access_token(client_id, client_secret, refresh_token)
                
                if not token:
                    # Mark account AUTH_ERROR
                    logger.error(f"[YOUTUBE_AUTH_ERROR] Token exchange failed for account '{account_name}' (ID: {account_id})")
                    async with get_db_session() as session:
                        repo = ContentRepository(session)
                        await repo.mark_youtube_account_status(
                            account_id=account_id,
                            status=YouTubeAccountStatus.AUTH_ERROR.value,
                            last_error="OAuth token exchange failed (unauthorized_client or invalid_grant)",
                            last_error_type="AUTH_ERROR"
                        )
                    tried_account_ids.append(account_id)
                    continue

                # Execute upload with this account's token
                upload_result = await cls._execute_resumable_upload(
                    file_path=file_path,
                    title=title,
                    description=description,
                    privacy=privacy,
                    thumbnail_path=thumbnail_path,
                    token=token,
                    progress_callback=progress_callback
                )

                yt_video_id = upload_result.get("youtube_video_id")
                yt_channel_id = account.channel_id

                # Record upload in DB
                async with get_db_session() as session:
                    repo = ContentRepository(session)
                    await repo.record_successful_youtube_upload(
                        account_id=account_id,
                        lecture_id=lecture_id,
                        youtube_video_id=yt_video_id,
                        youtube_channel_id=yt_channel_id,
                        job_id=batch_id
                    )

                upload_result["youtube_account_id"] = account_id
                upload_result["youtube_channel_id"] = yt_channel_id

                # Clear checkpoint on success
                if batch_id:
                    cls.clear_checkpoint(str(batch_id), lecture_index)

                # DISK CLEANUP: Clean up local video file from server disk immediately after successful upload
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"[DISK_CLEANUP] Deleted local prepared video file from server: {file_path}")
                except Exception as rm_e:
                    logger.debug(f"[DISK_CLEANUP_NOTICE] Could not delete local video file: {rm_e}")

                logger.info(f"[YOUTUBE_UPLOAD_SUCCESS] Upload succeeded on account '{account_name}' -> Video ID: {yt_video_id}")
                return upload_result

            except (YouTubeUploadLimitExceededError, Exception) as exc:
                err_classification = cls.classify_error(getattr(exc, "status_code", 400), getattr(exc, "raw_response", str(exc)), exc)
                logger.warning(f"[YOUTUBE_UPLOAD_EXCEPTION] Account '{account_name}' failed with classification: {err_classification}. Error: {exc}")

                if err_classification == "CHANNEL_UPLOAD_LIMIT":
                    # Mark current account LIMIT_REACHED
                    async with get_db_session() as session:
                        repo = ContentRepository(session)
                        await repo.mark_youtube_account_status(
                            account_id=account_id,
                            status=YouTubeAccountStatus.LIMIT_REACHED.value,
                            last_error=f"uploadLimitExceeded: {exc}",
                            last_error_type="CHANNEL_UPLOAD_LIMIT",
                            cooldown_hours=24.0
                        )

                    # Save checkpoint with prepared video
                    if batch_id:
                        cls.save_checkpoint(
                            batch_id=str(batch_id),
                            lecture_id=lecture_id,
                            lecture_index=lecture_index,
                            title=title,
                            prepared_video_path=file_path,
                            thumbnail_path=thumbnail_path,
                            selected_account_id=account_id,
                            stage="WATERMARKED_READY_FOR_UPLOAD",
                            reason="uploadLimitExceeded",
                            duration=duration,
                            resolution=resolution,
                            last_error=str(exc)
                        )

                    # Add to tried list and rotate to next ACTIVE account
                    tried_account_ids.append(account_id)
                    logger.info(f"[YOUTUBE_FAILOVER_ROTATION] Account '{account_name}' reached daily limit. Rotating to next active account...")
                    continue

                elif err_classification == "AUTH_ERROR":
                    async with get_db_session() as session:
                        repo = ContentRepository(session)
                        await repo.mark_youtube_account_status(
                            account_id=account_id,
                            status=YouTubeAccountStatus.AUTH_ERROR.value,
                            last_error=str(exc),
                            last_error_type="AUTH_ERROR"
                        )
                    tried_account_ids.append(account_id)
                    continue

                elif err_classification == "TEMPORARY":
                    # Bounded exponential retry on current account
                    logger.info(f"[YOUTUBE_TEMPORARY_RETRY] Retrying temporary error on account '{account_name}'...")
                    raise exc

                else:
                    # PERMANENT error
                    raise exc

    @classmethod
    async def _get_account_access_token(cls, client_id: str, client_secret: str, refresh_token: str) -> Optional[str]:
        """Exchanges refresh token for an access token for a specific account."""
        if not client_id or not client_secret or not refresh_token:
            return None

        import requests
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
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
    async def _execute_resumable_upload(
        cls,
        file_path: str,
        title: str,
        description: Optional[str],
        privacy: str,
        thumbnail_path: Optional[str],
        token: str,
        progress_callback: Optional[Callable[[float, int, int], None]] = None
    ) -> Dict[str, Any]:
        """Performs resumable chunked upload to YouTube API."""
        import requests

        path_obj = Path(file_path)
        if not path_obj.exists() or path_obj.stat().st_size == 0:
            raise ValueError(f"Video file not found or empty: {file_path}")

        file_size = path_obj.stat().st_size

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(file_size)
        }

        body = {
            "snippet": {
                "title": title[:100],
                "description": description or f"Course Wallah Content - {title}",
                "categoryId": "27"  # Education
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
            err_class = cls.classify_error(resp_init.status_code, err_text)
            if err_class == "CHANNEL_UPLOAD_LIMIT":
                raise YouTubeUploadLimitExceededError(
                    message=f"YouTube uploadLimitExceeded (HTTP {resp_init.status_code}): {err_text}",
                    status_code=resp_init.status_code,
                    raw_response=err_text
                )
            elif err_class == "API_PROJECT_QUOTA":
                raise YouTubeApiQuotaExceededError(
                    message=f"YouTube API Quota Exceeded (HTTP {resp_init.status_code}): {err_text}",
                    status_code=resp_init.status_code,
                    raw_response=err_text
                )
            elif err_class == "AUTH_ERROR":
                raise YouTubeAccountAuthError(
                    message=f"YouTube Auth Error (HTTP {resp_init.status_code}): {err_text}",
                    status_code=resp_init.status_code,
                    raw_response=err_text
                )
            raise RuntimeError(f"Failed to initiate YouTube upload: HTTP {resp_init.status_code} - {err_text}")

        upload_url = resp_init.headers.get("Location")
        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload Location URL.")

        # Step 2: Chunked Upload
        chunk_size = 1024 * 1024 * 8  # 8 MB chunks
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

                    # Step 3: Optional Thumbnail Upload
                    if thumbnail_path and os.path.exists(thumbnail_path) and yt_id:
                        await YouTubeUploader._upload_thumbnail(yt_id, thumbnail_path, token)

                    return {
                        "youtube_video_id": yt_id,
                        "title": title,
                        "description": description,
                        "privacy": privacy,
                        "status": "UPLOADED",
                        "uploaded_at": datetime.utcnow().isoformat(),
                        "file_size": file_size
                    }

                elif resp_chunk.status_code != 308:
                    err_text = resp_chunk.text
                    err_class = cls.classify_error(resp_chunk.status_code, err_text)
                    if err_class == "CHANNEL_UPLOAD_LIMIT":
                        raise YouTubeUploadLimitExceededError(
                            message=f"YouTube uploadLimitExceeded (HTTP {resp_chunk.status_code}): {err_text}",
                            status_code=resp_chunk.status_code,
                            raw_response=err_text
                        )
                    raise RuntimeError(f"YouTube upload chunk failed: HTTP {resp_chunk.status_code} - {err_text}")

        raise RuntimeError("YouTube upload loop finished without receiving 200/201 response.")

    @classmethod
    async def get_diagnostics(cls) -> Dict[str, Any]:
        """
        Retrieves sanitized diagnostics for all configured YouTube accounts,
        including status, uploads today, estimated remaining limit, and active queues.
        """
        await cls.sync_primary_from_env()

        async with get_db_session() as session:
            repo = ContentRepository(session)
            await repo.reset_account_quotas_if_needed()

            accounts = await repo.get_all_youtube_accounts()
            accounts_data = []

            for acc in accounts:
                client_id_masked = "Not Configured"
                if acc.client_id:
                    cid = acc.client_id
                    client_id_masked = f"{cid[:8]}...{cid[-14:]}" if len(cid) > 22 else "Configured"

                uploads = acc.uploads_today or 0
                estimated_limit = DEFAULT_ESTIMATED_DAILY_LIMIT
                remaining = max(0, estimated_limit - uploads) if acc.status == YouTubeAccountStatus.ACTIVE.value else 0

                accounts_data.append({
                    "id": acc.id,
                    "name": acc.name,
                    "client_id_masked": client_id_masked,
                    "channel_id": acc.channel_id or "Not Detected",
                    "channel_title": acc.channel_title or acc.name,
                    "status": acc.status,
                    "priority": acc.priority,
                    "uploads_today": uploads,
                    "estimated_daily_limit": estimated_limit,
                    "estimated_remaining_today": remaining,
                    "last_upload_at": acc.last_upload_at.isoformat() if acc.last_upload_at else None,
                    "limit_detected_at": acc.limit_detected_at.isoformat() if acc.limit_detected_at else None,
                    "cooldown_until": acc.cooldown_until.isoformat() if acc.cooldown_until else None,
                    "last_error": acc.last_error,
                    "last_error_type": acc.last_error_type
                })

            # Checkpoints count
            ckpt_base = Path(DOWNLOADS_DIR) / "checkpoints"
            blocked_count = 0
            if ckpt_base.exists():
                for b in ckpt_base.iterdir():
                    if b.is_dir():
                        for l in b.iterdir():
                            if (l / "youtube_upload_checkpoint.json").exists() or (l / "checkpoint.json").exists():
                                blocked_count += 1

            return {
                "accounts": accounts_data,
                "total_accounts": len(accounts_data),
                "active_accounts": sum(1 for a in accounts_data if a["status"] == YouTubeAccountStatus.ACTIVE.value),
                "limit_reached_accounts": sum(1 for a in accounts_data if a["status"] == YouTubeAccountStatus.LIMIT_REACHED.value),
                "auth_error_accounts": sum(1 for a in accounts_data if a["status"] == YouTubeAccountStatus.AUTH_ERROR.value),
                "blocked_checkpoints_count": blocked_count,
                "timestamp": datetime.utcnow().isoformat()
            }

    @classmethod
    def generate_oauth_authorization_url(
        cls,
        client_id: str,
        redirect_uri: str = "http://localhost"
    ) -> str:
        """
        Generates official Google OAuth 2.0 consent URL with all required YouTube scopes.
        """
        import urllib.parse
        params = {
            "client_id": client_id.strip(),
            "redirect_uri": redirect_uri.strip(),
            "response_type": "code",
            "scope": "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube https://www.googleapis.com/auth/youtube.readonly",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true"
        }
        return f"https://accounts.google.com/o/oauth2/auth?{urllib.parse.urlencode(params)}"

    @classmethod
    async def exchange_oauth_code_for_tokens(
        cls,
        client_id: str,
        client_secret: str,
        code: str,
        redirect_uri: str = "http://localhost"
    ) -> Dict[str, Any]:
        """
        Exchanges authorization code for access_token and refresh_token from Google's token endpoint.
        """
        if not client_id or not client_secret or not code:
            return {"valid": False, "error": "client_id, client_secret, and authorization code are all required."}

        import httpx
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "code": code.strip(),
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri.strip()
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(token_url, data=payload)
                if resp.status_code != 200:
                    err_json = {}
                    try:
                        err_json = resp.json()
                    except Exception:
                        pass
                    err_msg = err_json.get("error_description") or err_json.get("error") or resp.text
                    return {"valid": False, "error": f"Google Token Exchange Failed (HTTP {resp.status_code}): {err_msg}"}

                data = resp.json()
                refresh_token = data.get("refresh_token")
                access_token = data.get("access_token")
                if not refresh_token:
                    return {
                        "valid": False,
                        "error": "Google did not return a refresh_token. Please ensure you approved all YouTube permissions and re-authenticate."
                    }

                return {
                    "valid": True,
                    "refresh_token": refresh_token,
                    "access_token": access_token
                }
        except httpx.TimeoutException:
            return {"valid": False, "error": "Request timed out while contacting Google OAuth token endpoint."}
        except Exception as e:
            return {"valid": False, "error": f"Exception exchanging authorization code: {str(e)}"}

    @classmethod
    async def validate_and_fetch_channel_info(
        cls,
        client_id: str,
        client_secret: str,
        refresh_token: str
    ) -> Dict[str, Any]:
        """
        Validates OAuth credentials against Google's token endpoint and fetches channel info from YouTube API.
        """
        if not client_id or not client_secret or not refresh_token:
            return {"valid": False, "error": "client_id, client_secret, and refresh_token are all required."}

        import requests
        token_url = "https://oauth2.googleapis.com/token"
        payload = {
            "client_id": client_id.strip(),
            "client_secret": client_secret.strip(),
            "refresh_token": refresh_token.strip(),
            "grant_type": "refresh_token"
        }

        try:
            resp = requests.post(token_url, data=payload, timeout=15)
            if resp.status_code != 200:
                err_data = {}
                try:
                    err_data = resp.json()
                except Exception:
                    pass
                err_msg = err_data.get("error_description") or err_data.get("error") or resp.text
                return {"valid": False, "error": f"OAuth token exchange failed (HTTP {resp.status_code}): {err_msg}"}

            token_json = resp.json()
            access_token = token_json.get("access_token")
            if not access_token:
                return {"valid": False, "error": "No access_token returned by Google OAuth."}

            # Query YouTube API for channel info
            ch_url = "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true"
            ch_resp = requests.get(ch_url, headers={"Authorization": f"Bearer {access_token}"}, timeout=15)

            channel_id = None
            channel_title = None
            custom_url = None
            subscriber_count = 0
            video_count = 0

            if ch_resp.status_code == 200:
                ch_data = ch_resp.json()
                items = ch_data.get("items", [])
                if items:
                    item = items[0]
                    channel_id = item.get("id")
                    snippet = item.get("snippet", {})
                    channel_title = snippet.get("title")
                    custom_url = snippet.get("customUrl")
                    stats = item.get("statistics", {})
                    subscriber_count = int(stats.get("subscriberCount", 0))
                    video_count = int(stats.get("videoCount", 0))

            return {
                "valid": True,
                "access_token": access_token,
                "channel_id": channel_id,
                "channel_title": channel_title,
                "custom_url": custom_url,
                "subscriber_count": subscriber_count,
                "video_count": video_count
            }

        except requests.Timeout:
            return {"valid": False, "error": "Request timed out while connecting to Google OAuth / YouTube API."}
        except Exception as e:
            return {"valid": False, "error": f"Exception connecting to Google API: {str(e)}"}

    @classmethod
    async def add_account_from_credentials(
        cls,
        name: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        priority: int = 1,
        auto_test: bool = True
    ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """
        Validates credentials with Google and saves the new YouTube account to the database.
        """
        clean_name = name.strip() if name else "Secondary YouTube Channel"
        clean_cid = client_id.strip()
        clean_secret = client_secret.strip()
        clean_rt = refresh_token.strip()

        ch_id = None
        ch_title = None

        if auto_test:
            res = await cls.validate_and_fetch_channel_info(clean_cid, clean_secret, clean_rt)
            if not res["valid"]:
                return False, None, res["error"]
            ch_id = res.get("channel_id")
            ch_title = res.get("channel_title") or clean_name
            if not clean_name or clean_name == "Secondary YouTube Channel":
                clean_name = ch_title

        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.create_or_update_youtube_account(
                name=clean_name,
                client_id=clean_cid,
                client_secret=clean_secret,
                refresh_token=clean_rt,
                channel_id=ch_id,
                channel_title=ch_title,
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=priority
            )
            acc_dict = {
                "id": acc.id,
                "name": acc.name,
                "channel_title": acc.channel_title,
                "channel_id": acc.channel_id,
                "priority": acc.priority,
                "status": acc.status,
                "uploads_today": acc.uploads_today or 0
            }
            return True, acc_dict, "YouTube account added and verified successfully!"

    @classmethod
    async def remove_account(cls, account_id: str) -> Tuple[bool, str]:
        """Deletes an account from the database."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.get_youtube_account_by_id(account_id)
            if not acc:
                return False, "Account not found."
            name = acc.name
            deleted = await repo.delete_youtube_account(account_id)
            if deleted:
                return True, f"Account '{name}' removed successfully."
            return False, "Failed to delete account."

    @classmethod
    async def test_and_refresh_account(cls, account_id: str) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        """Tests OAuth connection and updates channel info for a registered account."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.get_youtube_account_by_id(account_id)
            if not acc:
                return False, None, "Account not found in database."

            res = await cls.validate_and_fetch_channel_info(acc.client_id, acc.client_secret, acc.refresh_token)
            if not res["valid"]:
                await repo.mark_youtube_account_status(
                    account_id=account_id,
                    status=YouTubeAccountStatus.AUTH_ERROR.value,
                    last_error=res["error"],
                    last_error_type="AUTH_ERROR"
                )
                return False, None, res["error"]

            if res.get("channel_id"):
                acc.channel_id = res["channel_id"]
            if res.get("channel_title"):
                acc.channel_title = res["channel_title"]
            acc.status = YouTubeAccountStatus.ACTIVE.value
            acc.last_error = None
            acc.last_error_type = None
            acc.cooldown_until = None
            await session.flush()

            acc_dict = {
                "id": acc.id,
                "name": acc.name,
                "channel_title": acc.channel_title,
                "channel_id": acc.channel_id,
                "status": acc.status,
                "priority": acc.priority,
                "uploads_today": acc.uploads_today or 0
            }
            return True, acc_dict, f"Account '{acc.name}' verified! Channel: '{acc.channel_title}' (ID: {acc.channel_id})"

    @classmethod
    async def set_account_priority(cls, account_id: str, priority: int) -> Tuple[bool, str]:
        """Sets priority order for an account."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.get_youtube_account_by_id(account_id)
            if not acc:
                return False, "Account not found."
            acc.priority = priority
            await session.flush()
            return True, f"Priority for '{acc.name}' set to {priority}."

    @classmethod
    async def toggle_account_active(cls, account_id: str, activate: Optional[bool] = None) -> Tuple[bool, str, str]:
        """Toggles account status between ACTIVE and DISABLED."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.get_youtube_account_by_id(account_id)
            if not acc:
                return False, "Account not found.", "UNKNOWN"

            if activate is None:
                new_status = YouTubeAccountStatus.ACTIVE.value if acc.status != YouTubeAccountStatus.ACTIVE.value else "DISABLED"
            else:
                new_status = YouTubeAccountStatus.ACTIVE.value if activate else "DISABLED"

            acc.status = new_status
            if new_status == YouTubeAccountStatus.ACTIVE.value:
                acc.cooldown_until = None
                acc.last_error = None
                acc.last_error_type = None
            await session.flush()
            return True, f"Account '{acc.name}' is now {new_status}.", new_status

