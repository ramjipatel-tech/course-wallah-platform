import sys
import os
import asyncio
import logging
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db.connection import init_db, get_db_session
from db.repository import ContentRepository
from db.models import Batch, Lecture, JobStatus, PublicationStatus
from engines.job_engine import ContentProcessingEngine, BatchJobController
from parsers.indexer import NormalizedBatchTree, NormalizedSubject, NormalizedFolder, NormalizedLecture

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("test_appx_3lectures")

async def run_test():
    await init_db()
    logger.info("Database initialized.")

    batch_name = "Digital Electronics Microprocessor"
    app_name = "Technical Classes"

    async with get_db_session() as session:
        repo = ContentRepository(session)
        apps = await repo.get_all_apps()
        app_obj = next((a for a in apps if "technical" in a.name.lower()), None)
        if not app_obj:
            logger.error("App Technical Classes not found!")
            return False

        batches = await repo.get_batches_by_app_id(app_obj.id)
        batch_obj = next((b for b in batches if "digital" in b.name.lower()), None)
        if not batch_obj:
            logger.error("Batch Digital Electronics Microprocessor not found!")
            return False

        lectures = await repo.get_lectures_by_batch(batch_obj.id)
        logger.info(f"Found {len(lectures)} lectures for batch: {batch_obj.name}")

    if not lectures:
        logger.error("No lectures found in batch!")
        return False

    # Construct NormalizedBatchTree from DB lectures
    norm_lectures = []
    for idx, lec in enumerate(lectures, start=1):
        norm_lectures.append(NormalizedLecture(
            index=lec.lecture_index,
            title=lec.title,
            video_url=lec.source_url,
            pdf_url=lec.source_pdf_url,
            provider=lec.provider or "appx_lecture",
            raw_reference=lec.raw_reference or f"Lecture {lec.lecture_index}"
        ))

    norm_folder = NormalizedFolder(
        name="Unit-01",
        unit_number=1,
        lectures=norm_lectures
    )
    norm_subject = NormalizedSubject(
        name="Digital Electronics & Microprocessor",
        folders=[norm_folder]
    )
    tree = NormalizedBatchTree(
        app_name=app_name,
        batch_name=batch_name,
        subjects=[norm_subject],
        total_lectures=len(norm_lectures)
    )

    engine = ContentProcessingEngine(bot_id="bot_test")
    job_id = f"test_job_{batch_obj.id[:8]}"

    # Mock Telegram status message to test that UI updates never cause exceptions or failure
    class MockTelegramMessage:
        async def edit_text(self, text, reply_markup=None):
            logger.debug(f"[MOCK_TELEGRAM_EDIT] {text[:60]}... (markup={bool(reply_markup)})")
            return True

    controller = BatchJobController(
        bot_id="bot_test",
        job_id=job_id,
        batch_id=batch_obj.id,
        batch_name=batch_obj.name,
        user_id=12345678,
        total_lectures=len(norm_lectures),
        status_message=MockTelegramMessage()
    )

    session_data = {
        "tree": tree,
        "app_name": app_name,
        "batch_name": batch_name,
        "quality_pref": "1080p",
        "watermark_profile": "Continuous Drift",
        "start_index": 1,
        "retry_failed_only": False
    }

    logger.info("Executing 3-lecture real AppX batch run...")
    summary = await engine.run_full_batch(
        controller=controller,
        session_data=session_data,
        start_index=1,
        retry_failed_only=False
    )

    logger.info(f"Execution Summary: {summary}")
    return summary

if __name__ == "__main__":
    summary = asyncio.run(run_test())
    print("\nFINAL SUMMARY RESULT:", summary)
