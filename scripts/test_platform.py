import sys
import os
import asyncio
import unittest
from pathlib import Path
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from db.connection import init_db, get_db_session, engine
from db.repository import ContentRepository, slugify
from db.models import Base, JobStatus, PublicationStatus, Lecture, Batch, App, Video, PDF, Subject, Folder
from parsers.indexer import TxtIndexer, NormalizedBatchTree
from parsers.academic_parser import parse_course_txt
from parsers.bracket_topic_parser import is_bracket_topic_format
from parsers.structured_batch_parser import detect_txt_format
from providers.router import MediaRouter, MediaType, parse_pdf_input
from engines.watermark import WatermarkEngine
from engines.video_processor import VideoProcessor
from engines.youtube_uploader import YouTubeUploader
from engines.b2_storage import B2StorageManager
from engines.job_engine import ContentProcessingEngine
from api.server import app
from api.auth import create_jwt_token
from bot.progress_ui import TelegramProgressUI

class CourseWallahPlatformTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    async def asyncTearDown(self):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    async def test_01_txt_parsers_and_format_detection(self):
        """Tests format detection and tree normalization for multiple TXT structures."""
        # 1. Structured batch sample
        sample_structured = """
        BATCH DETAILS
        Batch: B.Tech CSE 3rd Semester
        ID: 1042
        Instructor: Rakesh Sir
        CONTENT:
        [Unit 01 - Digital Logic] (Logic Gates) Class 01 | Number Systems : https://example.com/stream.m3u8
        [Unit 01 - Digital Logic] (Logic Gates) Class 01 | Number Systems Notes : https://example.com/notes.pdf
        """
        fmt = detect_txt_format(sample_structured)
        self.assertIn(fmt, ("structured_batch", "legacy_appx"))

        tree = TxtIndexer.index_txt(sample_structured, filename="btech_cse.txt")
        self.assertEqual(tree.batch_name, "B.Tech CSE 3rd Semester")
        self.assertGreaterEqual(len(tree.subjects), 1)
        self.assertGreaterEqual(tree.total_lectures, 1)

        # 2. Bracket topic sample
        sample_bracket = """
        [Operating Systems] Lecture 01 - Process Management : https://example.com/video1.mp4
        [Operating Systems] Lecture 02 - Threads and Concurrency : https://example.com/video2.mp4
        """
        is_bracket = is_bracket_topic_format(sample_bracket)
        self.assertTrue(is_bracket)

        bracket_tree = TxtIndexer.index_txt(sample_bracket, filename="os_batch.txt")
        self.assertEqual(bracket_tree.total_lectures, 2)

    async def test_02_database_hierarchy_and_duplicate_protection(self):
        """Tests App -> Batch -> Subject -> Folder -> Lecture -> Playlist creation & duplicate prevention."""
        async with get_db_session() as session:
            repo = ContentRepository(session)

            app_obj = await repo.get_or_create_app("B.Tech Engineering")
            self.assertIsNotNone(app_obj.id)

            import time
            unique_batch_name = f"Test Batch {int(time.time())}"
            batch, is_new = await repo.get_or_create_batch(
                app_id=app_obj.id,
                name=unique_batch_name,
                category="Engineering",
                branch="CSE"
            )
            self.assertTrue(is_new)

            # Test duplicate batch detection
            batch_dup, is_new_dup = await repo.get_or_create_batch(
                app_id=app_obj.id,
                name=unique_batch_name
            )
            self.assertFalse(is_new_dup)
            self.assertEqual(batch.id, batch_dup.id)

            subj = await repo.get_or_create_subject(batch.id, "Digital Electronics")
            folder = await repo.get_or_create_folder(subj.id, "Unit 01 Logic", unit_number="Unit 01")

            # Create lecture #1
            lec1 = await repo.create_or_update_lecture(
                folder_id=folder.id,
                subject_id=subj.id,
                batch_id=batch.id,
                lecture_index=1,
                title="Number System",
                source_url="https://example.com/v1.mp4",
                source_pdf_url="https://example.com/n1.pdf",
                has_video=True,
                has_pdf=True
            )
            self.assertEqual(lec1.lecture_index, 1)

            # Attach media
            await repo.attach_video_to_lecture(
                lecture_id=lec1.id,
                youtube_video_id="fake_yt_id_101",
                duration=1840.5,
                resolution="1080p",
                file_size=54000000
            )

            await repo.attach_pdf_to_lecture(
                lecture_id=lec1.id,
                b2_object_key=f"courses/btech/cs3/unit1/lec1/{int(time.time())}_notes.pdf",
                b2_bucket="course-wallah-pdfs",
                file_name="notes.pdf",
                page_count=24
            )

            # Mark published
            published_lec = await repo.set_lecture_published(lec1.id)
            self.assertEqual(published_lec.publication_status, PublicationStatus.PUBLISHED)

            # Verify playlist contains lecture
            summary = await repo.get_batch_lecture_summary(batch.id)
            self.assertEqual(summary["total_lectures"], 1)
            self.assertEqual(summary["published_lectures"], 1)

            # Clean up test entities
            await session.delete(published_lec)
            await session.delete(folder)
            await session.delete(subj)
            await session.delete(batch)
            await session.delete(app_obj)
            await session.flush()

    async def test_03_watermark_engine_and_filter(self):
        """Tests that moving watermark expressions are generated properly without syntax bugs."""
        vf_drift = WatermarkEngine.build_watermark_filter(
            text="COURSE WALLAH",
            opacity=0.45,
            animation_mode="continuous_drift"
        )
        self.assertIn("drawtext", vf_drift)
        self.assertIn("COURSE WALLAH", vf_drift)
        self.assertIn("sin(", vf_drift)

        vf_bounce = WatermarkEngine.build_watermark_filter(
            text="TEST BRAND",
            animation_mode="smooth_bounce"
        )
        self.assertIn("mod(", vf_bounce)

    async def test_04_b2_storage_and_signed_urls(self):
        """Tests B2 S3 key generation and presigned URL generation."""
        key = B2StorageManager.build_object_key(
            app_slug="b-tech",
            batch_slug="cse-3rd-sem",
            folder_slug="unit-01",
            lecture_slug="001-number-system",
            filename="lecture.pdf"
        )
        self.assertEqual(key, "courses/b-tech/cse-3rd-sem/unit-01/001-number-system/lecture.pdf")

        # Test presigned URL generation
        url = B2StorageManager.generate_presigned_url(key)
        self.assertTrue(len(url) > 10)

    async def test_05_media_router_classification(self):
        """Tests independent media URL routing."""
        self.assertEqual(MediaRouter.classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), MediaType.YOUTUBE)
        self.assertEqual(MediaRouter.classify_url("https://vcdn.spayee.in/master.m3u8"), MediaType.SPAYEE_HLS)
        self.assertEqual(MediaRouter.classify_url("https://cdn.example.com/document.pdf"), MediaType.DIRECT_PDF)
        self.assertEqual(MediaRouter.classify_url("https://cdn.example.com/lecture.mp4"), MediaType.DIRECT_VIDEO)

    async def test_06_fastapi_rest_endpoints(self):
        """Tests REST API endpoints for apps, batches, lectures, pdfs, search, and admin."""
        # Create a temporary fixture
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app_obj = await repo.get_or_create_app("Test API App")
            batch_obj, _ = await repo.get_or_create_batch(app_obj.id, "Test API Batch")
            subj = await repo.get_or_create_subject(batch_obj.id, "Test Subject")
            folder = await repo.get_or_create_folder(subj.id, "Test Unit")
            lec = await repo.create_or_update_lecture(
                batch_id=batch_obj.id,
                subject_id=subj.id,
                folder_id=folder.id,
                title="GATE Question Solving",
                lecture_index=1,
                has_video=True
            )
            await repo.set_lecture_published(lec.id)
            test_lec_id = lec.id
            test_app_id = app_obj.id
            test_batch_id = batch_obj.id
            test_folder_id = folder.id
            test_subj_id = subj.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Health check
            resp_health = await ac.get("/health")
            self.assertEqual(resp_health.status_code, 200)

            # 2. List apps
            resp_apps = await ac.get("/api/v1/apps")
            self.assertEqual(resp_apps.status_code, 200)
            apps_data = resp_apps.json()
            self.assertIsInstance(apps_data, list)

            # 3. Search
            resp_search = await ac.get("/api/v1/search?q=GATE")
            self.assertEqual(resp_search.status_code, 200)
            search_data = resp_search.json()
            self.assertIn("results_count", search_data)
            self.assertIn("lectures", search_data)

            # 4. Admin Login & Stats
            admin_token = create_jwt_token({"sub": "admin", "role": "ADMIN"})
            resp_stats = await ac.get(
                "/api/v1/admin/stats",
                headers={"Authorization": f"Bearer {admin_token}"}
            )
            self.assertEqual(resp_stats.status_code, 200)
            stats_data = resp_stats.json()
            self.assertIn("apps", stats_data)
            self.assertIn("lectures", stats_data)

        # Cleanup fixture
        async with get_db_session() as session:
            repo = ContentRepository(session)
            l = await repo.get_lecture_by_id(test_lec_id)
            if l: await session.delete(l)
            f = await session.get(Folder, test_folder_id)
            if f: await session.delete(f)
            s = await session.get(Subject, test_subj_id)
            if s: await session.delete(s)
            b = await repo.get_batch_by_id(test_batch_id)
            if b: await session.delete(b)
            a = await repo.get_app_by_id(test_app_id)
            if a: await session.delete(a)
            await session.flush()

    async def test_07_telegram_progress_card_rendering(self):
        """Tests single-message live Telegram progress card formatting."""
        card = TelegramProgressUI.format_live_card(
            batch_name="B.Tech CSE 3rd Semester",
            folder_name="Unit 01 Logic",
            lecture_index=148,
            lecture_title="Number System",
            total_lectures=200,
            completed_count=147,
            download_pct=72.0,
            download_status="Downloading",
            watermark_pct=61.0,
            watermark_status="Processing",
            thumbnail_ready=True,
            youtube_pct=31.0,
            youtube_status="Uploading",
            youtube_video_id="test_yt_id",
            has_pdf=True,
            pdf_pct=100.0,
            pdf_status="Complete ✅",
            b2_pct=100.0,
            b2_status="Uploaded ✅",
            db_status="100% ✅",
            playlist_status="Adding lecture #148...",
            failed_count=0
        )
        self.assertIn("COURSE WALLAH", card)
        self.assertIn("147 / 200 completed", card)
        self.assertIn("Number System", card)

    async def test_08_real_production_content_preservation(self):
        """Verifies end-to-end lecture details and access routing."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app_obj = await repo.get_or_create_app("Course Wallah Verification")
            batch_obj, _ = await repo.get_or_create_batch(app_obj.id, "Verification Batch")
            subj = await repo.get_or_create_subject(batch_obj.id, "Linear Algebra")
            folder = await repo.get_or_create_folder(subj.id, "Unit 1")
            lec = await repo.create_or_update_lecture(
                batch_id=batch_obj.id,
                subject_id=subj.id,
                folder_id=folder.id,
                title="4F. GATE 2017 Question",
                lecture_index=1,
                has_video=True,
                has_pdf=True
            )
            await repo.attach_video_to_lecture(lec.id, youtube_video_id="6ZhabLKu65E", duration=120.0)
            await repo.attach_pdf_to_lecture(lec.id, b2_object_key="courses/test.pdf", b2_bucket="course-wallah-pdfs", file_name="test.pdf")
            await repo.set_lecture_published(lec.id)
            test_lec_id = lec.id
            test_app_id = app_obj.id
            test_batch_id = batch_obj.id
            test_folder_id = folder.id
            test_subj_id = subj.id

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Check batch
            resp_batch = await ac.get(f"/api/v1/batches/{batch_obj.slug}")
            self.assertEqual(resp_batch.status_code, 200)
            batch_data = resp_batch.json()
            self.assertEqual(batch_data["name"], "Verification Batch")

            # Verify lecture details endpoint
            lec_resp = await ac.get(f"/api/v1/lectures/{test_lec_id}")
            self.assertEqual(lec_resp.status_code, 200)
            lec_data = lec_resp.json()
            self.assertEqual(lec_data["app_name"], "Course Wallah Verification")

            # Verify playback access
            acc_resp = await ac.get(f"/api/v1/lectures/{test_lec_id}/access")
            self.assertEqual(acc_resp.status_code, 200)
            acc_data = acc_resp.json()
            self.assertTrue(acc_data["has_video"])
            self.assertEqual(acc_data["youtube_video_id"], "6ZhabLKu65E")

            # Verify PDF access
            pdf_resp = await ac.get(f"/api/v1/pdfs/{test_lec_id}/access")
            self.assertEqual(pdf_resp.status_code, 200)

        # Cleanup fixture
        async with get_db_session() as session:
            repo = ContentRepository(session)
            l = await repo.get_lecture_by_id(test_lec_id)
            if l: await session.delete(l)
            f = await session.get(Folder, test_folder_id)
            if f: await session.delete(f)
            s = await session.get(Subject, test_subj_id)
            if s: await session.delete(s)
            b = await repo.get_batch_by_id(test_batch_id)
            if b: await session.delete(b)
            a = await repo.get_app_by_id(test_app_id)
            if a: await session.delete(a)
            await session.flush()

    async def test_09_temporary_video_cleanup_architecture(self):
        """Verifies that no permanent local video archive is created and working temp directories are clean."""
        downloads_dir = Path("downloads")
        temp_dir = Path("temp")
        
        # Ensure directories exist
        downloads_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Verify no permanent leftover mp4 files are accumulating in downloads or temp
        mp4_files = list(downloads_dir.glob("*.mp4")) + list(temp_dir.glob("*.mp4"))
        self.assertEqual(len(mp4_files), 0, "No permanent video files should remain in local storage after processing.")

if __name__ == "__main__":
    unittest.main()
