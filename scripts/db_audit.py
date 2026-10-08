import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import asyncio
from db.connection import get_db_session
from sqlalchemy import select, func
from db.models import App, Batch, Subject, Folder, Lecture, Job, YouTubeAccount

async def inspect_db():
    async with get_db_session() as session:
        n_apps = (await session.execute(select(func.count(App.id)))).scalar()
        n_batches = (await session.execute(select(func.count(Batch.id)))).scalar()
        n_subjs = (await session.execute(select(func.count(Subject.id)))).scalar()
        n_folders = (await session.execute(select(func.count(Folder.id)))).scalar()
        n_lectures = (await session.execute(select(func.count(Lecture.id)))).scalar()
        n_jobs = (await session.execute(select(func.count(Job.id)))).scalar()
        n_yt = (await session.execute(select(func.count(YouTubeAccount.id)))).scalar()
        print(f"DB_AUDIT: Apps={n_apps}, Batches={n_batches}, Subjects={n_subjs}, Folders={n_folders}, Lectures={n_lectures}, Jobs={n_jobs}, YTAccounts={n_yt}")
        
        yt_accs = (await session.execute(select(YouTubeAccount))).scalars().all()
        for y in yt_accs:
            print(f'  YouTubeAccount: id={y.id} name="{y.account_name}" status={y.status} channel_id={y.channel_id} priority={y.priority}')

        apps = (await session.execute(select(App))).scalars().all()
        for a in apps:
            print(f'  App: id={a.id} name="{a.name}" status={a.status}')
            
        batches = (await session.execute(select(Batch))).scalars().all()
        for b in batches:
            print(f'  Batch: id={b.id} name="{b.name}" app_id={b.app_id}')

        jobs = (await session.execute(select(Job))).scalars().all()
        for j in jobs:
            print(f'  Job: id={j.id} batch_id={j.batch_id} status={j.status}')

if __name__ == "__main__":
    asyncio.run(inspect_db())

