import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_db_session, init_db, engine
from db.models import Base
from sqlalchemy import text

async def reset_database():
    await init_db()
    async with get_db_session() as session:
        print("Cleaning all database tables...")
        # Disable foreign key checks for clean truncation in sqlite
        try:
            await session.execute(text("PRAGMA foreign_keys = OFF;"))
        except Exception:
            pass

        tables = [
            "video_storages",
            "videos",
            "pdfs",
            "playlist_items",
            "playlists",
            "jobs",
            "lectures",
            "folders",
            "subjects",
            "batches",
            "apps",
            "users",
            "system_logs",
            "audit_logs"
        ]

        for table in tables:
            try:
                await session.execute(text(f"DELETE FROM {table};"))
                print(f"  ✓ Cleaned table: {table}")
            except Exception as e:
                print(f"  - Table {table} skipped or not present: {e}")

        try:
            await session.execute(text("PRAGMA foreign_keys = ON;"))
        except Exception:
            pass

        await session.commit()
        print("\nDATABASE RESET 100% COMPLETE! All batches and lectures deleted cleanly.")

asyncio.run(reset_database())
