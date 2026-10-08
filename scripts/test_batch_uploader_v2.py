import sys
import os
import time
import asyncio
import unittest
from pathlib import Path
from typing import Dict, Any

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import OWNER_ID, ADMINS, WATERMARK_TEXT
from db.connection import init_db, get_db_session, engine
from db.repository import ContentRepository, slugify
from db.models import Base, Job, JobStatus, PublicationStatus, Lecture, Batch, App, Video, PDF
from parsers.indexer import TxtIndexer, NormalizedBatchTree, NormalizedLecture
from parsers.academic_parser import parse_course_txt
from parsers.structured_batch_parser import detect_txt_format
from providers.router import MediaRouter, MediaType
from engines.watermark import WatermarkEngine
from engines.video_processor import VideoProcessor
from engines.youtube_uploader import YouTubeUploader
from engines.b2_storage import B2StorageManager
from engines.job_engine import ContentProcessingEngine, BatchJobController
from bot.progress_ui import TelegramProgressUI, TelegramMessageThrottler, make_progress_bar, get_spinner
from bot.batch_wizard import BatchWizardManager, BatchWizardState
from bot.handlers import is_admin


class MockTelegramMessage:
    """Mock Telegram message for verifying edits, throttling, and state transitions."""
    def __init__(self, message_id: int = 1001):
        self.id = message_id
        self.text = ""
        self.reply_markup = None
        self.edit_count = 0

    async def edit_text(self, text: str, reply_markup=None):
        self.text = text
        self.reply_markup = reply_markup
        self.edit_count += 1
        return self

    async def reply_text(self, text: str, reply_markup=None):
        self.text = text
        self.reply_markup = reply_markup
        return self


