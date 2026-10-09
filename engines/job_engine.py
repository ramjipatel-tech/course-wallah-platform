import os
import time
import shutil
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List, Tuple

from config.settings import (
    TEMP_DIR,
    DOWNLOADS_DIR,
    THUMBNAILS_DIR,
    MAX_RETRIES,
    RETRY_DELAY,
    B2_BUCKET,
    MAX_CONCURRENT_JOBS,
    YOUTUBE_ENABLED,
    WATERMARK_ENABLED
)
from db.connection import get_db_session
from db.repository import ContentRepository, slugify
from db.models import JobStatus, PublicationStatus
from parsers.indexer import NormalizedLecture, NormalizedFolder, NormalizedSubject, NormalizedBatchTree
from providers.downloader import MediaDownloader, VideoUnavailableError
from providers.adapters import sanitize_url_for_logging
from providers.pdf_unlocker import download_pdf_file, validate_and_process_pdf
from providers.router import MediaRouter, MediaType, parse_pdf_input
from engines.watermark import WatermarkEngine
from engines.video_processor import VideoProcessor
from engines.youtube_uploader import YouTubeUploader, YouTubeUploadLimitExceededError, YouTubeApiQuotaExceededError
from engines.youtube_account_manager import YouTubeAccountManager
from engines.b2_storage import B2StorageManager
from storage.base import (
    StorageReplicationError,
    StorageReplicationProcessingError,
    StorageReplicationFailedError,
)
from storage.manager import MultiStorageManager
from bot.progress_ui import TelegramProgressUI, TelegramMessageThrottler, ProgressUICards


logger = logging.getLogger(__name__)


class BatchJobController:
    """
    Manages the lifecycle, pause/resume/cancel events, checkpointing,
    and progress reporting for an active batch ingestion job.
    """
    def __init__(
        self,
        bot_id: str,
        job_id: str,
        batch_id: str,
        batch_name: str,
        user_id: int,
        total_lectures: int,
        status_message=None
    ):
        self.bot_id = bot_id
        self.job_id = job_id
        self.batch_id = batch_id
        self.batch_name = batch_name
        self.user_id = user_id
        self.total_lectures = total_lectures
        self.status_message = status_message
        self.throttler = TelegramMessageThrottler(min_interval=1.6)

        self.is_paused = False
        self.is_cancelled = False
        self._pause_event = asyncio.Event()
        self._pause_event.set() # Set = running, Clear = paused

        self.completed_count = 0
        self.failed_count = 0
        self.skipped_count = 0
        self.failed_items: List[Dict[str, Any]] = []
        self.start_time_str = time.strftime("%I:%M %p", time.localtime())
        self.end_time_str = ""
        self.spinner_index = 0

    @property
    def pause_event(self) -> asyncio.Event:
        return self._pause_event

    def pause(self):
        self.is_paused = True
        self._pause_event.clear()
        logger.info(f"[JOB_PAUSED] bot_id={self.bot_id} job_id={self.job_id} batch_id={self.batch_id}")

    def resume(self):
        self.is_paused = False
        self._pause_event.set()
        logger.info(f"[JOB_RESUMED] bot_id={self.bot_id} job_id={self.job_id} batch_id={self.batch_id}")

    def cancel(self):
        self.is_cancelled = True
        self._pause_event.set() # Release wait so loop can exit cleanly
        logger.info(f"[JOB_CANCELLED] bot_id={self.bot_id} job_id={self.job_id} batch_id={self.batch_id}")

    async def wait_if_paused(self):
        if self.is_paused:
            await self._pause_event.wait()


