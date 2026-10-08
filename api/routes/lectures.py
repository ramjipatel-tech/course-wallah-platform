from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import Lecture, Video, PDF, Subject, Folder, Batch, PublicationStatus, Playlist, PlaylistItem

router = APIRouter(prefix="/lectures", tags=["Lectures"])

@router.get("/{lecture_id}")
async def get_lecture_details(lecture_id: str, db: AsyncSession = Depends(get_db_dependency)):
    stmt = (
        select(Lecture)
        .options(
            selectinload(Lecture.video),
            selectinload(Lecture.pdf),
            selectinload(Lecture.folder),
            selectinload(Lecture.subject),
            selectinload(Lecture.batch).selectinload(Batch.app)
        )
        .where(Lecture.id == lecture_id)
    )
    res = await db.execute(stmt)
    lecture = res.scalar_one_or_none()
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    # Find next and previous lectures in the same subject / folder
    sibling_stmt = (
        select(Lecture)
        .where(
            and_(
                Lecture.subject_id == lecture.subject_id,
                Lecture.publication_status == PublicationStatus.PUBLISHED
            )
        )
        .order_by(Lecture.lecture_index)
    )
    siblings_res = await db.execute(sibling_stmt)
    siblings = list(siblings_res.scalars().all())

    prev_lec = None
    next_lec = None
    for i, s in enumerate(siblings):
        if s.id == lecture.id:
            if i > 0:
                prev_lec = {"id": siblings[i-1].id, "title": siblings[i-1].title, "index": siblings[i-1].lecture_index}
            if i + 1 < len(siblings):
                next_lec = {"id": siblings[i+1].id, "title": siblings[i+1].title, "index": siblings[i+1].lecture_index}
            break

    return {
        "id": lecture.id,
        "title": lecture.title,
        "index": lecture.lecture_index,
        "duration_seconds": lecture.duration_seconds,
        "has_video": lecture.has_video,
        "has_pdf": lecture.has_pdf,
        "folder_name": lecture.folder.name if lecture.folder else "General",
        "subject_name": lecture.subject.name if lecture.subject else "Subject",
        "batch_name": lecture.batch.name if lecture.batch else "Batch",
        "batch_slug": lecture.batch.slug if lecture.batch else "engg-math",
        "app_name": lecture.batch.app.name if lecture.batch and lecture.batch.app else "Course Wallah",
        "app_slug": lecture.batch.app.slug if lecture.batch and lecture.batch.app else "course-wallah-e2e",
        "prev_lecture": prev_lec,
        "next_lecture": next_lec,
        "playlist": [
            {
                "id": item.id,
                "title": item.title,
                "index": item.lecture_index,
                "has_video": item.has_video,
                "has_pdf": item.has_pdf,
                "is_active": item.id == lecture.id
            }
            for item in siblings
        ]
    }

@router.get("/{lecture_id}/access")
async def get_lecture_playback_access(lecture_id: str, db: AsyncSession = Depends(get_db_dependency)):
    """
    Returns secure video playback access parameters for Course Wallah custom player.
    Never exposes internal tokens or storage credentials.
    """
    stmt = (
        select(Lecture)
        .options(selectinload(Lecture.video), selectinload(Lecture.pdf))
        .where(Lecture.id == lecture_id)
    )
    res = await db.execute(stmt)
    lecture = res.scalar_one_or_none()
    if not lecture or lecture.publication_status != PublicationStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Lecture not available or unpublished")

    video = lecture.video
    if not video or not video.youtube_video_id:
        return {
            "has_video": False,
            "has_pdf": lecture.has_pdf,
            "message": "This lecture contains study material only."
        }

    pdf_url = lecture.source_pdf_url or (f"/api/v1/pdfs/{lecture.id}/content" if lecture.pdf else None)
    return {
        "has_video": True,
        "has_pdf": lecture.has_pdf,
        "title": lecture.title,
        "duration": video.duration,
        "youtube_video_id": video.youtube_video_id,
        "pdf_download_url": pdf_url,
        "player_config": {
            "autoplay": False,
            "controls": True,
            "branding": "Course Wallah",
            "quality": video.resolution or "1080p"
        }
    }

