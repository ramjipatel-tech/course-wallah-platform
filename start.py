import os
import sys
import asyncio
import signal
import logging
import argparse
from pathlib import Path
import uvicorn

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config.settings import (
    BOT_TOKEN,
    API_ID,
    API_HASH,
    BOT_NAME
)
from db.connection import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [STARTUP] %(message)s"
)
logger = logging.getLogger("CourseWallahSupervisor")


async def run_web(host: str = "0.0.0.0", port: int = 8000):
    """Starts FastAPI Uvicorn server."""
    logger.info(f"Starting FastAPI Web Server on http://{host}:{port}...")
    from api.server import app
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="info",
        access_log=True
    )
    server = uvicorn.Server(config)
    await server.serve()


async def run_bot():
    """Starts Telegram Bot client."""
    if not BOT_TOKEN or not API_ID or not API_HASH:
        logger.warning("Telegram Bot credentials missing in environment. Bot service skipped.")
        return

    logger.info(f"Starting Telegram Bot ({BOT_NAME})...")
    from bot.bot_app import start_bot
    await start_bot()


async def run_worker():
    """Starts Background Ingestion & Processing Worker."""
    logger.info("Starting Background Queue Worker...")
    from worker import PlatformWorker
    worker = PlatformWorker(worker_id="railway_worker_1")
    await worker.start()


async def run_all(host: str, port: int):
    """Runs FastAPI Web API, Telegram Bot, and Background Worker concurrently in a single process."""
    logger.info("=" * 60)
    logger.info("COURSE WALLAH PLATFORM - UNIFIED CLOUD SUPERVISOR")
    logger.info(f"Target Host: {host} | Port: {port}")
    logger.info("=" * 60)

    # 1. Initialize Database & Migrations
    await init_db()

    tasks = []

    # 2. Add Web Server Task
    tasks.append(asyncio.create_task(run_web(host=host, port=port), name="FastAPI_WebServer"))

    # 3. Add Telegram Bot Task
    if BOT_TOKEN and API_ID and API_HASH:
        tasks.append(asyncio.create_task(run_bot(), name="Telegram_Bot"))
    else:
        logger.warning("BOT_TOKEN / API_ID not provided. Telegram bot will not start in this container.")

    # 4. Add Background Worker Task
    tasks.append(asyncio.create_task(run_worker(), name="Background_Worker"))

    # Wait for all services or exit on error
    try:
        await asyncio.gather(*tasks)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Shutdown signal received. Gracefully stopping all background tasks...")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("All services stopped.")


def main():
    parser = argparse.ArgumentParser(description="Course Wallah Production Supervisor")
    parser.add_argument(
        "--service",
        choices=["all", "web", "bot", "worker"],
        default=os.environ.get("SERVICE_TYPE", "all"),
        help="Service to start (all, web, bot, worker)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "8000")),
        help="Port for Web server"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host interface to bind"
    )
    args = parser.parse_args()

    service_mode = args.service.lower()
    port = args.port
    host = args.host

    logger.info(f"Selected Service Mode: '{service_mode}'")

    if service_mode == "web":
        asyncio.run(run_web(host=host, port=port))
    elif service_mode == "bot":
        asyncio.run(run_bot())
    elif service_mode == "worker":
        asyncio.run(run_worker())
    else:
        asyncio.run(run_all(host=host, port=port))


if __name__ == "__main__":
    main()
