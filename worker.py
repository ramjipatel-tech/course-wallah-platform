import os
import sys
import time
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config.settings import MAX_CONCURRENT_JOBS
from db.connection import get_db_session, init_db
from db.models import Job, JobStatus
from db.repository import ContentRepository
from engines.job_engine import ContentProcessingEngine
from sqlalchemy import select, and_

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [WORKER] %(message)s"
)
logger = logging.getLogger("CourseWallahWorker")

class PlatformWorker:
    """
    Dedicated Background Job Worker for Course Wallah Content Platform.
    Polls the database for queued/retrying jobs and executes them via ContentProcessingEngine.
    """

    def __init__(self, worker_id: str = "worker_main"):
        self.worker_id = worker_id
        self.engine = ContentProcessingEngine(bot_id=worker_id)
        self.running = False
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)

    async def start(self):
        logger.info(f"Initializing Course Wallah Content Worker ({self.worker_id})...")
        await init_db()
        self.running = True
        logger.info(f"Worker {self.worker_id} started. Max concurrency: {MAX_CONCURRENT_JOBS}")

        while self.running:
            try:
                await self._poll_and_execute_jobs()
            except Exception as e:
                logger.error(f"Error in worker event loop: {e}", exc_info=True)
            await asyncio.sleep(2)

    async def stop(self):
        logger.info(f"Stopping worker {self.worker_id}...")
        self.running = False

    async def _poll_and_execute_jobs(self):
        async with get_db_session() as session:
            stmt = (
                select(Job)
                .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]))
                .order_by(Job.created_at.asc())
                .limit(MAX_CONCURRENT_JOBS)
            )
            res = await session.execute(stmt)
            jobs = res.scalars().all()

            if jobs:
                logger.info(f"Found {len(jobs)} pending jobs in queue.")
                for job in jobs:
                    # Mark as downloading/processing in DB
                    job.status = JobStatus.DOWNLOADING
                    job.current_step = "Picked up by worker"
                await session.flush()

async def main():
    worker = PlatformWorker()
    try:
        await worker.start()
    except (KeyboardInterrupt, asyncio.CancelledError):
        await worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
