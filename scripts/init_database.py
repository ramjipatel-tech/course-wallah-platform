import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from db.connection import init_db, engine
from sqlalchemy import inspect

async def main():
    print("=" * 65)
    print("COURSE WALLAH - DATABASE INITIALIZATION & SCHEMA BUILDER")
    print("=" * 65)
    print("\nConnecting to configured database...\n")
    
    # 1. Run automatic table creation and migrations
    try:
        await init_db()
        print("[SUCCESS] Database connection established!")
        print("[SUCCESS] Tables verified / created successfully!\n")
    except Exception as e:
        print(f"[ERROR] Connection or creation failed: {e}")
        return

    # 2. Inspect and list all tables present
    async with engine.connect() as conn:
        def get_tables(sync_conn):
            inspector = inspect(sync_conn)
            return inspector.get_table_names()
        
        tables = await conn.run_sync(get_tables)
        
        print("Database Tables Present:")
        print("--------------------------------------------------")
        for idx, table_name in enumerate(sorted(tables), 1):
            print(f"  {idx:2d}. [TABLE] {table_name}")
        print("--------------------------------------------------")
        print(f"Total Tables Ready: {len(tables)}\n")

    print("All database tables are 100% ready for Bot, Website, and Worker!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
