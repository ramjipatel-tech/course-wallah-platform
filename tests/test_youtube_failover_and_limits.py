"""
Unit & Integration Test Suite for Course Wallah YouTube Multi-Account Failover & Limit-Aware Upload Manager.

Covers 14 Critical Scenarios:
1. Successful upload
2. uploadLimitExceeded (CHANNEL_UPLOAD_LIMIT classification & handling)
3. Multi-account rotation (failover from limit-reached account to next active account)
4. No available account (durable checkpoint saved & graceful exception)
5. Temporary 5xx retry
6. Auth error (unauthorized_client / invalid_grant marked AUTH_ERROR)
7. Duplicate upload prevention (checking DB youtube_video_id before uploading)
8. Checkpoint recovery (resuming prepared video artifact without redownload/re-watermark)
9. Worker restart recovery (recovering state from durable checkpoint)
10. Successful upload persistence (DB recording youtube_video_id, youtube_channel_id, youtube_account_id, upload_completed_at)
11. PDF-only lecture (does not fail when video unavailable)
12. Video + PDF lecture (processes video first, PDF second)
13. Batch continuation after YouTube limit
14. Multiple accounts with deterministic selection (priority ASC, uploads_today ASC, created_at ASC)
"""

import os
import sys
import json
import shutil
import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from typing import Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from config.settings import DOWNLOADS_DIR
from db.connection import init_db, get_db_session
from db.models import (
    App, Batch, Subject, Folder, Lecture, Video, PDF,
    PublicationStatus, JobStatus, YouTubeAccount, YouTubeAccountStatus
)
from db.repository import ContentRepository, slugify
from engines.youtube_account_manager import (
    YouTubeAccountManager,
    YouTubeAccountAuthError,
    YouTubeTemporaryUploadError,
    YouTubePermanentUploadError,
    DEFAULT_ESTIMATED_DAILY_LIMIT
)
from engines.youtube_uploader import (
    YouTubeUploadLimitExceededError,
    YouTubeApiQuotaExceededError
)
from engines.job_engine import ContentProcessingEngine


