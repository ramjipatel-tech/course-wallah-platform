from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import App, Batch, Subject, Lecture, PublicationStatus

router = APIRouter(prefix="/search", tags=["Search"])

@router.get("")
async def search_content(
    q: str = Query("", description="Search query"),
    db: AsyncSession = Depends(get_db_dependency)
):
    trimmed = q.strip()
    if len(trimmed) < 2:
        return {
            "query": q,
            "results_count": 0,
            "apps": [],
            "batches": [],
            "lectures": []
        }

    query_str = f"%{trimmed.lower()}%"

    # Search Apps
    app_stmt = select(App).where(and_(App.status == "ACTIVE", App.name.ilike(query_str)))
    app_res = await db.execute(app_stmt)
    apps = [
        {"type": "app", "id": a.id, "name": a.name, "slug": a.slug, "description": a.description, "icon_url": a.icon_url}
        for a in app_res.scalars().all()
    ]

    # Search Batches
    batch_stmt = select(Batch).where(and_(Batch.status == "ACTIVE", Batch.name.ilike(query_str)))
    batch_res = await db.execute(batch_stmt)
    batches = [
        {"type": "batch", "id": b.id, "name": b.name, "slug": b.slug, "category": b.category, "thumbnail_url": b.thumbnail_url}
        for b in batch_res.scalars().all()
    ]

    # Search Lectures
    lec_stmt = (
        select(Lecture)
        .options(selectinload(Lecture.batch), selectinload(Lecture.subject))
        .where(
            and_(
                Lecture.publication_status == PublicationStatus.PUBLISHED,
                Lecture.title.ilike(query_str)
            )
        )
        .limit(20)
    )
    lec_res = await db.execute(lec_stmt)
    lectures = [
        {
            "type": "lecture",
            "id": l.id,
            "title": l.title,
            "index": l.lecture_index,
            "lecture_index": l.lecture_index,
            "batch_name": l.batch.name if l.batch else "",
            "subject_name": l.subject.name if l.subject else "",
            "has_video": l.has_video,
            "has_pdf": l.has_pdf
        }
        for l in lec_res.scalars().all()
    ]

    return {
        "query": q,
        "results_count": len(apps) + len(batches) + len(lectures),
        "apps": apps,
        "batches": batches,
        "lectures": lectures
    }
