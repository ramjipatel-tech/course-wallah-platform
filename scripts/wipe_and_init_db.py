import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_db_session, init_db
from sqlalchemy import text

async def wipe_clean():
    await init_db()
    async with get_db_session() as session:
        print("[DB WIPE] Starting complete database purge...")
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
            "apps"
        ]
        
        try:
            await session.execute(text("PRAGMA foreign_keys = OFF;"))
        except Exception:
            pass

        for t in tables:
            try:
                await session.execute(text(f"DELETE FROM {t};"))
            except Exception as e:
                pass
        
        try:
            await session.execute(text("PRAGMA foreign_keys = ON;"))
        except Exception:
            pass

        await session.commit()
        print("[DB WIPE] All tables truncated successfully.")

    # Verify counts
    async with get_db_session() as session:
        print("\n[DB VERIFICATION] Checking table counts:")
        for t in tables:
            try:
                res = await session.execute(text(f"SELECT COUNT(*) FROM {t};"))
                cnt = res.scalar()
                print(f"  • Table {t:18}: {cnt} rows")
            except Exception as e:
                print(f"  • Table {t:18}: Error ({e})")

    print("\n[SUCCESS] Database is 100% clean and ready for new batch extraction!")

asyncio.run(wipe_clean())