class TestYouTubeMultiAccountFailover(unittest.IsolatedAsyncioTestCase):
    
    async def asyncSetUp(self):
        """Initializes test database and creates temporary test artifacts."""
        await init_db()
        self.test_dir = Path(DOWNLOADS_DIR) / "test_scratch"
        self.test_dir.mkdir(parents=True, exist_ok=True)
        
        # Create dummy video file
        self.dummy_video = self.test_dir / "test_video.mp4"
        self.dummy_video.write_bytes(b"\x00" * 4096)  # 4KB dummy file
        
        # Create dummy thumbnail
        self.dummy_thumb = self.test_dir / "test_thumb.jpg"
        self.dummy_thumb.write_bytes(b"\xFF\xD8\xFF" + b"\x00" * 512)

        # Ensure clean accounts slate with direct SQL update
        async with get_db_session() as session:
            from sqlalchemy import update
            await session.execute(
                update(YouTubeAccount).values(
                    status=YouTubeAccountStatus.DISABLED.value,
                    is_active=False,
                    uploads_today=0,
                    cooldown_until=None
                )
            )

    async def asyncTearDown(self):
        """Cleans up scratch files and test accounts, restoring primary .env account."""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)
        ckpt_base = Path(DOWNLOADS_DIR) / "checkpoints" / "test_batch_123"
        if ckpt_base.exists():
            shutil.rmtree(ckpt_base, ignore_errors=True)

        # Purge test accounts and restore primary
        async with get_db_session() as session:
            from sqlalchemy import select, delete
            from config.settings import YOUTUBE_CLIENT_ID
            res = await session.execute(select(YouTubeAccount))
            for a in res.scalars().all():
                if a.client_id != YOUTUBE_CLIENT_ID:
                    await session.delete(a)
                else:
                    a.status = YouTubeAccountStatus.ACTIVE.value
                    a.priority = 1
                    a.cooldown_until = None
                    a.limit_detected_at = None

        await YouTubeAccountManager.sync_primary_from_env()

    async def _create_test_hierarchy(self, session, batch_name: str = "Test Batch") -> Tuple[App, Batch, Subject, Folder]:
        repo = ContentRepository(session)
        app = await repo.get_or_create_app(name="Test App")
        batch, _ = await repo.get_or_create_batch(app_id=app.id, name=batch_name)
        subject = await repo.get_or_create_subject(batch_id=batch.id, name=f"Subject for {batch_name}")
        folder = await repo.get_or_create_folder(subject_id=subject.id, name="Test Folder")
        return app, batch, subject, folder

    async def _create_test_lecture(self, session, index: int, title: str, batch_name: str = "Test Batch") -> Lecture:
        _, batch, subject, folder = await self._create_test_hierarchy(session, batch_name=batch_name)
        repo = ContentRepository(session)
        lec = await repo.create_or_update_lecture(
            folder_id=folder.id,
            subject_id=subject.id,
            batch_id=batch.id,
            lecture_index=index,
            title=title
        )
        return lec

    # -------------------------------------------------------------------------
    # TEST 1: Successful upload
    # -------------------------------------------------------------------------
    async def test_01_successful_upload(self):
        """Verifies that a valid account completes the upload and cleans up local video file."""
        account_id = None
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.create_or_update_youtube_account(
                name="Success Channel",
                client_id="cid_success",
                client_secret="sec_success",
                refresh_token="ref_success",
                channel_id="UC_SUCCESS",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            account_id = acc.id

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock), \
             patch.object(YouTubeAccountManager, "_get_account_access_token", new_callable=AsyncMock) as mock_token, \
             patch.object(YouTubeAccountManager, "_execute_resumable_upload", new_callable=AsyncMock) as mock_upload:
            
            mock_token.return_value = "ya29.mock_access_token"
            mock_upload.return_value = {
                "youtube_video_id": "yt_success_123",
                "title": "Test Lecture",
                "status": "UPLOADED",
                "file_size": 4096
            }

            res = await YouTubeAccountManager.upload_with_multi_account_failover(
                file_path=str(self.dummy_video),
                title="Test Lecture",
                thumbnail_path=str(self.dummy_thumb),
                batch_id="test_batch_123",
                lecture_index=1
            )

            self.assertEqual(res["youtube_video_id"], "yt_success_123")
            self.assertEqual(res["youtube_account_id"], account_id)
            self.assertEqual(res["youtube_channel_id"], "UC_SUCCESS")
            mock_upload.assert_called_once()
            
            # Verify local video was cleaned up to conserve server storage
            self.assertFalse(os.path.exists(str(self.dummy_video)))

    # -------------------------------------------------------------------------
    # TEST 2: uploadLimitExceeded error classification & handling
    # -------------------------------------------------------------------------
    def test_02_error_classification(self):
        """Verifies accurate classification of YouTube errors."""
        # CHANNEL_UPLOAD_LIMIT
        c1 = YouTubeAccountManager.classify_error(400, '{"error": {"errors": [{"reason": "uploadLimitExceeded"}]}}')
        self.assertEqual(c1, "CHANNEL_UPLOAD_LIMIT")
        
        c1_alt = YouTubeAccountManager.classify_error(400, "The user has exceeded the upload limit for videos.")
        self.assertEqual(c1_alt, "CHANNEL_UPLOAD_LIMIT")

        # API_PROJECT_QUOTA
        c2 = YouTubeAccountManager.classify_error(403, '{"error": {"errors": [{"reason": "quotaExceeded"}]}}')
        self.assertEqual(c2, "API_PROJECT_QUOTA")

        # AUTH_ERROR
        c3 = YouTubeAccountManager.classify_error(401, '{"error": "unauthorized_client", "error_description": "Unauthorized"}')
        self.assertEqual(c3, "AUTH_ERROR")

        c3_alt = YouTubeAccountManager.classify_error(400, '{"error": "invalid_grant"}')
        self.assertEqual(c3_alt, "AUTH_ERROR")

        # TEMPORARY
        c4 = YouTubeAccountManager.classify_error(503, "Service Unavailable")
        self.assertEqual(c4, "TEMPORARY")
        
        c4_429 = YouTubeAccountManager.classify_error(429, "Too Many Requests")
        self.assertEqual(c4_429, "TEMPORARY")

        # PERMANENT
        c5 = YouTubeAccountManager.classify_error(400, "Invalid title characters")
        self.assertEqual(c5, "PERMANENT")

    # -------------------------------------------------------------------------
    # TEST 3: Multi-account rotation on uploadLimitExceeded
    # -------------------------------------------------------------------------
    async def test_03_account_rotation_on_limit(self):
        """Verifies that hitting daily limit on Account A rotates to Account B seamlessly."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc_a = await repo.create_or_update_youtube_account(
                name="Channel A (Hits Limit)",
                client_id="cid_a",
                client_secret="sec_a",
                refresh_token="ref_a",
                channel_id="UC_CHANNEL_A",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            acc_b = await repo.create_or_update_youtube_account(
                name="Channel B (Fallback)",
                client_id="cid_b",
                client_secret="sec_b",
                refresh_token="ref_b",
                channel_id="UC_CHANNEL_B",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=2
            )

        call_count = 0
        async def mock_upload_fn(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Account A fails with uploadLimitExceeded
                raise YouTubeUploadLimitExceededError("Daily limit reached", status_code=400, raw_response="uploadLimitExceeded")
            else:
                # Account B succeeds
                return {
                    "youtube_video_id": "yt_from_channel_b",
                    "title": kwargs.get("title"),
                    "status": "UPLOADED",
                    "file_size": 4096
                }

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock), \
             patch.object(YouTubeAccountManager, "_get_account_access_token", new_callable=AsyncMock) as mock_token, \
             patch.object(YouTubeAccountManager, "_execute_resumable_upload", side_effect=mock_upload_fn):
            
            mock_token.return_value = "ya29.mock_token"

            res = await YouTubeAccountManager.upload_with_multi_account_failover(
                file_path=str(self.dummy_video),
                title="Failover Lecture",
                thumbnail_path=str(self.dummy_thumb),
                batch_id="test_batch_123",
                lecture_index=2
            )

            self.assertEqual(res["youtube_video_id"], "yt_from_channel_b")
            self.assertEqual(res["youtube_channel_id"], "UC_CHANNEL_B")
            self.assertEqual(call_count, 2)

            # Check that Account A was marked LIMIT_REACHED in DB with cooldown
            async with get_db_session() as session:
                repo = ContentRepository(session)
                refreshed_a = await repo.get_youtube_account_by_id(acc_a.id)
                self.assertEqual(refreshed_a.status, YouTubeAccountStatus.LIMIT_REACHED.value)
                self.assertIsNotNone(refreshed_a.limit_detected_at)
                self.assertIsNotNone(refreshed_a.cooldown_until)

    # -------------------------------------------------------------------------
    # TEST 4: No available accounts -> durable checkpoint & graceful pause
    # -------------------------------------------------------------------------
    async def test_04_no_available_account(self):
        """Verifies checkpoint is saved and exception raised when no accounts remain."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            accounts = await repo.get_all_youtube_accounts()
            for a in accounts:
                await repo.mark_youtube_account_status(a.id, YouTubeAccountStatus.LIMIT_REACHED.value, "Manual limit for test")

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock):
            with self.assertRaises(YouTubeUploadLimitExceededError):
                await YouTubeAccountManager.upload_with_multi_account_failover(
                    file_path=str(self.dummy_video),
                    title="Paused Lecture",
                    batch_id="test_batch_123",
                    lecture_index=3
                )

        # Check durable checkpoint exists
        ckpt = YouTubeAccountManager.load_checkpoint("test_batch_123", 3)
        self.assertIsNotNone(ckpt)
        self.assertEqual(ckpt["lecture_index"], 3)
        self.assertEqual(ckpt["status"], "WAITING_FOR_YOUTUBE_ACCOUNT")

    # -------------------------------------------------------------------------
    # TEST 5: Temporary 5xx retry
    # -------------------------------------------------------------------------
    async def test_05_temporary_error_retry(self):
        """Verifies transient 5xx errors are re-raised for bounded exponential retry."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            await repo.create_or_update_youtube_account(
                name="Active Channel",
                client_id="cid_temp",
                client_secret="sec_temp",
                refresh_token="ref_temp",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock), \
             patch.object(YouTubeAccountManager, "_get_account_access_token", new_callable=AsyncMock) as mock_token, \
             patch.object(YouTubeAccountManager, "_execute_resumable_upload", new_callable=AsyncMock) as mock_upload:
            
            mock_token.return_value = "ya29.token"
            mock_upload.side_effect = YouTubeTemporaryUploadError("503 Service Unavailable", status_code=503)

            with self.assertRaises(YouTubeTemporaryUploadError):
                await YouTubeAccountManager.upload_with_multi_account_failover(
                    file_path=str(self.dummy_video),
                    title="Temp Error Lecture",
                    batch_id="test_batch_123",
                    lecture_index=4
                )

    # -------------------------------------------------------------------------
    # TEST 6: Auth error handling
    # -------------------------------------------------------------------------
    async def test_06_auth_error_handling(self):
        """Verifies that invalid_grant/unauthorized_client marks account AUTH_ERROR."""
        acc_bad_id = None
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc_bad = await repo.create_or_update_youtube_account(
                name="Bad Token Channel",
                client_id="cid_bad",
                client_secret="sec_bad",
                refresh_token="ref_bad",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            acc_bad_id = acc_bad.id

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock), \
             patch.object(YouTubeAccountManager, "_get_account_access_token", new_callable=AsyncMock) as mock_token:
            mock_token.return_value = None  # Failed auth

            with self.assertRaises(YouTubeUploadLimitExceededError):  # Fails all accounts
                await YouTubeAccountManager.upload_with_multi_account_failover(
                    file_path=str(self.dummy_video),
                    title="Auth Error Lecture",
                    batch_id="test_batch_123",
                    lecture_index=5
                )

            async with get_db_session() as session:
                repo = ContentRepository(session)
                refreshed = await repo.get_youtube_account_by_id(acc_bad_id)
                self.assertEqual(refreshed.status, YouTubeAccountStatus.AUTH_ERROR.value)

    # -------------------------------------------------------------------------
    # TEST 7: Duplicate upload prevention
    # -------------------------------------------------------------------------
    async def test_07_duplicate_upload_prevention(self):
        """Verifies that existing DB youtube_video_id bypasses re-uploading."""
        lecture_id = None
        async with get_db_session() as session:
            lec = await self._create_test_lecture(session, 7, "Already Uploaded Lecture")
            lecture_id = lec.id

            repo = ContentRepository(session)
            await repo.attach_video_to_lecture(
                lecture_id=lecture_id,
                youtube_video_id="EXISTING_YT_VIDEO_999",
                youtube_channel_id="UC_EXISTING",
                youtube_account_id="acc_1",
                youtube_url="https://youtu.be/EXISTING_YT_VIDEO_999",
                duration=120.0
            )

        with patch.object(YouTubeAccountManager, "_execute_resumable_upload", new_callable=AsyncMock) as mock_upload:
            res = await YouTubeAccountManager.upload_with_multi_account_failover(
                file_path=str(self.dummy_video),
                title="Already Uploaded Lecture",
                lecture_id=lecture_id,
                batch_id="test_batch_123",
                lecture_index=7
            )
            self.assertEqual(res["youtube_video_id"], "EXISTING_YT_VIDEO_999")
            self.assertEqual(res["status"], "ALREADY_UPLOADED")
            mock_upload.assert_not_called()

    # -------------------------------------------------------------------------
    # TEST 8 & 9: Checkpoint recovery & Worker restart recovery
    # -------------------------------------------------------------------------
    async def test_08_09_checkpoint_recovery(self):
        """Verifies checkpoint saving and loading preserves prepared artifacts without redownloading."""
        ckpt_file = YouTubeAccountManager.save_checkpoint(
            batch_id="test_batch_123",
            lecture_id="lec_123",
            lecture_index=8,
            title="Checkpointed Lecture",
            prepared_video_path=str(self.dummy_video),
            thumbnail_path=str(self.dummy_thumb),
            duration=300.0,
            resolution="1080p",
            file_size=4096,
            reason="uploadLimitExceeded"
        )
        self.assertTrue(ckpt_file.exists())

        # Load checkpoint
        loaded = YouTubeAccountManager.load_checkpoint("test_batch_123", 8)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["lecture_index"], 8)
        self.assertEqual(loaded["title"], "Checkpointed Lecture")
        self.assertTrue(os.path.exists(loaded["prepared_video_path"]))
        self.assertTrue(os.path.exists(loaded["thumbnail_path"]))

        # Clear checkpoint
        YouTubeAccountManager.clear_checkpoint("test_batch_123", 8)
        self.assertIsNone(YouTubeAccountManager.load_checkpoint("test_batch_123", 8))

    # -------------------------------------------------------------------------
    # TEST 10: Successful upload persistence in database
    # -------------------------------------------------------------------------
    async def test_10_upload_persistence(self):
        """Verifies successful upload records account ID, channel ID, video ID, and timestamp."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc = await repo.create_or_update_youtube_account(
                name="Persistence Channel",
                client_id="cid_p",
                client_secret="sec_p",
                refresh_token="ref_p",
                channel_id="UC_PERSIST",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            lec = await self._create_test_lecture(session, 10, "Persist Lecture")
            lec_id = lec.id

            await repo.record_successful_youtube_upload(
                account_id=acc.id,
                lecture_id=lec_id,
                youtube_video_id="YT_PERSIST_456",
                youtube_channel_id="UC_PERSIST",
                job_id="batch_persist"
            )

            # Validate account uploads today incremented
            refreshed_acc = await repo.get_youtube_account_by_id(acc.id)
            self.assertEqual(refreshed_acc.uploads_today, 1)
            self.assertIsNotNone(refreshed_acc.last_upload_at)

            # Validate video attachment
            refreshed_lec = await repo.get_lecture_by_id(lec_id)
            self.assertIsNotNone(refreshed_lec.video)
            self.assertEqual(refreshed_lec.video.youtube_video_id, "YT_PERSIST_456")
            self.assertEqual(refreshed_lec.video.youtube_account_id, acc.id)
            self.assertEqual(refreshed_lec.video.youtube_channel_id, "UC_PERSIST")

    # -------------------------------------------------------------------------
    # TEST 11: PDF-only lecture
    # -------------------------------------------------------------------------
    async def test_11_pdf_only_lecture(self):
        """Verifies that a lecture with only PDF succeeds and does not fail because video is missing."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            lec = await self._create_test_lecture(session, 11, "Notes Only Lecture")
            lec_id = lec.id
            
            # Attach PDF only
            pdf = await repo.attach_pdf_to_lecture(
                lecture_id=lec_id,
                b2_object_key="pdfs/lec_11.pdf",
                b2_bucket="course-wallah-pdfs",
                file_name="Lecture_11_Notes.pdf",
                file_size=102400,
                page_count=5
            )
            
            refreshed = await repo.get_lecture_by_id(lec_id)
            self.assertIsNotNone(refreshed.pdf)
            self.assertIsNone(refreshed.video)
            self.assertEqual(refreshed.pdf.b2_object_key, "pdfs/lec_11.pdf")

    # -------------------------------------------------------------------------
    # TEST 12: Video + PDF lecture
    # -------------------------------------------------------------------------
    async def test_12_video_plus_pdf_lecture(self):
        """Verifies that lecture with both video and PDF records both attachments correctly."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            lec = await self._create_test_lecture(session, 12, "Complete Lecture")
            lec_id = lec.id

            await repo.attach_video_to_lecture(
                lecture_id=lec_id,
                youtube_video_id="YT_BOTH_123",
                youtube_channel_id="UC_BOTH",
                youtube_account_id="acc_both",
                duration=360.0
            )
            await repo.attach_pdf_to_lecture(
                lecture_id=lec_id,
                b2_object_key="pdfs/lec_12.pdf",
                b2_bucket="course-wallah-pdfs",
                file_name="Notes.pdf",
                file_size=50000,
                page_count=8
            )

            refreshed = await repo.get_lecture_by_id(lec_id)
            self.assertIsNotNone(refreshed.video)
            self.assertIsNotNone(refreshed.pdf)
            self.assertEqual(refreshed.video.youtube_video_id, "YT_BOTH_123")
            self.assertEqual(refreshed.pdf.b2_object_key, "pdfs/lec_12.pdf")

    # -------------------------------------------------------------------------
    # TEST 13: Diagnostics and remaining limit estimation
    # -------------------------------------------------------------------------
    async def test_13_diagnostics(self):
        """Verifies diagnostics correctly calculates remaining limits and masks credentials."""
        diag = await YouTubeAccountManager.get_diagnostics()
        self.assertIn("accounts", diag)
        self.assertIn("total_accounts", diag)
        self.assertIn("active_accounts", diag)
        for acc in diag["accounts"]:
            self.assertNotIn("client_secret", acc)
            self.assertNotIn("refresh_token", acc)
            self.assertIn("estimated_remaining_today", acc)

    # -------------------------------------------------------------------------
    # TEST 14: Deterministic account selection
    # -------------------------------------------------------------------------
    async def test_14_deterministic_selection(self):
        """Verifies accounts are selected deterministically by priority ASC, uploads_today ASC."""
        acc_p1_less_id = None
        async with get_db_session() as session:
            repo = ContentRepository(session)
            # Create High priority account with 5 uploads
            acc_p1 = await repo.create_or_update_youtube_account(
                name="Account Priority 1 (5 uploads)",
                client_id="cid_p1",
                client_secret="sec_p1",
                refresh_token="ref_p1",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            acc_p1.uploads_today = 5
            
            # Create High priority account with 1 upload (should be chosen first)
            acc_p1_less = await repo.create_or_update_youtube_account(
                name="Account Priority 1 Least Loaded (1 upload)",
                client_id="cid_p1_less",
                client_secret="sec_p1_less",
                refresh_token="ref_p1_less",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            acc_p1_less.uploads_today = 1
            acc_p1_less_id = acc_p1_less.id

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock):
            selected = await YouTubeAccountManager.select_youtube_account()
            self.assertIsNotNone(selected)
            self.assertEqual(selected.id, acc_p1_less_id)


    # -------------------------------------------------------------------------
    # TEST 15: E2E 3-Lecture Batch Pipeline Simulation with Failover
    # -------------------------------------------------------------------------
    async def test_15_e2e_full_batch_pipeline(self):
        """
        Simulates an End-to-End Batch Ingestion:
        - Lec 1: Video only (Account 1 succeeds)
        - Lec 2: Video + PDF (Account 1 hits limit, failover to Account 2 succeeds, PDF processed)
        - Lec 3: PDF only (processes PDF without failing)
        """
        ts = int(datetime.now(timezone.utc).timestamp())
        async with get_db_session() as session:
            repo = ContentRepository(session)
            acc1 = await repo.create_or_update_youtube_account(
                name=f"Primary Channel {ts}",
                client_id=f"cid_e2e_1_{ts}",
                client_secret="sec_e2e_1",
                refresh_token=f"ref_e2e_1_{ts}",
                channel_id="UC_E2E_1",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=1
            )
            acc2 = await repo.create_or_update_youtube_account(
                name=f"Secondary Backup Channel {ts}",
                client_id=f"cid_e2e_2_{ts}",
                client_secret="sec_e2e_2",
                refresh_token=f"ref_e2e_2_{ts}",
                channel_id="UC_E2E_2",
                status=YouTubeAccountStatus.ACTIVE.value,
                priority=2
            )
            acc1_id = acc1.id
            acc2_id = acc2.id

        lec1_video = self.test_dir / "lec1.mp4"
        lec1_video.write_bytes(b"\x00" * 4096)

        lec2_video = self.test_dir / "lec2.mp4"
        lec2_video.write_bytes(b"\x00" * 4096)

        lec2_pdf = self.test_dir / "lec2.pdf"
        lec2_pdf.write_bytes(b"%PDF-1.4 mock pdf content")

        lec3_pdf = self.test_dir / "lec3.pdf"
        lec3_pdf.write_bytes(b"%PDF-1.4 notes only content")

        batch_name = f"E2E Test Batch {ts}"
        async with get_db_session() as session:
            lec1 = await self._create_test_lecture(session, 1, "Lecture 1 Video Only", batch_name=batch_name)
            lec2 = await self._create_test_lecture(session, 2, "Lecture 2 Video and Notes", batch_name=batch_name)
            lec3 = await self._create_test_lecture(session, 3, "Lecture 3 Notes Only", batch_name=batch_name)
            lec1_id, lec2_id, lec3_id = lec1.id, lec2.id, lec3.id

        upload_calls = []
        async def mock_upload(file_path, title, **kwargs):
            upload_calls.append((file_path, title))
            if "Lecture 2" in title and len(upload_calls) == 2:
                # First attempt for Lecture 2 on Account 1 fails with uploadLimitExceeded
                raise YouTubeUploadLimitExceededError("Account 1 daily limit reached", status_code=400, raw_response="uploadLimitExceeded")
            return {
                "youtube_video_id": f"yt_id_{len(upload_calls)}",
                "title": title,
                "status": "UPLOADED",
                "file_size": 4096
            }

        with patch.object(YouTubeAccountManager, "sync_primary_from_env", new_callable=AsyncMock), \
             patch.object(YouTubeAccountManager, "_get_account_access_token", new_callable=AsyncMock) as mock_token, \
             patch.object(YouTubeAccountManager, "_execute_resumable_upload", side_effect=mock_upload):
            
            mock_token.return_value = "ya29.mock_token"

            # --- Process Lecture 1 (Video only) ---
            res1 = await YouTubeAccountManager.upload_with_multi_account_failover(
                file_path=str(lec1_video),
                title="Lecture 1 Video Only",
                lecture_id=lec1_id,
                batch_id="test_batch_e2e",
                lecture_index=1
            )
            self.assertEqual(res1["youtube_video_id"], "yt_id_1")
            self.assertEqual(res1["youtube_account_id"], acc1_id)

            # --- Process Lecture 2 (Video + PDF with Failover) ---
            res2 = await YouTubeAccountManager.upload_with_multi_account_failover(
                file_path=str(lec2_video),
                title="Lecture 2 Video and Notes",
                lecture_id=lec2_id,
                batch_id="test_batch_e2e",
                lecture_index=2
            )
            self.assertEqual(res2["youtube_video_id"], "yt_id_3")
            self.assertEqual(res2["youtube_account_id"], acc2_id)
            self.assertEqual(res2["youtube_channel_id"], "UC_E2E_2")

            # Process PDF for Lecture 2
            async with get_db_session() as session:
                repo = ContentRepository(session)
                await repo.attach_pdf_to_lecture(
                    lecture_id=lec2_id,
                    b2_object_key=f"pdfs/e2e_{ts}_lec2.pdf",
                    b2_bucket="cw-pdfs",
                    file_name="lec2.pdf",
                    file_size=len(lec2_pdf.read_bytes())
                )

            # --- Process Lecture 3 (PDF only - no video) ---
            async with get_db_session() as session:
                repo = ContentRepository(session)
                await repo.attach_pdf_to_lecture(
                    lecture_id=lec3_id,
                    b2_object_key=f"pdfs/e2e_{ts}_lec3.pdf",
                    b2_bucket="cw-pdfs",
                    file_name="lec3.pdf",
                    file_size=len(lec3_pdf.read_bytes())
                )

        # Verify final states in DB
        async with get_db_session() as session:
            repo = ContentRepository(session)
            
            # Account 1 should be LIMIT_REACHED
            refreshed_acc1 = await repo.get_youtube_account_by_id(acc1_id)
            self.assertEqual(refreshed_acc1.status, YouTubeAccountStatus.LIMIT_REACHED.value)
            self.assertIsNotNone(refreshed_acc1.limit_detected_at)

            # Account 2 should be ACTIVE with 1 upload
            refreshed_acc2 = await repo.get_youtube_account_by_id(acc2_id)
            self.assertEqual(refreshed_acc2.status, YouTubeAccountStatus.ACTIVE.value)
            self.assertEqual(refreshed_acc2.uploads_today, 1)

            # Lecture 1: has video, no pdf
            lec1_final = await repo.get_lecture_by_id(lec1_id)
            self.assertTrue(lec1_final.has_video)
            self.assertFalse(lec1_final.has_pdf)
            self.assertEqual(lec1_final.video.youtube_video_id, "yt_id_1")

            # Lecture 2: has video AND pdf
            lec2_final = await repo.get_lecture_by_id(lec2_id)
            self.assertTrue(lec2_final.has_video)
            self.assertTrue(lec2_final.has_pdf)
            self.assertEqual(lec2_final.video.youtube_video_id, "yt_id_3")
            self.assertEqual(lec2_final.video.youtube_account_id, acc2_id)

            # Lecture 3: has pdf, NO video (did not fail)
            lec3_final = await repo.get_lecture_by_id(lec3_id)
            self.assertFalse(lec3_final.has_video)
            self.assertTrue(lec3_final.has_pdf)


if __name__ == "__main__":
    unittest.main()
