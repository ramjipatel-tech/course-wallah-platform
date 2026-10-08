import os
import sys
import json
import asyncio
import shutil
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Ensure platform root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db.connection import init_db, get_db_session, engine
from db.repository import ContentRepository
from db.models import Base, PublicationStatus, JobStatus
from parsers.indexer import NormalizedLecture, NormalizedFolder, NormalizedSubject, NormalizedBatchTree
from providers.adapters import (
    AppxProviderAdapter,
    VideoUnavailableError,
    ProviderResolutionError,
    UnifiedMediaDownloader
)
from providers.downloader import MediaDownloader
from engines.youtube_uploader import (
    YouTubeUploader,
    YouTubeUploadLimitExceededError,
    YouTubeApiQuotaExceededError
)
from engines.job_engine import ContentProcessingEngine, BatchJobController
from bot.progress_ui import TelegramMessageThrottler, TelegramProgressUI
from pyrogram.errors import MessageNotModified, RPCError
from api.server import app as fastapi_app
from api.auth import create_jwt_token
from config.settings import ADMIN_USERNAME


class TestCourseWallahResilience(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.test_dir = BASE_DIR / "downloads" / "test_scratch"
        self.test_dir.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        # Clean test checkpoints
        ckpt_dir = BASE_DIR / "downloads" / "checkpoints"
        if ckpt_dir.exists():
            shutil.rmtree(ckpt_dir, ignore_errors=True)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def test_appx_case_a_video_and_pdf_single_resolution(self):
        """
        CASE A: AppX returns Video + PDF in a single resolution call.
        Requirements:
        1. Single AppX resolver call
        2. Video processed first -> Watermark -> Thumbnail -> YouTube upload
        3. PDF processed second -> Brand/decrypt -> B2 upload
        4. Both video_id and pdf_id attached to the same lecture_id
        """
        fake_url = "https://appx.store/fetch_video?id=101"
        fake_lec_res = MagicMock()
        fake_lec_res.is_drm = False
        fake_lec_res.has_video = True
        fake_lec_res.video_url = "https://cdn.example.com/stream.m3u8"
        fake_lec_res.has_pdf = True
        fake_lec_res.pdf_url = "https://cdn.example.com/notes.pdf"
        fake_lec_res.title = "AppX Lecture A"
        fake_lec_res.thumbnail = "https://cdn.example.com/thumb.jpg"
        fake_lec_res.video_id = "v_101"
        fake_lec_res.course_id = "c_101"
        fake_lec_res.video_quality = "720p"

        dummy_video = self.test_dir / "video_a.mp4"
        dummy_video.write_bytes(b"\x00" * 4096)

        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("AppX App")
            batch, _ = await repo.get_or_create_batch(app.id, "AppX Batch A")

        item = NormalizedLecture(
            index=1,
            title="AppX Lecture A",
            video_url=fake_url,
            pdf_url=None,
            provider="appx_lecture"
        )

        mock_yt = AsyncMock(return_value={"youtube_video_id": "yt_case_a", "status": "UPLOADED"})
        mock_b2 = AsyncMock(return_value={"b2_object_key": "apps/appx/lec1.pdf", "file_id": "b2_case_a"})

        def mock_validate_pdf(input_pdf, output_pdf, password=None, watermark_text=None):
            Path(output_pdf).write_bytes(b"%PDF-1.4 cleaned test content")
            return (True, 10, None)

        def mock_watermark(input_video, output_video, watermark_text, animation_mode):
            Path(output_video).write_bytes(b"\x00" * 4096)
            return output_video

        engine_inst = ContentProcessingEngine(bot_id="bot_test")

        with patch("providers.adapters.original_helper.resolve_lecture_source", return_value=fake_lec_res) as mock_resolver, \
             patch("providers.adapters.original_helper.download_appx_m3u8", return_value=str(dummy_video)), \
             patch("providers.adapters.MediaValidator.validate_video_file", new_callable=AsyncMock, return_value={"valid": True}), \
             patch("engines.job_engine.VideoProcessor.probe_video", new_callable=AsyncMock, return_value={"duration": 180.0, "resolution": "720p", "size": 4096}), \
             patch("engines.job_engine.VideoProcessor.split_if_large", new_callable=AsyncMock, return_value=[str(dummy_video)]), \
             patch("engines.job_engine.WatermarkEngine.apply_watermark", side_effect=mock_watermark), \
             patch("engines.job_engine.VideoProcessor.extract_thumbnail", new_callable=AsyncMock, return_value=None), \
             patch("engines.job_engine.YouTubeUploader.upload_video", mock_yt), \
             patch("engines.job_engine.YouTubeUploader.check_video_status", new_callable=AsyncMock, return_value={"is_ready": True, "upload_status": "uploaded"}), \
             patch("engines.job_engine.download_pdf_file", return_value=(True, None)), \
             patch("engines.job_engine.validate_and_process_pdf", side_effect=mock_validate_pdf), \
             patch("engines.job_engine.B2StorageManager.upload_pdf", mock_b2):

            res = await engine_inst.process_lecture_item(
                app_id=app.id,
                app_slug=app.slug,
                batch_id=batch.id,
                batch_slug=batch.slug,
                subject_name="Engineering",
                folder_name="Unit 1",
                unit_number="1",
                item=item,
                user_id=12345
            )

            self.assertEqual(res["status"], "SUCCESS")
            # 1. Single AppX resolver call verified
            mock_resolver.assert_called_once()
            # 2. YouTube upload called
            mock_yt.assert_called_once()
            # 3. B2 upload called
            mock_b2.assert_called_once()

        # 4. Verify DB state: both video and PDF attached to SAME lecture
        async with get_db_session() as session:
            repo = ContentRepository(session)
            db_lec = await repo.get_lecture_by_index(batch.id, 1)
            self.assertIsNotNone(db_lec)
            self.assertTrue(db_lec.has_video)
            self.assertTrue(db_lec.has_pdf)
            self.assertEqual(db_lec.publication_status, PublicationStatus.PUBLISHED)
            self.assertIsNotNone(db_lec.video)
            self.assertEqual(db_lec.video.youtube_video_id, "yt_case_a")
            self.assertIsNotNone(db_lec.pdf)
            self.assertEqual(db_lec.pdf.b2_object_key, "apps/appx/lec1.pdf")

    async def test_appx_case_b_video_only(self):
        """
        CASE B: AppX returns Video ONLY.
        Requirements:
        - Download only video
        - Watermark + Thumbnail + YouTube upload
        - DB video relation created
        - Do NOT attempt PDF
        """
        fake_url = "https://appx.store/fetch_video?id=102"
        fake_lec_res = MagicMock()
        fake_lec_res.is_drm = False
        fake_lec_res.has_video = True
        fake_lec_res.video_url = "https://cdn.example.com/stream2.m3u8"
        fake_lec_res.has_pdf = False
        fake_lec_res.pdf_url = None
        fake_lec_res.title = "AppX Video Only"
        fake_lec_res.thumbnail = None
        fake_lec_res.video_id = "v_102"
        fake_lec_res.course_id = "c_102"
        fake_lec_res.video_quality = "720p"

        dummy_video = self.test_dir / "video_b.mp4"
        dummy_video.write_bytes(b"\x00" * 4096)

        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("AppX App")
            batch, _ = await repo.get_or_create_batch(app.id, "AppX Batch B")

        item = NormalizedLecture(
            index=2,
            title="AppX Video Only",
            video_url=fake_url,
            pdf_url=None,
            provider="appx_lecture"
        )

        mock_yt = AsyncMock(return_value={"youtube_video_id": "yt_case_b", "status": "UPLOADED"})
        mock_pdf_dl = MagicMock()

        def mock_watermark_b(input_video, output_video, watermark_text, animation_mode):
            Path(output_video).write_bytes(b"\x00" * 4096)
            return output_video

        engine_inst = ContentProcessingEngine(bot_id="bot_test")

        with patch("providers.adapters.original_helper.resolve_lecture_source", return_value=fake_lec_res), \
             patch("providers.adapters.original_helper.download_appx_m3u8", return_value=str(dummy_video)), \
             patch("providers.adapters.MediaValidator.validate_video_file", new_callable=AsyncMock, return_value={"valid": True}), \
             patch("engines.job_engine.VideoProcessor.probe_video", new_callable=AsyncMock, return_value={"duration": 120.0, "resolution": "720p", "size": 4096}), \
             patch("engines.job_engine.VideoProcessor.split_if_large", new_callable=AsyncMock, return_value=[str(dummy_video)]), \
             patch("engines.job_engine.WatermarkEngine.apply_watermark", side_effect=mock_watermark_b), \
             patch("engines.job_engine.VideoProcessor.extract_thumbnail", new_callable=AsyncMock, return_value=None), \
             patch("engines.job_engine.YouTubeUploader.upload_video", mock_yt), \
             patch("engines.job_engine.YouTubeUploader.check_video_status", new_callable=AsyncMock, return_value={"is_ready": True, "upload_status": "uploaded"}), \
             patch("engines.job_engine.download_pdf_file", mock_pdf_dl):

            res = await engine_inst.process_lecture_item(
                app_id=app.id,
                app_slug=app.slug,
                batch_id=batch.id,
                batch_slug=batch.slug,
                subject_name="Engineering",
                folder_name="Unit 1",
                unit_number="1",
                item=item,
                user_id=12345
            )

            self.assertEqual(res["status"], "SUCCESS")
            mock_yt.assert_called_once()
            mock_pdf_dl.assert_not_called()

        # Verify DB state
        async with get_db_session() as session:
            repo = ContentRepository(session)
            db_lec = await repo.get_lecture_by_index(batch.id, 2)
            self.assertIsNotNone(db_lec)
            self.assertTrue(db_lec.has_video)
            self.assertFalse(db_lec.has_pdf)
            self.assertIsNotNone(db_lec.video)
            self.assertIsNone(db_lec.pdf)

    async def test_appx_case_c_pdf_only_no_video_retries(self):
        """
        CASE C: AppX returns ONLY PDF (Video=NO | PDF=YES).
        Requirements:
        - DO NOT retry video download 3 times
        - DO NOT invent video URL or use generic yt-dlp fallback
        - Skip video stage immediately
        - Decrypt/brand/upload PDF to private B2
        - Save pdf_id against lecture_id with has_video=False, has_pdf=True
        """
        fake_url = "https://akstechnicalclasses.courses.store/get/fetch_video_url?course_id=100&video_id=200"

        fake_lec_res = MagicMock()
        fake_lec_res.is_drm = False
        fake_lec_res.has_video = False
        fake_lec_res.video_url = None
        fake_lec_res.has_pdf = True
        fake_lec_res.pdf_url = "https://cdn.example.com/lecture_notes.pdf"
        fake_lec_res.title = "Unit 1 Lecture 1 Notes"
        fake_lec_res.thumbnail = None
        fake_lec_res.video_id = "200"
        fake_lec_res.course_id = "100"
        fake_lec_res.video_quality = "720p"

        with patch("providers.adapters.original_helper.resolve_lecture_source", return_value=fake_lec_res):
            with self.assertRaises(VideoUnavailableError) as ctx:
                await AppxProviderAdapter.resolve_and_download(fake_url, "Lecture 1")
            
            self.assertEqual(ctx.exception.pdf_url, "https://cdn.example.com/lecture_notes.pdf")
            self.assertIn("PDF available", str(ctx.exception))

        engine_inst = ContentProcessingEngine(bot_id="bot_test")
        item = NormalizedLecture(
            index=3,
            title="Lecture 3 - Notes Only",
            video_url=fake_url,
            pdf_url=None,
            provider="appx_lecture"
        )

        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("Test App")
            batch, _ = await repo.get_or_create_batch(app.id, "Test Batch PDF Only")

        def mock_validate_pdf(input_pdf, output_pdf, password=None, watermark_text=None):
            Path(output_pdf).write_bytes(b"%PDF-1.4 cleaned test content")
            return (True, 5, None)

        mock_yt_upload = AsyncMock()

        with patch("providers.adapters.original_helper.resolve_lecture_source", return_value=fake_lec_res), \
             patch("engines.job_engine.YouTubeUploader.upload_video", mock_yt_upload), \
             patch("engines.job_engine.download_pdf_file", return_value=(True, None)), \
             patch("engines.job_engine.validate_and_process_pdf", side_effect=mock_validate_pdf), \
             patch("engines.job_engine.B2StorageManager.upload_pdf", new_callable=AsyncMock) as mock_b2:
            
            mock_b2.return_value = {"b2_object_key": "apps/test/batches/b1/notes.pdf", "file_id": "b2_123"}
            
            res = await engine_inst.process_lecture_item(
                app_id=app.id,
                app_slug=app.slug,
                batch_id=batch.id,
                batch_slug=batch.slug,
                subject_name="Mathematics",
                folder_name="Unit 1",
                unit_number="1",
                item=item,
                user_id=12345
            )

            self.assertEqual(res["status"], "SUCCESS")
            # Video upload never attempted
            mock_yt_upload.assert_not_called()
            # B2 upload succeeded
            mock_b2.assert_called_once()

        # Verify DB state
        async with get_db_session() as session:
            repo = ContentRepository(session)
            db_lec = await repo.get_lecture_by_index(batch.id, 3)
            self.assertIsNotNone(db_lec)
            self.assertFalse(db_lec.has_video)
            self.assertTrue(db_lec.has_pdf)
            self.assertEqual(db_lec.publication_status, PublicationStatus.PUBLISHED)
            self.assertIsNone(db_lec.video)
            self.assertIsNotNone(db_lec.pdf)
            self.assertEqual(db_lec.pdf.b2_object_key, "apps/test/batches/b1/notes.pdf")

    async def test_appx_case_d_neither_video_nor_pdf(self):
        """
        CASE D: AppX returns NEITHER video nor PDF.
        Requirements:
        - Mark explicit NO_MEDIA error
        - Do not loop indefinitely
        - Never fabricate media
        """
        fake_url = "https://appx.store/fetch_video?id=empty"
        fake_lec_res = MagicMock()
        fake_lec_res.is_drm = False
        fake_lec_res.has_video = False
        fake_lec_res.video_url = None
        fake_lec_res.has_pdf = False
        fake_lec_res.pdf_url = None
        fake_lec_res.error = "No media stream or notes available for this lecture."

        with patch("providers.adapters.original_helper.resolve_lecture_source", return_value=fake_lec_res):
            with self.assertRaises(ProviderResolutionError) as ctx:
                await AppxProviderAdapter.resolve_and_download(fake_url, "Empty Lecture")
            self.assertIn("No playable video or PDF found", str(ctx.exception))

    async def test_youtube_error_classification_quota_vs_limit(self):
        """
        Verify distinction between uploadLimitExceeded (CHANNEL_UPLOAD_LIMIT)
        and quotaExceeded (API_PROJECT_QUOTA).
        """
        limit_err = YouTubeUploadLimitExceededError("Account limit exceeded", status_code=400)
        self.assertEqual(limit_err.reason, "uploadLimitExceeded")
        self.assertEqual(limit_err.classification, "CHANNEL_UPLOAD_LIMIT")
        self.assertTrue(limit_err.is_account_limit)

        quota_err = YouTubeApiQuotaExceededError("Project quota units exhausted", status_code=403)
        self.assertEqual(quota_err.reason, "quotaExceeded")
        self.assertEqual(quota_err.classification, "API_PROJECT_QUOTA")
        self.assertFalse(quota_err.is_account_limit)

    async def test_youtube_upload_limit_exceeded_and_checkpoint_resume(self):
        """
        Verify that when YouTube uploadLimitExceeded occurs:
        1. YouTubeUploadLimitExceededError is raised immediately on attempt 1 without retry storm
        2. Prepared watermarked video and thumbnail are checkpointed on disk
        3. Ingestion loop pauses gracefully with youtube_limit_reached=True
        4. When resumed, checkpoint is loaded, skipping download & watermark phases
        """
        engine_inst = ContentProcessingEngine(bot_id="bot_test")

        dummy_video = self.test_dir / "raw_video.mp4"
        dummy_video.write_bytes(b"\x00" * 4096)

        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("Test App 2")
            batch, _ = await repo.get_or_create_batch(app.id, "Test Batch Limit")

        item = NormalizedLecture(
            index=2,
            title="Lecture 2 - YouTube Limit Test",
            video_url="https://example.com/video2.mp4",
            pdf_url=None,
            provider="direct_video"
        )

        upload_attempts = []

        async def mock_upload_with_limit(*args, **kwargs):
            upload_attempts.append(1)
            raise YouTubeUploadLimitExceededError(
                "YouTube uploadLimitExceeded: The user has exceeded the number of videos they may upload.",
                status_code=400,
                raw_response='{"error": {"code": 400, "errors": [{"reason": "uploadLimitExceeded"}]}}'
            )

        async def mock_watermark(input_video, output_video, watermark_text, animation_mode):
            Path(output_video).write_bytes(b"\x00" * 4096)
            return output_video

        with patch("engines.job_engine.MediaDownloader.download_video_stream_with_meta", new_callable=AsyncMock, return_value=(str(dummy_video), {})), \
             patch("engines.job_engine.VideoProcessor.probe_video", new_callable=AsyncMock, return_value={"duration": 120.0, "resolution": "720p", "size": 4096}), \
             patch("engines.job_engine.VideoProcessor.split_if_large", new_callable=AsyncMock, return_value=[str(dummy_video)]), \
             patch("engines.job_engine.WatermarkEngine.apply_watermark", side_effect=mock_watermark), \
             patch("engines.job_engine.VideoProcessor.extract_thumbnail", new_callable=AsyncMock, return_value=None), \
             patch("engines.job_engine.YouTubeUploader.upload_video", side_effect=mock_upload_with_limit):

            with self.assertRaises(YouTubeUploadLimitExceededError):
                await engine_inst.process_lecture_item(
                    app_id=app.id,
                    app_slug=app.slug,
                    batch_id=batch.id,
                    batch_slug=batch.slug,
                    subject_name="Physics",
                    folder_name="Unit 1",
                    unit_number="1",
                    item=item,
                    user_id=12345
                )

        # 1. Verify zero retry storm: upload was attempted exactly once!
        self.assertEqual(len(upload_attempts), 1)

        # 2. Verify checkpoint was created on disk
        ckpt_dir = BASE_DIR / "downloads" / "checkpoints" / str(batch.id) / f"lec_{item.index:04d}"
        ckpt_file = ckpt_dir / "checkpoint.json"
        self.assertTrue(ckpt_file.exists())
        ckpt_data = json.loads(ckpt_file.read_text("utf-8"))
        self.assertEqual(ckpt_data.get("reason"), "uploadLimitExceeded")
        self.assertEqual(ckpt_data.get("stage"), "WATERMARKED_READY_FOR_UPLOAD")
        self.assertTrue((ckpt_dir / "wm_video.mp4").exists())

        # 3. Test Resume from Checkpoint (Download and Watermark should NOT be called!)
        mock_download = AsyncMock()
        mock_watermark = AsyncMock()
        mock_yt_success = AsyncMock(return_value={"youtube_video_id": "yt_resumed_999", "status": "UPLOADED"})

        with patch("engines.job_engine.MediaDownloader.download_video_stream_with_meta", mock_download), \
             patch("engines.job_engine.WatermarkEngine.apply_watermark", mock_watermark), \
             patch("engines.job_engine.YouTubeUploader.upload_video", mock_yt_success), \
             patch("engines.job_engine.YouTubeUploader.check_video_status", new_callable=AsyncMock, return_value={"is_ready": True, "upload_status": "uploaded"}):

            res = await engine_inst.process_lecture_item(
                app_id=app.id,
                app_slug=app.slug,
                batch_id=batch.id,
                batch_slug=batch.slug,
                subject_name="Physics",
                folder_name="Unit 1",
                unit_number="1",
                item=item,
                user_id=12345
            )

            self.assertEqual(res["status"], "SUCCESS")
            # Verify download and watermark were skipped (reused checkpoint)
            mock_download.assert_not_called()
            mock_watermark.assert_not_called()
            mock_yt_success.assert_called_once()

        # Checkpoint should now be cleaned up after successful upload
        self.assertFalse(ckpt_file.exists())

    async def test_admin_youtube_diagnostics_endpoint(self):
        """
        Verify /admin/youtube diagnostics endpoint returns channel health,
        platform DB upload counts (24h/7d/30d), labels, and disclaimers.
        """
        token = create_jwt_token({"sub": ADMIN_USERNAME, "role": "ADMIN"})
        headers = {"Authorization": f"Bearer {token}"}

        transport = ASGITransport(app=fastapi_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/v1/admin/youtube", headers=headers)
            self.assertEqual(resp.status_code, 200)
            data = resp.json()

            self.assertIn("channel", data)
            self.assertIn("platform_upload_history", data)
            self.assertIn("queues", data)
            self.assertIn("limits_policy", data)

            # Check explicit labels & disclaimer
            self.assertIn("label", data["platform_upload_history"])
            self.assertIn("disclaimer", data["limits_policy"])
            self.assertIn("CHANNEL_UPLOAD_LIMIT", data["limits_policy"]["error_classification"]["uploadLimitExceeded"])

            # Test refresh
            ref_resp = await client.post("/api/v1/admin/youtube/refresh", headers=headers)
            self.assertEqual(ref_resp.status_code, 200)

    async def test_telegram_message_not_modified_handling(self):
        """
        Verify that MessageNotModified from Pyrogram is handled gracefully
        without throwing unhandled exceptions or breaking the callback loop.
        """
        throttler = TelegramMessageThrottler(min_interval=0.1)

        fake_msg = MagicMock()
        fake_msg.edit_text = AsyncMock(side_effect=MessageNotModified)

        res = await throttler.edit(fake_msg, "Same Text", force=True)
        self.assertTrue(res)

    async def test_telegram_disconnect_non_fatal_to_job(self):
        """
        Verify that if Telegram raises a ConnectionError or RPCError during status message edits,
        the job progress continues without marking the lecture failed.
        """
        throttler = TelegramMessageThrottler(min_interval=0.1)

        fake_msg = MagicMock()
        fake_msg.edit_text = AsyncMock(side_effect=ConnectionError("Client has not been started yet"))

        res = await throttler.edit(fake_msg, "New Text", force=True)
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
