import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.connection import engine, init_db
from db.models import Base

async def reset_database():
    print("=" * 60)
    print(" ⚠️  COURSE WALLAH — DATABASE RESET UTILITY")
    print("=" * 60)
    print("Connecting to database...")

    async with engine.begin() as conn:
        print("Dropping all existing tables...")
        await conn.run_sync(Base.metadata.drop_all)
        print("All old tables dropped successfully.")

    print("\nRebuilding fresh schema...")
    await init_db()
    print("\n✅ Database schema has been freshly recreated with 0 test rows!")
    print("=" * 60)

if __name__ == "__main__":
    confirm = input("Are you sure you want to drop and reset all database tables? (yes/no): ").strip().lower()
    if confirm in ("yes", "y"):
        asyncio.run(reset_database())
    else:
        print("Reset cancelled.")
