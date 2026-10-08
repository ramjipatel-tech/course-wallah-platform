from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import Batch, Subject, Folder, Lecture, PublicationStatus

router = APIRouter(prefix="/batches", tags=["Batches"])

@router.get("/{batch_id_or_slug}")
async def get_batch_hierarchy(batch_id_or_slug: str, db: AsyncSession = Depends(get_db_dependency)):
    """
    Returns complete batch hierarchy: Subjects -> Folders / Units -> Lectures.
    Only PUBLISHED lectures are visible to normal students.
    """
    stmt = (
        select(Batch)
        .options(
            selectinload(Batch.app),
            selectinload(Batch.subjects)
            .selectinload(Subject.folders)
            .selectinload(Folder.lectures)
        )
        .where(
            or_(Batch.id == batch_id_or_slug, Batch.slug == batch_id_or_slug)
        )
    )
    res = await db.execute(stmt)
    batch = res.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")

    subjects_data = []
    for subj in sorted(batch.subjects, key=lambda s: s.sort_order):
        folders_data = []
        for folder in sorted(subj.folders, key=lambda f: f.sort_order):
            published_lectures = [
                lec for lec in sorted(folder.lectures, key=lambda l: l.lecture_index)
                if lec.publication_status == PublicationStatus.PUBLISHED
            ]
            folders_data.append({
                "id": folder.id,
                "name": folder.name,
                "slug": folder.slug,
                "unit_number": folder.unit_number,
                "total_lectures": len(published_lectures),
                "lectures": [
                    {
                        "id": l.id,
                        "title": l.title,
                        "slug": l.slug,
                        "index": l.lecture_index,
                        "duration_seconds": l.duration_seconds,
                        "has_video": l.has_video,
                        "has_pdf": l.has_pdf,
                        "thumbnail_url": l.thumbnail_url
                    }
                    for l in published_lectures
                ]
            })

        subjects_data.append({
            "id": subj.id,
            "name": subj.name,
            "slug": subj.slug,
            "code": subj.code,
            "folders": folders_data
        })

    return {
        "id": batch.id,
        "name": batch.name,
        "slug": batch.slug,
        "app_name": batch.app.name if batch.app else "Course Wallah",
        "category": batch.category,
        "branch": batch.branch,
        "semester": batch.semester,
        "academic_year": batch.academic_year,
        "thumbnail_url": batch.thumbnail_url,
        "subjects": subjects_data
    }
