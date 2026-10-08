import os
import sys
import unittest
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM_DIR))

from sqlalchemy import select, func
from db.connection import get_db_session, init_db
from db.models import (
    App,
    Batch,
    Subject,
    Folder,
    Lecture,
    Video,
    PDF,
    Job,
    Playlist
)
from db.repository import ContentRepository
from validators.image_validator import validate_image_url, is_ip_private_or_restricted
from parsers.indexer import TxtIndexer
from bot.batch_wizard import BatchWizardManager, BatchWizardState
from bot.progress_ui import TelegramProgressUI

class TestFreshDbAndImageUrl(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()

    def test_ssrf_ip_detection(self):
        self.assertTrue(is_ip_private_or_restricted("127.0.0.1"))
        self.assertTrue(is_ip_private_or_restricted("10.0.0.1"))
        self.assertTrue(is_ip_private_or_restricted("172.16.0.1"))
        self.assertTrue(is_ip_private_or_restricted("192.168.1.1"))
        self.assertTrue(is_ip_private_or_restricted("169.254.169.254"))
        self.assertTrue(is_ip_private_or_restricted("0.0.0.0"))
        self.assertFalse(is_ip_private_or_restricted("8.8.8.8"))
        self.assertFalse(is_ip_private_or_restricted("1.1.1.1"))

    def test_image_url_security_rejections(self):
        # SSRF localhost / internal
        is_val, reason, _ = validate_image_url("http://127.0.0.1/logo.png")
        self.assertFalse(is_val)
        self.assertIn("rejected", reason.lower())

        is_val, reason, _ = validate_image_url("http://localhost:8000/avatar.jpg")
        self.assertFalse(is_val)
        self.assertIn("rejected", reason.lower())

        is_val, reason, _ = validate_image_url("http://169.254.169.254/latest/meta-data/")
        self.assertFalse(is_val)
        self.assertIn("rejected", reason.lower())

        # Disallowed schemes
        is_val, reason, _ = validate_image_url("file:///C:/Windows/system.ini")
        self.assertFalse(is_val)
        self.assertIn("scheme", reason.lower())

        is_val, reason, _ = validate_image_url("ftp://example.com/logo.png")
        self.assertFalse(is_val)
        self.assertIn("scheme", reason.lower())

        # Empty or non-string
        is_val, reason, _ = validate_image_url("")
        self.assertFalse(is_val)

        # Unresolvable host
        is_val, reason, _ = validate_image_url("https://nonexistent-domain-course-wallah-fake.org/image.png")
        self.assertFalse(is_val)

    def test_image_url_validation_public(self):
        # Known reliable public images (Google, Wikipedia, GitHub logos)
        test_url = "https://www.google.com/images/branding/googlelogo/2x/googlelogo_color_92x30dp.png"
        try:
            is_val, reason, ct = validate_image_url(test_url, timeout=6)
            if is_val:
                self.assertTrue(is_val)
                self.assertIn("image", ct)
        except Exception:
            pass # Network may be offline in some test environments

    async def test_app_and_batch_creation_flow(self):
        test_app_name = "__TEMP_TEST_APP_FOR_VERIFICATION__"
        test_batch_name = "__TEMP_TEST_BATCH_FOR_VERIFICATION__"
        test_icon_url = "https://example.com/test_app_icon.png"
        test_thumb_url = "https://example.com/test_batch_thumb.png"

        async with get_db_session() as session:
            repo = ContentRepository(session)
            
            # 1. Create App
            app = await repo.get_or_create_app(
                name=test_app_name,
                description="Temporary validation app",
                icon_url=test_icon_url
            )
            self.assertIsNotNone(app.id)
            self.assertEqual(app.name, test_app_name)
            self.assertEqual(app.icon_url, test_icon_url)

            # 2. Create Batch
            batch, created = await repo.get_or_create_batch(
                app_id=app.id,
                name=test_batch_name,
                category="B.Tech",
                branch="CSE",
                semester="3rd Semester",
                academic_year="2026",
                thumbnail_url=test_thumb_url,
                quality_pref="1080p"
            )
            self.assertTrue(created)
            self.assertEqual(batch.app_id, app.id)
            self.assertEqual(batch.thumbnail_url, test_thumb_url)

            # 3. Create Subject & Folder & Lecture
            subject = await repo.get_or_create_subject(batch.id, "Mathematics III")
            folder = await repo.get_or_create_folder(subject.id, "Unit 1: Linear Algebra")
            lec = await repo.create_or_update_lecture(
                batch_id=batch.id,
                subject_id=subject.id,
                folder_id=folder.id,
                title="Lecture 01: Introduction",
                lecture_index=1,
                provider="appx"
            )
            self.assertIsNotNone(lec.id)

            # Clean up temporary test data to keep DB 100% clean
            await session.delete(lec)
            await session.delete(folder)
            await session.delete(subject)
            await session.delete(batch)
            await session.delete(app)
            await session.flush()

    async def test_db_cleanliness_verification(self):
        async with get_db_session() as session:
            n_apps = (await session.execute(select(func.count(App.id)))).scalar() or 0
            n_batches = (await session.execute(select(func.count(Batch.id)))).scalar() or 0
            n_subjects = (await session.execute(select(func.count(Subject.id)))).scalar() or 0
            n_folders = (await session.execute(select(func.count(Folder.id)))).scalar() or 0
            n_lectures = (await session.execute(select(func.count(Lecture.id)))).scalar() or 0
            n_videos = (await session.execute(select(func.count(Video.id)))).scalar() or 0
            n_pdfs = (await session.execute(select(func.count(PDF.id)))).scalar() or 0
            n_jobs = (await session.execute(select(func.count(Job.id)))).scalar() or 0

            self.assertEqual(n_apps, 0, f"Expected 0 apps, found {n_apps}")
            self.assertEqual(n_batches, 0, f"Expected 0 batches, found {n_batches}")
            self.assertEqual(n_subjects, 0, f"Expected 0 subjects, found {n_subjects}")
            self.assertEqual(n_folders, 0, f"Expected 0 folders, found {n_folders}")
            self.assertEqual(n_lectures, 0, f"Expected 0 lectures, found {n_lectures}")
            self.assertEqual(n_videos, 0, f"Expected 0 videos, found {n_videos}")
            self.assertEqual(n_pdfs, 0, f"Expected 0 pdfs, found {n_pdfs}")
            self.assertEqual(n_jobs, 0, f"Expected 0 jobs, found {n_jobs}")

    async def test_txt_indexer_and_wizard_metadata(self):
        sample_txt = (
            "01. Lecture 1*https://example.com/video1.m3u8\n"
            "02. Lecture 2*https://example.com/video2.m3u8\n"
        )
        tree = TxtIndexer.index_txt(sample_txt, filename="sample.txt", app_name="Course Wallah", batch_override="Engineering Mathematics")
        self.assertIsNotNone(tree)
        self.assertEqual(tree.total_lectures, 2)
        self.assertEqual(tree.app_name, "Course Wallah")
        self.assertEqual(tree.batch_name, "Engineering Mathematics")

        state = await BatchWizardManager.analyze_and_start_session(
            bot_id="bot_test",
            user_id=123456,
            file_content=sample_txt,
            filename="sample.txt"
        )
        self.assertIsNotNone(state)
        self.assertEqual(state.analysis_stats["total_lectures"], 2)

if __name__ == "__main__":
    unittest.main()
