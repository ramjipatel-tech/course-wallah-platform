from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from db.connection import get_db_dependency
from db.models import Lecture, PDF, PublicationStatus
from engines.b2_storage import B2StorageManager

router = APIRouter(prefix="/pdfs", tags=["PDFs"])

@router.get("/{lecture_id}/access")
async def get_pdf_access(lecture_id: str, db: AsyncSession = Depends(get_db_dependency)):
    """
    Generates a secure, temporary presigned URL for Backblaze B2 PDF access.
    Expires in 15 minutes (900 seconds). Credentials are NEVER exposed to the frontend.
    """
    stmt = (
        select(Lecture)
        .options(selectinload(Lecture.pdf))
        .where(Lecture.id == lecture_id)
    )
    res = await db.execute(stmt)
    lecture = res.scalar_one_or_none()
    if not lecture or not lecture.pdf or lecture.publication_status != PublicationStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="PDF notes not found or lecture is not published")

    pdf = lecture.pdf
    presigned_url = B2StorageManager.generate_presigned_url(
        object_key=pdf.b2_object_key,
        bucket_name=pdf.b2_bucket,
        expires_in_seconds=900
    )

    return {
        "lecture_id": lecture.id,
        "lecture_title": lecture.title,
        "file_name": pdf.file_name,
        "file_size": pdf.file_size,
        "page_count": pdf.page_count,
        "download_url": presigned_url or f"/api/v1/pdfs/{lecture.id}/content",
        "access_url": f"/api/v1/pdfs/{lecture.id}/content",
        "expires_in_seconds": 900
    }

@router.get("/{lecture_id}/content")
async def get_pdf_content(lecture_id: str, db: AsyncSession = Depends(get_db_dependency)):
    """
    Streams PDF content securely to PDF.js canvas viewer.
    Eliminates all CORS restrictions and preserves complete privacy of Backblaze B2 credentials.
    """
    import asyncio
    from fastapi.responses import Response
    
    stmt = (
        select(Lecture)
        .options(selectinload(Lecture.pdf))
        .where(Lecture.id == lecture_id)
    )
    res = await db.execute(stmt)
    lecture = res.scalar_one_or_none()
    if not lecture or not lecture.pdf or lecture.publication_status != PublicationStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="PDF notes not found or lecture is not published")

    pdf = lecture.pdf
    pdf_bytes = await asyncio.to_thread(B2StorageManager.get_pdf_bytes, pdf.b2_object_key, pdf.b2_bucket)
    if not pdf_bytes:
        raise HTTPException(status_code=502, detail="Unable to retrieve PDF data from secure storage")

    import urllib.parse
    ascii_filename = "".join(c if ord(c) < 128 and (c.isalnum() or c in ".-_ ") else "_" for c in pdf.file_name).strip("_")
    if not ascii_filename.endswith(".pdf"):
        ascii_filename += ".pdf"
    encoded_filename = urllib.parse.quote(pdf.file_name)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{ascii_filename}"; filename*=UTF-8\'\'{encoded_filename}',
            "Cache-Control": "private, max-age=1800",
            "Access-Control-Allow-Origin": "*",
            "X-Content-Type-Options": "nosniff"
        }
    )