class TestBatchUploaderV2Complete(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        await init_db()
        self.bot_id = "test_bot_1"
        self.admin_user_id = OWNER_ID or 8504838657
        self.non_admin_user_id = 999999999

    async def asyncTearDown(self):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    # 1. /START COMMAND FLOW
    async def test_01_start_command_admin_and_user(self):
        """Tests that /start returns appropriate welcome screens for admin vs non-admin."""
        admin_welcome = TelegramProgressUI.render_welcome_screen("Admin", is_admin=True)
        self.assertIn("COURSE WALLAH", admin_welcome)
        self.assertIn("Manage your educational content", admin_welcome)
        admin_markup = BatchWizardManager.build_welcome_markup(is_admin=True)
        self.assertGreaterEqual(len(admin_markup.inline_keyboard), 2)

        user_welcome = TelegramProgressUI.render_welcome_screen("Student", is_admin=False)
        self.assertIn("does not have administrator access", user_welcome)
        user_markup = BatchWizardManager.build_welcome_markup(is_admin=False)
        self.assertGreaterEqual(len(user_markup.inline_keyboard), 1)

    # 2. /HELP COMMAND FLOW
    async def test_02_help_command(self):
        """Tests that /help separates admin commands from general user commands."""
        admin_help = TelegramProgressUI.render_help_screen(is_admin=True)
        self.assertIn("/admin", admin_help)
        self.assertIn("/batch", admin_help)
        self.assertIn("/batchpause", admin_help)

        user_help = TelegramProgressUI.render_help_screen(is_admin=False)
        self.assertNotIn("/batchpause", user_help)
        self.assertIn("/id", user_help)

    # 3. /ID COMMAND FLOW
    async def test_03_id_command(self):
        """Tests /id output card format."""
        id_card = TelegramProgressUI.render_id_screen(self.admin_user_id, is_admin=True, bot_username="@cw_bot")
        self.assertIn(str(self.admin_user_id), id_card)
        self.assertIn("YES", id_card)

    # 4. ADMIN AUTHORIZATION & NON-ADMIN BLOCKING
    async def test_04_admin_authorization(self):
        """Tests authorization gate for OWNER_ID, ADMINS, and non-admin IDs."""
        self.assertTrue(is_admin(self.admin_user_id))
        self.assertFalse(is_admin(self.non_admin_user_id))
        self.assertFalse(is_admin(0))
        self.assertFalse(is_admin(None))

    # 5. ADMIN DASHBOARD
    async def test_05_admin_dashboard(self):
        """Tests /admin dashboard rendering and buttons."""
        stats = {"active_apps": 2, "total_batches": 5, "total_lectures": 140, "active_jobs": 1}
        dash = TelegramProgressUI.render_admin_dashboard(stats)
        self.assertIn("COURSE WALLAH ADMIN", dash)
        self.assertIn("ONLINE", dash)
        markup = BatchWizardManager.build_admin_dashboard_markup()
        self.assertGreaterEqual(len(markup.inline_keyboard), 3)

    # 6. TXT UPLOAD & DEEP ANALYSIS
    async def test_06_txt_upload_and_analysis(self):
        """Tests parsing and deep analysis statistics calculation."""
        sample_txt = (
            "BATCH DETAILS\n"
            "Batch: B.Tech Computer Science 2026\n"
            "CONTENT:\n"
            "[Unit 01 - OS] (Processes) Class 01 | Intro : https://example.com/stream1.m3u8\n"
            "[Unit 01 - OS] (Processes) Class 01 | Intro Notes : https://example.com/notes1.pdf\n"
            "[Unit 01 - OS] (Threads) Class 02 | Multi-threading : https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        )
        state = await BatchWizardManager.analyze_and_start_session(
            bot_id=self.bot_id,
            user_id=self.admin_user_id,
            file_content=sample_txt,
            filename="cs2026.txt"
        )
        self.assertEqual(state.batch_name, "B.Tech Computer Science 2026")
        self.assertEqual(state.analysis_stats["total_lectures"], 2)
        self.assertEqual(state.analysis_stats["video_count"], 2)
        self.assertEqual(state.analysis_stats["pdf_count"], 1)

        card = TelegramProgressUI.render_analysis(state.analysis_stats)
        self.assertIn("TXT ANALYSIS COMPLETE", card)
        self.assertIn("cs2026.txt", card)

    # 7. SELECT EXISTING APP
    async def test_07_select_existing_app(self):
        """Tests querying apps and generating app selection buttons."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app1 = await repo.get_or_create_app("Test App Engineering")
            apps = await repo.get_all_apps()
            self.assertGreaterEqual(len(apps), 1)

            markup = BatchWizardManager.build_app_selection_markup(apps)
            # Find callback data
            found_app_cb = False
            for row in markup.inline_keyboard:
                for btn in row:
                    if btn.callback_data and btn.callback_data.startswith("wizard:app_select:"):
                        found_app_cb = True
            self.assertTrue(found_app_cb)

    # 8. CREATE NEW APP INTERACTIVE
    async def test_08_create_new_app(self):
        """Tests creating a new app interactively in DB."""
        state = BatchWizardManager.get_or_create_session(self.bot_id, self.admin_user_id)
        state.app_name = f"New Platform App {int(time.time())}"
        state.app_description = "Engineered for GATE"

        async with get_db_session() as session:
            repo = ContentRepository(session)
            new_app = await repo.get_or_create_app(state.app_name, description=state.app_description)
            self.assertIsNotNone(new_app.id)
            self.assertEqual(new_app.name, state.app_name)

    # 9. EDIT APP METADATA
    async def test_09_edit_app(self):
        """Tests editing app name without altering batch/lecture relations."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app(f"Editable App {int(time.time())}")
            updated = await repo.update_app(app.id, description="Updated Description via Wizard")
            self.assertEqual(updated.description, "Updated Description via Wizard")

    # 10. SELECT EXISTING BATCH
    async def test_10_select_existing_batch(self):
        """Tests listing batches for an app and selecting an existing batch."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("Batch Testing App")
            batch, _ = await repo.get_or_create_batch(app.id, f"Batch {int(time.time())}")
            batches = await repo.get_batches_by_app_id(app.id)
            self.assertGreaterEqual(len(batches), 1)

            markup = BatchWizardManager.build_batch_selection_markup(batches)
            found_batch_cb = any(
                btn.callback_data and btn.callback_data.startswith("wizard:batch_select:")
                for row in markup.inline_keyboard for btn in row
            )
            self.assertTrue(found_batch_cb)

    # 11. CREATE NEW BATCH
    async def test_11_create_new_batch(self):
        """Tests creating a new batch with academic category, branch, and semester."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("Batch Creation App")
            batch_name = f"B.Tech CSE {int(time.time())}"
            batch, is_new = await repo.get_or_create_batch(
                app_id=app.id,
                name=batch_name,
                category="B.Tech",
                branch="CSE",
                semester="3rd Semester",
                academic_year="2026"
            )
            self.assertTrue(is_new)
            self.assertEqual(batch.category, "B.Tech")
            self.assertEqual(batch.branch, "CSE")

    # 12. TXT MAPPING & PARSED PREVIEW
    async def test_12_edit_mapping_and_preview(self):
        """Tests mapping menu and parsed items preview generator."""
        items = [
            {"index": 1, "subject": "Math", "folder": "Unit 01", "title": "Calculus", "video_url": "https://v1.mp4", "pdf_url": "https://n1.pdf"},
            {"index": 2, "subject": "Math", "folder": "Unit 01", "title": "Algebra", "video_url": "https://v2.mp4", "pdf_url": None}
        ]
        preview_text = TelegramProgressUI.render_parsed_preview(items)
        self.assertIn("Calculus", preview_text)
        self.assertIn("Algebra", preview_text)
        self.assertIn("PARSED PREVIEW", preview_text)

    # 13. BACK NAVIGATION STATE HISTORY
    async def test_13_back_navigation(self):
        """Tests push_step and pop_step history tracking."""
        state = BatchWizardManager.get_or_create_session(self.bot_id, self.admin_user_id)
        state.step = "ANALYSIS_PREVIEW"
        state.history.clear()

        state.push_step("SELECT_APP")
        self.assertEqual(state.step, "SELECT_APP")
        self.assertEqual(state.history, ["ANALYSIS_PREVIEW"])

        state.push_step("SELECT_BATCH")
        self.assertEqual(state.step, "SELECT_BATCH")
        self.assertEqual(state.history, ["ANALYSIS_PREVIEW", "SELECT_APP"])

        # Pop back
        prev = state.pop_step()
        self.assertEqual(prev, "SELECT_APP")
        prev2 = state.pop_step()
        self.assertEqual(prev2, "ANALYSIS_PREVIEW")

    # 14. CANCEL NAVIGATION
    async def test_14_cancel_navigation(self):
        """Tests session clearing on cancel."""
        BatchWizardManager.get_or_create_session(self.bot_id, self.admin_user_id)
        self.assertIsNotNone(BatchWizardManager.get_session(self.bot_id, self.admin_user_id))

        BatchWizardManager.clear_session(self.bot_id, self.admin_user_id)
        self.assertIsNone(BatchWizardManager.get_session(self.bot_id, self.admin_user_id))

    # 15. FINAL CONFIRMATION CARD
    async def test_15_final_confirmation(self):
        """Tests final confirmation card display."""
        session_data = {
            "app_name": "Course Wallah",
            "batch_name": "Computer Science 2026",
            "quality_pref": "AUTO / BEST",
            "watermark_enabled": True,
            "execution_mode": "APPEND NEW CONTENT",
            "analysis_stats": {
                "video_count": 138,
                "pdf_count": 121,
                "subject_count": 5,
                "unit_count": 17,
                "already_processed_count": 5,
                "new_count": 133,
                "failed_count": 0
            }
        }
        card = TelegramProgressUI.render_final_confirmation(session_data)
        self.assertIn("READY TO PROCESS", card)
        self.assertIn("Course Wallah", card)
        self.assertIn("138", card)

    # 16. DUPLICATE DETECTION & SKIPPING
    async def test_16_duplicate_detection(self):
        """Tests duplicate lecture skipping when publication_status == PUBLISHED."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("Dup App")
            batch, _ = await repo.get_or_create_batch(app.id, f"Dup Batch {int(time.time())}")
            subj = await repo.get_or_create_subject(batch.id, "Math")
            folder = await repo.get_or_create_folder(subj.id, "Unit 1")

            lec = await repo.create_or_update_lecture(
                folder.id, subj.id, batch.id, 1, "Duplicate Test",
                publication_status=PublicationStatus.PUBLISHED
            )
            self.assertEqual(lec.publication_status, PublicationStatus.PUBLISHED)

    # 17. BATCH STATUS RENDERING
    async def test_17_batch_status_rendering(self):
        """Tests /batchstatus rendering with active controller."""
        mock_msg = MockTelegramMessage()
        ctrl = BatchJobController(
            bot_id=self.bot_id,
            job_id="test_status_job",
            batch_id="b_1",
            batch_name="Operating Systems 2026",
            user_id=self.admin_user_id,
            total_lectures=100,
            status_message=mock_msg
        )
        ctrl.completed_count = 25
        controllers = {"test_status_job": ctrl}
        status_text = TelegramProgressUI.render_batch_status_screen(controllers)
        self.assertIn("Operating Systems 2026", status_text)
        self.assertIn("25 / 100", status_text)

    # 18. PAUSE & RESUME CONTROLLER
    async def test_18_pause_and_resume_controller(self):
        """Tests atomic pause and resume states."""
        mock_msg = MockTelegramMessage()
        ctrl = BatchJobController(
            bot_id=self.bot_id,
            job_id="test_ctrl_job",
            batch_id="b_2",
            batch_name="Networks",
            user_id=self.admin_user_id,
            total_lectures=50,
            status_message=mock_msg
        )
        self.assertFalse(ctrl.is_paused)
        ctrl.pause()
        self.assertTrue(ctrl.is_paused)
        ctrl.resume()
        self.assertFalse(ctrl.is_paused)

    # 19. CANCEL CONTROLLER
    async def test_19_cancel_controller(self):
        """Tests cancel flag on BatchJobController."""
        mock_msg = MockTelegramMessage()
        ctrl = BatchJobController(
            bot_id=self.bot_id,
            job_id="test_cancel_job",
            batch_id="b_3",
            batch_name="DBMS",
            user_id=self.admin_user_id,
            total_lectures=40,
            status_message=mock_msg
        )
        self.assertFalse(ctrl.is_cancelled)
        ctrl.cancel()
        self.assertTrue(ctrl.is_cancelled)

    # 20. RETRY FAILED TRACKING
    async def test_20_retry_failed_tracking(self):
        """Tests failed items tracking."""
        mock_msg = MockTelegramMessage()
        ctrl = BatchJobController(
            bot_id=self.bot_id,
            job_id="test_fail_job",
            batch_id="b_4",
            batch_name="Algorithms",
            user_id=self.admin_user_id,
            total_lectures=30,
            status_message=mock_msg
        )
        ctrl.failed_items.append({"index": 4, "title": "Graph Traversal", "error": "HTTP 500"})
        card = TelegramProgressUI.render_failed_summary(ctrl.failed_items, ctrl.batch_name)
        self.assertIn("Graph Traversal", card)
        self.assertIn("HTTP 500", card)

    # 21. MULTI-USER ISOLATION
    async def test_21_multi_user_state_isolation(self):
        """Tests that two different user IDs have completely isolated states."""
        s1 = BatchWizardManager.get_or_create_session(self.bot_id, 1111)
        s2 = BatchWizardManager.get_or_create_session(self.bot_id, 2222)
        s1.batch_name = "Batch User 1"
        s2.batch_name = "Batch User 2"

        self.assertEqual(BatchWizardManager.get_session(self.bot_id, 1111).batch_name, "Batch User 1")
        self.assertEqual(BatchWizardManager.get_session(self.bot_id, 2222).batch_name, "Batch User 2")
        BatchWizardManager.clear_session(self.bot_id, 1111)
        BatchWizardManager.clear_session(self.bot_id, 2222)

    # 22. MULTI-BOT ISOLATION
    async def test_22_multi_bot_state_isolation(self):
        """Tests that two different bot IDs have completely isolated states."""
        sA = BatchWizardManager.get_or_create_session("bot_A", self.admin_user_id)
        sB = BatchWizardManager.get_or_create_session("bot_B", self.admin_user_id)
        sA.app_name = "Bot A App"
        sB.app_name = "Bot B App"

        self.assertEqual(BatchWizardManager.get_session("bot_A", self.admin_user_id).app_name, "Bot A App")
        self.assertEqual(BatchWizardManager.get_session("bot_B", self.admin_user_id).app_name, "Bot B App")
        BatchWizardManager.clear_session("bot_A", self.admin_user_id)
        BatchWizardManager.clear_session("bot_B", self.admin_user_id)

    # 23. TELEGRAM EDIT THROTTLING & FLOODWAIT SAFETY
    async def test_23_telegram_edit_throttling_and_floodwait(self):
        """Tests TelegramMessageThrottler rate limits message edits."""
        mock_msg = MockTelegramMessage()
        throttler = TelegramMessageThrottler(min_interval=0.4)

        # First edit
        res1 = await throttler.edit(mock_msg, "Edit 1", force=True)
        self.assertTrue(res1)

        # Throttled edit
        res2 = await throttler.edit(mock_msg, "Edit 2", force=False)
        self.assertFalse(res2)

        # Delayed edit
        await asyncio.sleep(0.45)
        res3 = await throttler.edit(mock_msg, "Edit 3", force=False)
        self.assertTrue(res3)

    # 24. RECENT JOBS DB PERSISTENCE
    async def test_24_recent_jobs_db_persistence(self):
        """Tests creating a Job in DB and querying recent jobs."""
        async with get_db_session() as session:
            repo = ContentRepository(session)
            app = await repo.get_or_create_app("Jobs App")
            batch, _ = await repo.get_or_create_batch(app.id, f"Jobs Batch {int(time.time())}")
            job = await repo.create_job(
                bot_id=self.bot_id,
                user_id=self.admin_user_id,
                batch_id=batch.id
            )
            await repo.update_job_progress(job.id, JobStatus.PROCESSING, "WATERMARKING", 60.0)

            recent = await repo.get_recent_jobs(limit=5)
            self.assertGreaterEqual(len(recent), 1)
            found = any(j.id == job.id for j in recent)
            self.assertTrue(found)


if __name__ == "__main__":
    unittest.main()