class ContentProcessingEngine:
    """
    Production-Grade Batch Ingestion Engine for Course Wallah Platform.
    Executes sequential & concurrent processing, moving watermarks, YouTube uploads,
    B2 PDF processing, duplicate skips, and live Telegram UI animations.
    """

    _active_batch_controllers: Dict[str, BatchJobController] = {}
    _concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    def __init__(self, bot_id: str = "bot_1"):
        self.bot_id = bot_id

    @classmethod
    def register_controller(cls, controller: BatchJobController):
        cls._active_batch_controllers[controller.job_id] = controller

    @classmethod
    def get_controller(cls, job_id: str) -> Optional[BatchJobController]:
        return cls._active_batch_controllers.get(job_id)

    @classmethod
    def remove_controller(cls, job_id: str):
        if job_id in cls._active_batch_controllers:
            del cls._active_batch_controllers[job_id]

    async def run_full_batch(
        self,
        controller: BatchJobController,
        session_data: Dict[str, Any],
        start_index: int = 1,
        retry_failed_only: bool = False
    ) -> Dict[str, Any]:
        """
        Runs the end-to-end batch ingestion loop with live progress updates,
        duplicate checks, pause/resume handling, and temporary scratch cleanup.
        """
        tree: NormalizedBatchTree = session_data["tree"]
        app_name = session_data.get("app_name", "Course Wallah")
        batch_name = session_data.get("batch_name", tree.batch_name)
        quality_pref = session_data.get("quality_pref", "AUTO / HIGHEST")
        watermark_text = session_data.get("watermark_text", "COURSE WALLAH")

        async with get_db_session() as db_sess:
            repo = ContentRepository(db_sess)
            app = await repo.get_or_create_app(app_name)
            batch, _ = await repo.get_or_create_batch(
                app_id=app.id,
                name=batch_name,
                category=session_data.get("category"),
                branch=session_data.get("branch"),
                semester=session_data.get("semester"),
                academic_year=session_data.get("academic_year"),
                thumbnail_url=session_data.get("thumbnail_url"),
                quality_pref=quality_pref
            )
            app_id = app.id
            app_slug = app.slug
            batch_id = batch.id
            batch_slug = batch.slug

        logger.info(f"[JOB_CREATED] bot_id={self.bot_id} job_id={controller.job_id} batch_id={batch_id} batch_name='{batch_name}' total={tree.total_lectures}")

        # Flatten lectures
        flat_lecture_items: List[Tuple[NormalizedSubject, NormalizedFolder, NormalizedLecture]] = []
        for s in tree.subjects:
            for f in s.folders:
                for l in f.lectures:
                    flat_lecture_items.append((s, f, l))

        for subj, folder, item in flat_lecture_items:
            # Check for cancellation
            if controller.is_cancelled:
                logger.info(f"[JOB_CANCELLED] Ingestion loop exiting for job_id={controller.job_id}")
                break

            # Wait if paused
            await controller.wait_if_paused()

            if controller.is_cancelled:
                break

            if item.index < start_index and not retry_failed_only:
                controller.skipped_count += 1
                continue

            # Check if lecture is already PUBLISHED in DB with media
            async with get_db_session() as db_sess:
                repo = ContentRepository(db_sess)
                existing_lec = await repo.get_lecture_by_index(batch_id, item.index)
                if existing_lec and existing_lec.publication_status == PublicationStatus.PUBLISHED:
                    # Verified published: skip re-download
                    logger.info(f"[LECTURE_SKIPPED] #{item.index} '{item.title}' is already published.")
                    controller.skipped_count += 1
                    controller.completed_count += 1
                    continue

            # Process single lecture
            try:
                await self.process_lecture_item(
                    app_id=app_id,
                    app_slug=app_slug,
                    batch_id=batch_id,
                    batch_slug=batch_slug,
                    subject_name=subj.name,
                    folder_name=folder.name,
                    unit_number=folder.unit_number,
                    item=item,
                    user_id=controller.user_id,
                    quality_pref=quality_pref,
                    watermark_text=watermark_text,
                    controller=controller
                )
                controller.completed_count += 1
            except asyncio.CancelledError:
                logger.info(f"[JOB_CANCELLED] Cancelled during lecture #{item.index}")
                break
            except YouTubeUploadLimitExceededError as limit_e:
                controller.pause()
                controller.failed_count += 1
                controller.failed_items.append({
                    "index": item.index,
                    "title": item.title,
                    "error": "YouTube uploadLimitExceeded: Daily upload limit reached. Prepared artifact preserved in durable checkpoint.",
                    "limit_exceeded": True
                })
                logger.warning(f"[BATCH_PAUSED_YOUTUBE_LIMIT] Batch '{batch_name}' paused: {limit_e}")

                try:
                    async with get_db_session() as db_sess:
                        repo = ContentRepository(db_sess)
                        db_lec = await repo.get_lecture_by_index(batch_id, item.index)
                        if db_lec:
                            db_lec.publication_status = PublicationStatus.PROCESSING
                except Exception as db_err:
                    logger.debug(f"[DB_STATUS_UPDATE_NOTICE] {db_err}")

                limit_msg = (
                    f"⚠️ <b>YOUTUBE UPLOAD LIMIT REACHED</b>\n\n"
                    f"<b>Batch:</b> {batch_name}\n"
                    f"<b>Paused at:</b> #{item.index} - {item.title}\n\n"
                    f"All active YouTube account limits have been reached for today.\n"
                    f"Download and watermark processing are complete, but upload is paused.\n\n"
                    f"💾 <i>Prepared video artifacts have been safely checkpointed on disk. Add another active YouTube account or click <b>Resume</b> when YouTube quotas reset.</i>"
                )
                try:
                    from bot.batch_wizard import BatchWizardManager
                    markup = BatchWizardManager.build_paused_batch_markup(controller.job_id)
                    if controller.status_message:
                        await controller.throttler.edit(controller.status_message, limit_msg, reply_markup=markup, force=True)
                except Exception as ui_e:
                    logger.debug(f"[UI_LIMIT_NOTICE] {ui_e}")

                break

            except StorageReplicationProcessingError as proc_e:
                controller.pause()
                controller.failed_count += 1
                controller.failed_items.append({
                    "index": item.index,
                    "title": item.title,
                    "error": f"Storage Processing: {proc_e}. Remote asset transcoding in progress; prepared artifact preserved in durable checkpoint.",
                    "storage_processing": True
                })
                logger.warning(f"[BATCH_PAUSED_STORAGE_PROCESSING] Batch '{batch_name}' paused at #{item.index}: {proc_e}")

                try:
                    async with get_db_session() as db_sess:
                        repo = ContentRepository(db_sess)
                        db_lec = await repo.get_lecture_by_index(batch_id, item.index)
                        if db_lec:
                            db_lec.publication_status = PublicationStatus.PROCESSING
                except Exception as db_err:
                    logger.debug(f"[DB_STATUS_UPDATE_NOTICE] {db_err}")

                proc_msg = (
                    f"⏳ <b>STORAGE REPLICATION IN PROGRESS</b>\n\n"
                    f"<b>Batch:</b> {batch_name}\n"
                    f"<b>Paused at:</b> #{item.index} - {item.title}\n\n"
                    f"Required storage provider ({proc_e.provider}) is transcoding asynchronously on remote servers.\n"
                    f"Upload is complete, and status verification will resume without re-uploading.\n\n"
                    f"💾 <i>Prepared video artifacts and remote IDs have been safely checkpointed. Click <b>Resume</b> when remote processing completes.</i>"
                )
                try:
                    from bot.batch_wizard import BatchWizardManager
                    markup = BatchWizardManager.build_paused_batch_markup(controller.job_id)
                    if controller.status_message:
                        await controller.throttler.edit(controller.status_message, proc_msg, reply_markup=markup, force=True)
                except Exception as ui_e:
                    logger.debug(f"[UI_STORAGE_PROC_NOTICE] {ui_e}")

                break

            except Exception as e:
                controller.failed_count += 1
                controller.failed_items.append({
                    "index": item.index,
                    "title": item.title,
                    "error": str(e)
                })
                logger.error(f"[LECTURE_FAILED] bot_id={self.bot_id} job_id={controller.job_id} lecture_index=#{item.index} error={e}")
                try:
                    async with get_db_session() as db_sess:
                        repo = ContentRepository(db_sess)
                        await repo.set_lecture_failed(batch_id, item.index, str(e))
                except Exception as db_e:
                    logger.debug(f"[DB_FAILURE_RECORD_NOTICE] Could not mark lecture #{item.index} as failed in DB: {db_e}")

        controller.end_time_str = time.strftime("%I:%M %p", time.localtime())
        has_limit_exceeded = any(f.get("limit_exceeded") for f in controller.failed_items)
        logger.info(f"[JOB_COMPLETED] bot_id={self.bot_id} job_id={controller.job_id} success={controller.completed_count} failed={controller.failed_count} skipped={controller.skipped_count} limit_paused={has_limit_exceeded}")

        return {
            "batch_name": batch_name,
            "total": tree.total_lectures,
            "success": controller.completed_count,
            "failed": controller.failed_count,
            "skipped": controller.skipped_count,
            "pending": max(0, tree.total_lectures - controller.completed_count - controller.failed_count - controller.skipped_count),
            "start_time": controller.start_time_str,
            "end_time": controller.end_time_str,
            "failed_items": controller.failed_items,
            "youtube_limit_reached": has_limit_exceeded
        }

    async def process_lecture_item(
        self,
        app_id: str,
        app_slug: str,
        batch_id: str,
        batch_slug: str,
        subject_name: str,
        folder_name: str,
        unit_number: Optional[str],
        item: NormalizedLecture,
        user_id: int,
        quality_pref: str = "AUTO / HIGHEST",
        watermark_text: str = "COURSE WALLAH",
        controller: Optional[BatchJobController] = None
    ) -> Dict[str, Any]:
        """
        Executes end-to-end pipeline for a single lecture:
        1. Download Video -> 2. Watermark -> 3. Thumbnail -> 4. YouTube Upload -> 5. PDF Processing -> 6. B2 Upload -> 7. DB Sync -> 8. Playlist -> 9. Publish.
        """
        lecture_job_id = f"lec_{batch_id[:8]}_{item.index:04d}_{int(time.time())}"
        work_dir = Path(TEMP_DIR) / f"work_{lecture_job_id}"
        work_dir.mkdir(parents=True, exist_ok=True)

        downloaded_video_path = None
        watermarked_video_path = None
        thumb_path = None
        pdf_temp_path = None
        pdf_clean_path = None
        storage_replication_success = True if not item.video_url else False

        phase_states = {
            "download": "⏳",
            "watermark": "⏳",
            "thumbnail": "⏳",
            "youtube": "⏳",
            "pdf": "⏳" if item.pdf_url else "N/A",
            "b2": "⏳" if item.pdf_url else "N/A",
            "database": "⏳",
            "playlist": "⏳",
            "publish": "⏳"
        }

        async def _update_telegram_ui(step_text: str, dl_pct=0.0, wm_pct=0.0, yt_pct=0.0, p_pct=0.0, b_pct=0.0, force=False):
            if not controller or not controller.status_message:
                return
            try:
                controller.spinner_index += 1
                card_text = TelegramProgressUI.render_live_card(
                    batch_name=controller.batch_name,
                    folder_name=folder_name,
                    lecture_index=item.index,
                    lecture_title=item.title,
                    total_lectures=controller.total_lectures,
                    completed_count=controller.completed_count,
                    failed_count=controller.failed_count,
                    skipped_count=controller.skipped_count,
                    current_step=step_text,
                    download_pct=dl_pct,
                    watermark_pct=wm_pct,
                    youtube_pct=yt_pct,
                    pdf_pct=p_pct,
                    b2_pct=b_pct,
                    phase_states=phase_states,
                    spinner_idx=controller.spinner_index
                )
                markup = None
                try:
                    from bot.batch_wizard import BatchWizardManager
                    markup = BatchWizardManager.build_running_batch_markup(controller.job_id)
                except Exception as ui_e:
                    logger.debug(f"[UI_MARKUP_NOTICE] Running batch markup fallback: {ui_e}")

                await controller.throttler.edit(controller.status_message, card_text, reply_markup=markup, force=force)
            except Exception as exc:
                logger.exception("Non-fatal Telegram progress error; continuing pipeline: %s", exc)

        try:
            logger.info(f"[LECTURE_STARTED] lecture_id=#{item.index} title='{item.title}' provider={item.provider}")
            
            # Setup DB entries
            async with get_db_session() as session:
                repo = ContentRepository(session)
                subj = await repo.get_or_create_subject(batch_id, subject_name)
                folder = await repo.get_or_create_folder(subj.id, folder_name, unit_number=unit_number)
                lecture = await repo.create_or_update_lecture(
                    folder_id=folder.id,
                    subject_id=subj.id,
                    batch_id=batch_id,
                    lecture_index=item.index,
                    title=item.title,
                    source_url=item.video_url,
                    source_pdf_url=item.pdf_url,
                    provider=item.provider,
                    raw_reference=item.raw_reference,
                    has_video=bool(item.video_url),
                    has_pdf=bool(item.pdf_url)
                )

            # ==========================================
            # CHECKPOINT DISCOVERY & RESUME
            # ==========================================
            youtube_video_id = None
            youtube_channel_id = None
            youtube_account_id = None
            youtube_url = None
            upload_completed_at = None
            video_duration = 0.0
            video_resolution = "1080p"
            video_size = 0

            ckpt_data = YouTubeAccountManager.load_checkpoint(str(batch_id), item.index)
            has_valid_checkpoint = False

            if ckpt_data and ckpt_data.get("prepared_video_path") and os.path.exists(ckpt_data["prepared_video_path"]):
                watermarked_video_path = ckpt_data["prepared_video_path"]
                thumb_path = ckpt_data.get("thumbnail_path")
                video_duration = float(ckpt_data.get("duration", 0.0))
                video_resolution = str(ckpt_data.get("resolution", "1080p"))
                video_size = int(ckpt_data.get("file_size", os.path.getsize(watermarked_video_path)))
                has_valid_checkpoint = True
                logger.info(f"[CHECKPOINT_RESUMED] lecture_index=#{item.index} Reusing prepared watermarked artifact: {watermarked_video_path}")

            # Check DB if lecture was already processed and uploaded in a previous run
            is_already_uploaded = False
            async with get_db_session() as chk_s:
                chk_repo = ContentRepository(chk_s)
                existing_lec = await chk_repo.get_lecture_by_index(batch_id, item.index)
                if existing_lec and existing_lec.video and existing_lec.video.youtube_video_id:
                    youtube_video_id = existing_lec.video.youtube_video_id
                    youtube_channel_id = existing_lec.video.youtube_channel_id
                    youtube_account_id = existing_lec.video.youtube_account_id
                    youtube_url = existing_lec.video.youtube_url
                    is_already_uploaded = True
                    phase_states["download"] = "✅"
                    phase_states["watermark"] = "✅"
                    phase_states["thumbnail"] = "✅"
                    phase_states["youtube"] = "✅"
                    logger.info(f"[ALREADY_PROCESSED] lecture_index=#{item.index} title='{item.title}' ALREADY uploaded to YouTube -> ID: {youtube_video_id}. Auto-skipping download & upload!")
                    await _update_telegram_ui(f"Lecture #{item.index} already uploaded ({youtube_video_id}) - auto-skipped.", dl_pct=100.0, yt_pct=100.0)

            if is_already_uploaded:
                pass # Already uploaded, will proceed to check PDF/DB
            elif has_valid_checkpoint:
                phase_states["download"] = "✅"
                phase_states["watermark"] = "✅"
                phase_states["thumbnail"] = "✅"
                await _update_telegram_ui("Reusing prepared video artifact (checkpoint)...", dl_pct=100.0, wm_pct=100.0)

            elif item.video_url:
                # ==========================================
                # PHASE 1: DOWNLOAD VIDEO
                # ==========================================
                phase_states["download"] = "🔄"
                await _update_telegram_ui("Downloading source video...", dl_pct=15.0)
                logger.info(f"[DOWNLOAD_STARTED] lecture_index=#{item.index} url={sanitize_url_for_logging(item.video_url)}")


                last_dl_err = None
                for attempt in range(1, MAX_RETRIES + 1):
                    try:
                        downloaded_video_path, dl_meta = await MediaDownloader.download_video_stream_with_meta(
                            url=item.video_url,
                            title=f"{item.index:03d}_{item.title}",
                            quality=quality_pref
                        )
                        if dl_meta:
                            if dl_meta.get("pdf_url") and not item.pdf_url:
                                item.pdf_url = dl_meta["pdf_url"]
                                logger.info(f"[MEDIA_ROUTING] Companion PDF resolved in single API call for lecture #{item.index}: {sanitize_url_for_logging(item.pdf_url)}")
                            
                            # Attach high-res provider thumbnail to lecture and batch
                            thumb_url = dl_meta.get("thumbnail")
                            if thumb_url:
                                try:
                                    async with get_db_session() as db_s:
                                        repo_s = ContentRepository(db_s)
                                        lec_rec = await repo_s.get_lecture_by_index(batch_id, item.index)
                                        if lec_rec and not lec_rec.thumbnail_url:
                                            lec_rec.thumbnail_url = thumb_url
                                        b_rec = await repo_s.get_batch_by_id(batch_id)
                                        if b_rec and not b_rec.thumbnail_url:
                                            b_rec.thumbnail_url = thumb_url
                                            logger.info(f"[BATCH_THUMBNAIL_ATTACHED] batch_id={batch_id} thumb={thumb_url}")
                                except Exception as th_err:
                                    logger.debug(f"[THUMBNAIL_PROPAGATE_NOTICE] {th_err}")
                        break
                    except VideoUnavailableError as vu_e:
                        # Legitimate deterministic provider response: Video=NO | PDF=YES
                        logger.info(f"[VIDEO_UNAVAILABLE] lecture_index=#{item.index} {vu_e}")
                        if vu_e.pdf_url:
                            item.pdf_url = vu_e.pdf_url
                        item.video_url = None
                        downloaded_video_path = None
                        storage_replication_success = True
                        
                        # Check metadata from error for thumbnail
                        th_url = vu_e.metadata.get("thumbnail") if hasattr(vu_e, "metadata") and vu_e.metadata else None
                        
                        # Update DB record to reflect PDF-only
                        async with get_db_session() as db_s:
                            db_repo = ContentRepository(db_s)
                            await db_repo.create_or_update_lecture(
                                folder_id=folder.id,
                                subject_id=subj.id,
                                batch_id=batch_id,
                                lecture_index=item.index,
                                title=item.title,
                                source_url=None,
                                source_pdf_url=item.pdf_url,
                                provider=item.provider,
                                raw_reference=item.raw_reference,
                                has_video=False,
                                has_pdf=bool(item.pdf_url),
                                thumbnail_url=th_url
                            )
                            if th_url:
                                b_rec = await db_repo.get_batch_by_id(batch_id)
                                if b_rec and not b_rec.thumbnail_url:
                                    b_rec.thumbnail_url = th_url
                        phase_states["download"] = "N/A"
                        phase_states["watermark"] = "N/A"
                        phase_states["thumbnail"] = "N/A"
                        phase_states["youtube"] = "N/A"
                        break
                    except Exception as dl_e:
                        last_dl_err = dl_e
                        if attempt < MAX_RETRIES:
                            logger.warning(f"[DOWNLOAD_RETRY] lecture_index=#{item.index} attempt={attempt}/{MAX_RETRIES} err={dl_e}. Retrying in {RETRY_DELAY}s...")
                            await _update_telegram_ui(f"Download retry {attempt}/{MAX_RETRIES}...", dl_pct=5.0)
                            await asyncio.sleep(RETRY_DELAY)
                        else:
                            raise last_dl_err

                if downloaded_video_path:
                    phase_states["download"] = "✅"
                    await _update_telegram_ui("Video Downloaded", dl_pct=100.0)
                    logger.info(f"[DOWNLOAD_COMPLETED] lecture_index=#{item.index} path={downloaded_video_path}")

                    if controller and controller.is_cancelled:
                        raise asyncio.CancelledError()
                    if controller:
                        await controller.wait_if_paused()

                    # Inspect duration and resolution
                    probe_info = await VideoProcessor.probe_video(downloaded_video_path)
                    video_duration = probe_info.get("duration", 0.0)
                    video_resolution = probe_info.get("resolution", "1080p")
                    video_size = probe_info.get("size", os.path.getsize(downloaded_video_path))

                    # Large video check: split if exceeds upload threshold
                    split_parts = await VideoProcessor.split_if_large(downloaded_video_path)
                    primary_video = split_parts[0]

                    # ==========================================
                    # PHASE 2: ANIMATED MOVING WATERMARK
                    # ==========================================
                    if WATERMARK_ENABLED:
                        phase_states["watermark"] = "🔄"
                        await _update_telegram_ui("Applying high-speed moving watermark...", wm_pct=35.0)
                        logger.info(f"[WATERMARK_STARTED] lecture_index=#{item.index} mode=continuous_drift")

                        watermarked_video_path = str(work_dir / f"wm_{Path(primary_video).name}")
                        await WatermarkEngine.apply_watermark(
                            input_video=primary_video,
                            output_video=watermarked_video_path,
                            watermark_text=watermark_text,
                            animation_mode="continuous_drift"
                        )
                        phase_states["watermark"] = "✅"
                        await _update_telegram_ui("Watermark Applied", wm_pct=100.0)
                        logger.info(f"[WATERMARK_COMPLETED] lecture_index=#{item.index} output={watermarked_video_path}")
                    else:
                        watermarked_video_path = primary_video
                        phase_states["watermark"] = "⏭️"
                        logger.info(f"[WATERMARK_BYPASSED] Watermark is disabled (WATERMARK_ENABLED=false). Skipping re-encoding.")

                    # ==========================================
                    # PHASE 3: THUMBNAIL EXTRACTION
                    # ==========================================
                    phase_states["thumbnail"] = "🔄"
                    await _update_telegram_ui("Generating thumbnail frame...", wm_pct=100.0)
                    thumb_target = str(work_dir / f"thumb_{item.index}.jpg")
                    extracted_thumb = await VideoProcessor.extract_thumbnail(watermarked_video_path, thumb_target)
                    if extracted_thumb:
                        thumb_path = extracted_thumb
                        phase_states["thumbnail"] = "✅"
                        logger.info(f"[THUMBNAIL_CREATED] lecture_index=#{item.index} thumb={thumb_path}")
                    else:
                        phase_states["thumbnail"] = "✅"

                    if controller and controller.is_cancelled:
                        raise asyncio.CancelledError()
                    if controller:
                        await controller.wait_if_paused()

            # ==========================================
            # PHASE 4: YOUTUBE RESUMABLE UPLOAD (OPTIONAL)
            # ==========================================
            youtube_video_id = None
            youtube_channel_id = None
            youtube_account_id = None
            youtube_url = None
            upload_completed_at = None

            if YOUTUBE_ENABLED and watermarked_video_path and os.path.exists(watermarked_video_path):
                phase_states["youtube"] = "🔄"
                await _update_telegram_ui("Uploading to YouTube (Multi-Account Manager)...", yt_pct=15.0)
                logger.info(f"[YOUTUBE_UPLOAD_STARTED] lecture_index=#{item.index} title='{item.title}'")

                def _yt_progress_cb(pct, up, tot):
                    asyncio.create_task(_update_telegram_ui("Uploading to YouTube...", yt_pct=pct))

                try:
                    yt_res = await YouTubeAccountManager.upload_with_multi_account_failover(
                        file_path=watermarked_video_path,
                        title=f"{item.title} | {subject_name}",
                        description=f"Course Wallah Platform: {item.title}\nSubject: {subject_name}\nUnit: {folder_name}",
                        privacy="unlisted",
                        thumbnail_path=thumb_path,
                        batch_id=str(batch_id),
                        lecture_id=lecture.id if 'lecture' in locals() else None,
                        lecture_index=item.index,
                        duration=video_duration,
                        resolution=video_resolution,
                        progress_callback=_yt_progress_cb
                    )
                except YouTubeUploadLimitExceededError as limit_exc:
                    logger.warning(f"[CHECKPOINT_SAVED] lecture_index=#{item.index} Saving prepared artifact before pausing.")
                    YouTubeAccountManager.save_checkpoint(
                        batch_id=str(batch_id),
                        lecture_index=item.index,
                        prepared_video_path=watermarked_video_path,
                        thumbnail_path=thumb_path,
                        duration=video_duration,
                        resolution=video_resolution,
                        file_size=video_size,
                        reason="uploadLimitExceeded"
                    )
                    raise limit_exc

                youtube_video_id = yt_res.get("youtube_video_id")
                youtube_channel_id = yt_res.get("youtube_channel_id")
                youtube_account_id = yt_res.get("youtube_account_id")
                youtube_url = yt_res.get("youtube_url")
                upload_completed_at = datetime.utcnow()

                # Clean up checkpoint since upload succeeded
                YouTubeAccountManager.clear_checkpoint(str(batch_id), item.index)

                phase_states["youtube"] = "✅"
                await _update_telegram_ui("YouTube Uploaded", yt_pct=100.0)
                logger.info(f"[YOUTUBE_UPLOAD_COMPLETED] lecture_index=#{item.index} youtube_id={youtube_video_id} account_id={youtube_account_id}")

                # YouTube backend processing status verification if real YouTube ID
                if youtube_video_id and not youtube_video_id.startswith("cw_"):
                    try:
                        yt_status = await YouTubeUploader.check_video_status(youtube_video_id)
                        logger.info(
                            f"[YOUTUBE_PROCESSING_STATUS] lecture_index=#{item.index} "
                            f"upload_status={yt_status.get('upload_status')} "
                            f"processing_status={yt_status.get('processing_status')} "
                            f"is_ready={yt_status.get('is_ready')}"
                        )
                    except Exception as yt_check_err:
                        logger.debug(f"[YOUTUBE_STATUS_CHECK_NOTICE] {yt_check_err}")
            else:
                phase_states["youtube"] = "⏭️"
                logger.info(f"[YOUTUBE_SKIPPED] YouTube upload disabled (YOUTUBE_ENABLED=false). Proceeding directly to Multi-Storage replication.")

                # ==========================================
                # PHASE 4.5: MULTI-STORAGE VIDEO REPLICATION
                # Sequential 4 Providers: VCDN -> Media.cm -> AnonMP4 -> Vevocloud
                # ==========================================
                storage_replication_success = True
                video_db_id = None
                async with get_db_session() as v_sess:
                    v_repo = ContentRepository(v_sess)
                    lec_rec = await v_repo.get_lecture_by_index(batch_id, item.index)
                    if lec_rec:
                        vid_rec = await v_repo.attach_video_to_lecture(
                            lecture_id=lec_rec.id,
                            youtube_video_id=youtube_video_id or f"cw_temp_{item.index}",
                            duration=video_duration,
                            resolution=video_resolution,
                            file_size=video_size,
                            title=item.title,
                            youtube_channel_id=youtube_channel_id,
                            youtube_account_id=youtube_account_id,
                            youtube_url=youtube_url,
                            upload_completed_at=upload_completed_at or datetime.utcnow(),
                        )
                        video_db_id = vid_rec.id

                if video_db_id:
                    logger.info(f"[STORAGE_REPLICATION_START] lecture_index=#{item.index} video_id={video_db_id}")

                    async def _storage_ui_callback(payload: Dict[str, Any]):
                        if controller and controller.status_message:
                            try:
                                card_text = ProgressUICards.render_storage_replication_card(payload)
                                markup = None
                                try:
                                    from bot.batch_wizard import BatchWizardManager
                                    markup = BatchWizardManager.build_running_batch_markup(controller.job_id)
                                except Exception:
                                    pass
                                await controller.throttler.edit(
                                    controller.status_message,
                                    card_text,
                                    reply_markup=markup,
                                    force=payload.get("force", False)
                                )
                            except Exception as ui_exc:
                                logger.debug(f"[STORAGE_UI_NOTICE] {ui_exc}")

                    storage_manager = MultiStorageManager()
                    storage_res = await storage_manager.replicate_video(
                        video_id=video_db_id,
                        video_file_path=watermarked_video_path,
                        title=item.title,
                        metadata={
                            "subject": subject_name,
                            "folder": folder_name,
                            "lecture_index": item.index,
                            "batch_id": str(batch_id),
                        },
                        progress_ui_callback=_storage_ui_callback,
                    )
                    storage_replication_success = storage_res.get("success", False)
                    logger.info(
                        f"[STORAGE_REPLICATION_END] lecture_index=#{item.index} "
                        f"ready={storage_res.get('ready_count')}/{storage_res.get('total_enabled')} "
                        f"success={storage_replication_success}"
                    )
                    if controller and controller.status_message:
                        try:
                            if storage_replication_success:
                                card_text = ProgressUICards.render_storage_completed_card(storage_res)
                            else:
                                card_text = ProgressUICards.render_storage_incomplete_card(storage_res)
                            await controller.throttler.edit(controller.status_message, card_text, force=True)
                        except Exception as end_ui_exc:
                            logger.debug(f"[STORAGE_FINAL_UI_NOTICE] {end_ui_exc}")

                    if not storage_replication_success:
                        processing_required = storage_res.get("processing_required", [])
                        failed_required = storage_res.get("failed_required", [])

                        # Save durable checkpoint to preserve prepared watermarked video
                        YouTubeAccountManager.save_checkpoint(
                            batch_id=str(batch_id),
                            lecture_index=item.index,
                            prepared_video_path=watermarked_video_path,
                            thumbnail_path=thumb_path,
                            duration=video_duration,
                            resolution=video_resolution,
                            file_size=video_size,
                            reason="storageReplicationProcessing" if processing_required else "storageReplicationFailed",
                            stage="STORAGE_REPLICATION_PROCESSING" if processing_required else "STORAGE_REPLICATION_FAILED"
                        )

                        if processing_required:
                            proc_names = ", ".join(processing_required)
                            raise StorageReplicationProcessingError(
                                f"Required storage provider(s) still processing remotely: {proc_names}",
                                provider=proc_names
                            )
                        else:
                            fail_names = ", ".join(failed_required) if failed_required else "unknown"
                            raise StorageReplicationFailedError(
                                f"Required storage provider(s) failed replication: {fail_names}",
                                failed_providers=failed_required
                            )

            # ==========================================
            # PHASE 5 & 6: PDF PIPELINE & B2 UPLOAD
            # ==========================================
            b2_object_key = None
            pdf_page_count = 0
            pdf_size = 0

            if item.pdf_url:
                phase_states["pdf"] = "🔄"
                phase_states["b2"] = "⏳"
                await _update_telegram_ui("Downloading & branding PDF notes...", p_pct=30.0)
                logger.info(f"[PDF_STARTED] lecture_index=#{item.index} pdf_url={sanitize_url_for_logging(item.pdf_url)}")

                pdf_input = parse_pdf_input(item.pdf_url)
                raw_pdf_url = pdf_input["url"]
                pdf_pwd = pdf_input["password"]

                pdf_temp_path = work_dir / f"raw_{item.index}.pdf"
                pdf_clean_path = work_dir / f"clean_{item.index}.pdf"

                last_pdf_dl_err = None
                for attempt in range(1, MAX_RETRIES + 1):
                    ok, err = download_pdf_file(raw_pdf_url, pdf_temp_path)
                    if ok:
                        break
                    last_pdf_dl_err = err
                    if attempt < MAX_RETRIES:
                        logger.warning(f"[PDF_RETRY] lecture_index=#{item.index} attempt={attempt}/{MAX_RETRIES} err={err}. Retrying in {RETRY_DELAY}s...")
                        await asyncio.sleep(RETRY_DELAY)

                if not ok:
                    if youtube_video_id or item.video_url:
                        logger.warning(f"[PDF_SKIPPED] Companion PDF download failed ({last_pdf_dl_err}), but video is uploaded. Proceeding with video-only.")
                        phase_states["pdf"] = "N/A"
                        phase_states["b2"] = "N/A"
                    else:
                        raise RuntimeError(f"PDF download failed: {last_pdf_dl_err}")
                else:
                    v_ok, p_count, v_err = validate_and_process_pdf(
                        input_pdf=pdf_temp_path,
                        output_pdf=pdf_clean_path,
                        password=pdf_pwd,
                        watermark_text=watermark_text
                    )
                    if not v_ok:
                        if youtube_video_id or item.video_url:
                            logger.warning(f"[PDF_SKIPPED] Companion PDF processing failed ({v_err}), but video is uploaded. Proceeding with video-only.")
                            phase_states["pdf"] = "N/A"
                            phase_states["b2"] = "N/A"
                        else:
                            raise RuntimeError(f"PDF processing failed: {v_err}")
                    else:
                        pdf_page_count = p_count
                        pdf_size = pdf_clean_path.stat().st_size
                        phase_states["pdf"] = "✅"

                        # Upload to Backblaze B2 private bucket
                        phase_states["b2"] = "🔄"
                        await _update_telegram_ui("Uploading PDF to private B2 storage...", p_pct=100.0, b_pct=50.0)

                        obj_key = B2StorageManager.build_object_key(
                            app_slug=app_slug,
                            batch_slug=batch_slug,
                            folder_slug=slugify(folder_name),
                            lecture_slug=f"{item.index:03d}-{slugify(item.title)}",
                            filename="lecture.pdf"
                        )
                        b2_res = await B2StorageManager.upload_pdf(str(pdf_clean_path), obj_key)
                        b2_object_key = b2_res.get("b2_object_key")
                        phase_states["b2"] = "✅"
                        await _update_telegram_ui("PDF Stored in B2", b_pct=100.0)
                        logger.info(f"[B2_UPLOAD_COMPLETED] lecture_index=#{item.index} b2_key={b2_object_key}")

            # ==========================================
            # PHASE 7 & 8 & 9: DATABASE, PLAYLIST & PUBLISH
            # ==========================================
            phase_states["database"] = "🔄"
            phase_states["playlist"] = "⏳"
            phase_states["publish"] = "⏳"
            await _update_telegram_ui("Attaching database relations...", dl_pct=100.0, wm_pct=100.0, yt_pct=100.0)

            async with get_db_session() as session:
                repo = ContentRepository(session)
                lec = await repo.get_lecture_by_index(batch_id, item.index)
                if lec:
                    if youtube_video_id:
                        await repo.attach_video_to_lecture(
                            lecture_id=lec.id,
                            youtube_video_id=youtube_video_id,
                            duration=video_duration,
                            resolution=video_resolution,
                            file_size=video_size,
                            title=item.title,
                            youtube_channel_id=youtube_channel_id,
                            youtube_account_id=youtube_account_id,
                            youtube_url=youtube_url,
                            upload_completed_at=upload_completed_at
                        )

                    if b2_object_key:
                        await repo.attach_pdf_to_lecture(
                            lecture_id=lec.id,
                            b2_object_key=b2_object_key,
                            b2_bucket=B2_BUCKET,
                            file_name=f"{item.title}.pdf",
                            file_size=pdf_size,
                            page_count=pdf_page_count
                        )

                    phase_states["database"] = "✅"
                    logger.info(f"[DB_SYNCED] lecture_index=#{item.index} lecture_id={lec.id}")

                    # Internal Playlist Sync
                    phase_states["playlist"] = "🔄"
                    await repo.add_lecture_to_playlist(lec.subject_id, lec.id)
                    phase_states["playlist"] = "✅"
                    logger.info(f"[PLAYLIST_UPDATED] lecture_index=#{item.index} subject_id={lec.subject_id}")

                    # Immediate Auto-Publish
                    phase_states["publish"] = "🔄"
                    await repo.set_lecture_published(lec.id)
                    phase_states["publish"] = "✅"
                    logger.info(f"[LECTURE_PUBLISHED] lecture_index=#{item.index} status=PUBLISHED")

            await _update_telegram_ui("Published Successfully ✅", force=True)
            return {"status": "SUCCESS", "index": item.index, "title": item.title}

        finally:
            if locals().get('storage_replication_success', False):
                # Temporary scratch cleanup only after all required storage replication succeeded
                shutil.rmtree(work_dir, ignore_errors=True)
                if downloaded_video_path and os.path.exists(downloaded_video_path):
                    try:
                        os.remove(downloaded_video_path)
                    except Exception:
                        pass
                if 'watermarked_video_path' in locals() and watermarked_video_path and os.path.exists(watermarked_video_path):
                    try:
                        if not locals().get('has_valid_checkpoint', False):
                            os.remove(watermarked_video_path)
                    except Exception:
                        pass
            else:
                logger.info(
                    f"[STORAGE_CLEANUP_PROTECTION] Preserving local video files for lecture #{item.index} "
                    f"because required storage replication is incomplete."
                )
