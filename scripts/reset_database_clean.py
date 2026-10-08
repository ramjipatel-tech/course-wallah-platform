import os
import sys
import shutil
import asyncio
from datetime import datetime
from pathlib import Path

# Set up project path
PLATFORM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLATFORM_DIR))

from sqlalchemy import select, func
from db.connection import get_db_session, init_db, engine
from db.models import (
    Base,
    App,
    Batch,
    Subject,
    Folder,
    Lecture,
    Video,
    VideoPart,
    PDF,
    Playlist,
    PlaylistItem,
    WatermarkProfile,
    Job,
    JobStep,
    YouTubeAccount,
    YouTubeUpload,
    AdminUser,
    AuditLog,
    Setting
)

async def get_all_table_counts():
    async with get_db_session() as session:
        counts = {
            "Apps": (await session.execute(select(func.count(App.id)))).scalar() or 0,
            "Batches": (await session.execute(select(func.count(Batch.id)))).scalar() or 0,
            "Subjects": (await session.execute(select(func.count(Subject.id)))).scalar() or 0,
            "Folders": (await session.execute(select(func.count(Folder.id)))).scalar() or 0,
            "Lectures": (await session.execute(select(func.count(Lecture.id)))).scalar() or 0,
            "Videos": (await session.execute(select(func.count(Video.id)))).scalar() or 0,
            "VideoParts": (await session.execute(select(func.count(VideoPart.id)))).scalar() or 0,
            "PDFs": (await session.execute(select(func.count(PDF.id)))).scalar() or 0,
            "Playlists": (await session.execute(select(func.count(Playlist.id)))).scalar() or 0,
            "PlaylistItems": (await session.execute(select(func.count(PlaylistItem.id)))).scalar() or 0,
            "WatermarkProfiles": (await session.execute(select(func.count(WatermarkProfile.id)))).scalar() or 0,
            "Jobs": (await session.execute(select(func.count(Job.id)))).scalar() or 0,
            "JobSteps": (await session.execute(select(func.count(JobStep.id)))).scalar() or 0,
            "YouTubeAccounts": (await session.execute(select(func.count(YouTubeAccount.id)))).scalar() or 0,
            "YouTubeUploads": (await session.execute(select(func.count(YouTubeUpload.id)))).scalar() or 0,
            "AdminUsers": (await session.execute(select(func.count(AdminUser.id)))).scalar() or 0,
            "AuditLogs": (await session.execute(select(func.count(AuditLog.id)))).scalar() or 0,
            "Settings": (await session.execute(select(func.count(Setting.key)))).scalar() or 0,
        }
        return counts

async def perform_database_reset():
    db_file = PLATFORM_DIR / "data" / "course_wallah.db"
    backups_dir = PLATFORM_DIR / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_file = backups_dir / f"course_wallah.db.{timestamp}.bak"
    report_file = backups_dir / f"database_reset_report.{timestamp}.txt"

    print("=" * 60)
    print("COURSE WALLAH — FRESH DATABASE RESET")
    print("=" * 60)
    print(f"Target Database: {db_file}")
    print(f"Backups Directory: {backups_dir}")

    old_counts = {}
    if db_file.exists():
        print("\n[1/5] Collecting pre-reset database counts...")
        try:
            old_counts = await get_all_table_counts()
            for k, v in old_counts.items():
                print(f"  • {k}: {v}")
        except Exception as e:
            print(f"  Warning querying old DB: {e}")
            old_counts = {"Error": str(e)}

        print(f"\n[2/5] Creating database backup: {backup_file.name}...")
        await engine.dispose()
        shutil.copy2(db_file, backup_file)
        print(f"  Backup saved ({backup_file.stat().st_size} bytes)")
    else:
        print("\n[1/5] No existing database file found to backup.")
        old_counts = {"status": "No pre-existing database file"}

    print("\n[3/5] Resetting database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("  All existing tables dropped.")

    print("\n[4/5] Initializing fresh schema tables...")
    await init_db()
    print("  Schema created cleanly.")

    print("\n[5/5] Verifying new zero database counts...")
    new_counts = await get_all_table_counts()
    for k, v in new_counts.items():
        print(f"  • {k}: {v}")

    # Write report file
    report_content = f"""COURSE WALLAH DATABASE RESET REPORT
============================================================
Reset Timestamp (UTC): {datetime.utcnow().isoformat()}Z
Platform Directory: {PLATFORM_DIR}
Database File: {db_file}
Backup Path: {backup_file if db_file.exists() else 'N/A'}
Backup Size: {backup_file.stat().st_size if backup_file.exists() else 0} bytes

OLD DATABASE RECORD COUNTS:
------------------------------------------------------------
"""
    for k, v in old_counts.items():
        report_content += f"{k}: {v}\n"

    report_content += f"""
NEW FRESH DATABASE RECORD COUNTS:
------------------------------------------------------------
"""
    for k, v in new_counts.items():
        report_content += f"{k}: {v}\n"

    report_content += """
STATUS: CLEAN FRESH DATABASE READY
============================================================
"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_content)

    print(f"\nReset report generated: {report_file}")
    print("=" * 60)
    print("FRESH DATABASE RESET COMPLETE — ALL CONTENT COUNTS = 0")
    print("=" * 60)
    return old_counts, new_counts, backup_file, report_file

if __name__ == "__main__":
    asyncio.run(perform_database_reset())
