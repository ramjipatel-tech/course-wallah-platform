import re
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
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
    WatermarkAnimationMode,
    Job,
    JobStep,
    JobStatus,
    PublicationStatus,
    YouTubeAccount,
    YouTubeAccountStatus,
    YouTubeUpload,
    AdminUser,
    AuditLog,
    Setting,
    Student,
    StudentBatchAccess,
    StudentActivity
)

logger = logging.getLogger(__name__)

def slugify(text: str) -> str:
    """Generates a clean URL slug from text."""
    if not text:
        return "default"
    cleaned = re.sub(r"[^\w\s-]", "", text.strip().lower())
    slug = re.sub(r"[-\s]+", "-", cleaned)
    return slug[:100] if slug else "item"


class ContentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ==========================================
    # APPS & BATCHES
    # ==========================================

    async def get_or_create_app(self, name: str, description: Optional[str] = None, icon_url: Optional[str] = None) -> App:
        slug = slugify(name)
        stmt = select(App).where(or_(App.name == name, App.slug == slug))
        res = await self.session.execute(stmt)
        app = res.scalar_one_or_none()
        if not app:
            app = App(name=name, slug=slug, description=description, icon_url=icon_url)
            self.session.add(app)
            await self.session.flush()
        return app

    async def get_all_apps(self) -> List[App]:
        stmt = select(App).options(selectinload(App.batches)).where(App.status == "ACTIVE").order_by(App.name)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def count_all_batches(self) -> int:
        stmt = select(func.count(Batch.id))
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def get_app_by_slug(self, slug: str) -> Optional[App]:
        stmt = select(App).options(selectinload(App.batches)).where(App.slug == slug)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_existing_batch(self, app_id: str, batch_name: str) -> Optional[Batch]:
        slug = slugify(batch_name)
        stmt = (
            select(Batch)
            .options(selectinload(Batch.subjects))
            .where(
                and_(
                    Batch.app_id == app_id,
                    or_(Batch.name == batch_name, Batch.slug == slug)
                )
            )
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_or_create_batch(
        self,
        app_id: str,
        name: str,
        category: Optional[str] = None,
        branch: Optional[str] = None,
        semester: Optional[str] = None,
        academic_year: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        quality_pref: str = "1080p",
        source_identifier: Optional[str] = None
    ) -> Tuple[Batch, bool]:
        existing = await self.find_existing_batch(app_id, name)
        if existing:
            return existing, False

        slug = slugify(name)
        batch = Batch(
            app_id=app_id,
            name=name,
            slug=slug,
            category=category,
            branch=branch,
            semester=semester,
            academic_year=academic_year,
            thumbnail_url=thumbnail_url,
            video_quality_preference=quality_pref,
            source_identifier=source_identifier
        )
        self.session.add(batch)
        await self.session.flush()
        return batch, True

    async def get_batch_by_id(self, batch_id: str) -> Optional[Batch]:
        stmt = (
            select(Batch)
            .options(
                selectinload(Batch.app),
                selectinload(Batch.subjects).selectinload(Subject.folders)
            )
            .where(Batch.id == batch_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_app_by_id(self, app_id: str) -> Optional[App]:
        stmt = select(App).options(selectinload(App.batches)).where(App.id == app_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def update_app(
        self,
        app_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        icon_url: Optional[str] = None
    ) -> Optional[App]:
        app = await self.session.get(App, app_id)
        if not app:
            return None
        if name:
            app.name = name
            app.slug = slugify(name)
        if description is not None:
            app.description = description
        if icon_url is not None:
            app.icon_url = icon_url
        await self.session.flush()
        return app

    async def get_batches_by_app_id(self, app_id: str) -> List[Batch]:
        stmt = (
            select(Batch)
            .options(selectinload(Batch.subjects))
            .where(Batch.app_id == app_id)
            .order_by(Batch.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def update_batch(
        self,
        batch_id: str,
        name: Optional[str] = None,
        branch: Optional[str] = None,
        semester: Optional[str] = None,
        academic_year: Optional[str] = None,
        category: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        quality_pref: Optional[str] = None
    ) -> Optional[Batch]:
        batch = await self.session.get(Batch, batch_id)
        if not batch:
            return None
        if name:
            batch.name = name
            batch.slug = slugify(name)
        if branch is not None:
            batch.branch = branch
        if semester is not None:
            batch.semester = semester
        if academic_year is not None:
            batch.academic_year = academic_year
        if category is not None:
            batch.category = category
        if thumbnail_url is not None:
            batch.thumbnail_url = thumbnail_url
        if quality_pref is not None:
            batch.video_quality_preference = quality_pref
        await self.session.flush()
        return batch

    async def get_recent_jobs(self, limit: int = 10) -> List[Job]:
        stmt = (
            select(Job)
            .options(selectinload(Job.batch))
            .order_by(Job.created_at.desc())
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_batch_by_slug(self, app_slug: str, batch_slug: str) -> Optional[Batch]:
        stmt = (
            select(Batch)
            .join(App)
            .options(
                selectinload(Batch.app),
                selectinload(Batch.subjects).selectinload(Subject.folders).selectinload(Folder.lectures)
            )
            .where(and_(App.slug == app_slug, Batch.slug == batch_slug))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    # ==========================================
    # SUBJECTS & FOLDERS
    # ==========================================

    async def get_or_create_subject(self, batch_id: str, name: str, code: Optional[str] = None) -> Subject:
        slug = slugify(name)
        stmt = select(Subject).where(and_(Subject.batch_id == batch_id, or_(Subject.name == name, Subject.slug == slug)))
        res = await self.session.execute(stmt)
        subj = res.scalar_one_or_none()
        if not subj:
            # Determine sort order
            count_stmt = select(func.count(Subject.id)).where(Subject.batch_id == batch_id)
            count_res = await self.session.execute(count_stmt)
            order = (count_res.scalar() or 0) + 1
            subj = Subject(batch_id=batch_id, name=name, slug=slug, code=code, sort_order=order)
            self.session.add(subj)
            await self.session.flush()
            
            # Automatically create default playlist for subject
            await self.get_or_create_playlist(subject_id=subj.id, batch_id=batch_id, name=name)
        return subj

    async def get_or_create_folder(
        self,
        subject_id: str,
        name: str,
        parent_id: Optional[str] = None,
        unit_number: Optional[str] = None
    ) -> Folder:
        slug = slugify(name)
        cond = [Folder.subject_id == subject_id, Folder.slug == slug]
        if parent_id:
            cond.append(Folder.parent_id == parent_id)
        else:
            cond.append(Folder.parent_id.is_(None))

        stmt = select(Folder).where(and_(*cond))
        res = await self.session.execute(stmt)
        folder = res.scalar_one_or_none()
        if not folder:
            count_stmt = select(func.count(Folder.id)).where(Folder.subject_id == subject_id)
            count_res = await self.session.execute(count_stmt)
            order = (count_res.scalar() or 0) + 1

            folder = Folder(
                subject_id=subject_id,
                parent_id=parent_id,
                name=name,
                slug=slug,
                unit_number=unit_number,
                sort_order=order
            )
            self.session.add(folder)
            await self.session.flush()
        return folder

    # ==========================================
    # LECTURES & MEDIA
    # ==========================================

    async def get_lecture_by_index(self, batch_id: str, lecture_index: int) -> Optional[Lecture]:
        stmt = (
            select(Lecture)
            .options(
                selectinload(Lecture.video),
                selectinload(Lecture.pdf),
                selectinload(Lecture.folder)
            )
            .where(and_(Lecture.batch_id == batch_id, Lecture.lecture_index == lecture_index))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_max_lecture_index_for_batch(self, batch_id: str) -> int:
        stmt = select(func.max(Lecture.lecture_index)).where(Lecture.batch_id == batch_id)
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def get_batch_lecture_summary(self, batch_id: str) -> Dict[str, Any]:
        """Returns total, completed, max index, video count, pdf count for batch."""
        total_stmt = select(func.count(Lecture.id)).where(Lecture.batch_id == batch_id)
        pub_stmt = select(func.count(Lecture.id)).where(
            and_(Lecture.batch_id == batch_id, Lecture.publication_status == PublicationStatus.PUBLISHED)
        )
        max_idx_stmt = select(func.max(Lecture.lecture_index)).where(Lecture.batch_id == batch_id)
        video_count_stmt = select(func.count(Video.id)).join(Lecture).where(Lecture.batch_id == batch_id)
        pdf_count_stmt = select(func.count(PDF.id)).join(Lecture).where(Lecture.batch_id == batch_id)

        total = (await self.session.execute(total_stmt)).scalar() or 0
        published = (await self.session.execute(pub_stmt)).scalar() or 0
        max_index = (await self.session.execute(max_idx_stmt)).scalar() or 0
        videos = (await self.session.execute(video_count_stmt)).scalar() or 0
        pdfs = (await self.session.execute(pdf_count_stmt)).scalar() or 0

        return {
            "total_lectures": total,
            "published_lectures": published,
            "max_index": max_index,
            "videos_count": videos,
            "pdfs_count": pdfs
        }

    async def get_batch_by_name_or_slug(self, name_or_slug: str) -> Optional[Batch]:
        slug = slugify(name_or_slug)
        stmt = (
            select(Batch)
            .options(
                selectinload(Batch.app),
                selectinload(Batch.subjects).selectinload(Subject.folders)
            )
            .where(or_(Batch.name == name_or_slug, Batch.slug == slug))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_lecture_by_id(self, lecture_id: str) -> Optional[Lecture]:
        stmt = (
            select(Lecture)
            .options(
                selectinload(Lecture.video),
                selectinload(Lecture.pdf),
                selectinload(Lecture.folder)
            )
            .where(Lecture.id == lecture_id)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_lectures_by_batch(self, batch_id: str) -> List[Lecture]:
        stmt = (
            select(Lecture)
            .options(
                selectinload(Lecture.video),
                selectinload(Lecture.pdf),
                selectinload(Lecture.folder)
            )
            .where(Lecture.batch_id == batch_id)
            .order_by(Lecture.lecture_index)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_failed_lectures_by_batch(self, batch_id: str) -> List[Lecture]:
        stmt = (
            select(Lecture)
            .where(and_(Lecture.batch_id == batch_id, Lecture.publication_status != PublicationStatus.PUBLISHED))
            .order_by(Lecture.lecture_index)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_subject_playlist(self, subject_id: str) -> List[Dict[str, Any]]:
        stmt = (
            select(PlaylistItem)
            .join(Lecture, PlaylistItem.lecture_id == Lecture.id)
            .options(selectinload(PlaylistItem.lecture))
            .join(Playlist, PlaylistItem.playlist_id == Playlist.id)
            .where(Playlist.subject_id == subject_id)
            .order_by(PlaylistItem.position)
        )
        res = await self.session.execute(stmt)
        items = res.scalars().all()
        result = []
        for it in items:
            if it.lecture:
                result.append({
                    "position": it.position,
                    "lecture_id": it.lecture_id,
                    "title": it.lecture.title,
                    "slug": it.lecture.slug,
                    "has_video": it.lecture.has_video,
                    "has_pdf": it.lecture.has_pdf
                })
        return result

    async def create_or_update_lecture(
        self,
        folder_id: str,
        subject_id: str,
        batch_id: str,
        lecture_index: int,
        title: str,
        source_url: Optional[str] = None,
        source_pdf_url: Optional[str] = None,
        provider: Optional[str] = None,
        raw_reference: Optional[str] = None,
        has_video: bool = False,
        has_pdf: bool = False,
        publication_status: Optional[PublicationStatus] = None
    ) -> Lecture:
        stmt = select(Lecture).where(and_(Lecture.batch_id == batch_id, Lecture.lecture_index == lecture_index))
        res = await self.session.execute(stmt)
        lecture = res.scalar_one_or_none()

        pub_st = publication_status or PublicationStatus.PROCESSING
        slug = f"{lecture_index}-{slugify(title)}"
        if not lecture:
            lecture = Lecture(
                folder_id=folder_id,
                subject_id=subject_id,
                batch_id=batch_id,
                lecture_index=lecture_index,
                title=title,
                slug=slug,
                source_url=source_url,
                source_pdf_url=source_pdf_url,
                provider=provider,
                raw_reference=raw_reference,
                has_video=has_video,
                has_pdf=has_pdf,
                sort_order=lecture_index,
                publication_status=pub_st
            )
            self.session.add(lecture)
            await self.session.flush()
        else:
            lecture.folder_id = folder_id
            lecture.subject_id = subject_id
            lecture.title = title
            lecture.slug = slug
            if source_url:
                lecture.source_url = source_url
            if source_pdf_url:
                lecture.source_pdf_url = source_pdf_url
            if provider:
                lecture.provider = provider
            lecture.has_video = has_video
            lecture.has_pdf = has_pdf
            await self.session.flush()

        return lecture

    async def attach_video_to_lecture(
        self,
        lecture_id: str,
        youtube_video_id: str,
        duration: float,
        resolution: str = "1080p",
        file_size: int = 0,
        title: Optional[str] = None,
        description: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
        youtube_channel_id: Optional[str] = None,
        youtube_account_id: Optional[str] = None,
        youtube_url: Optional[str] = None,
        upload_completed_at: Optional[datetime] = None
    ) -> Video:
        completed_time = upload_completed_at or datetime.utcnow()
        clean_url = youtube_url or (f"https://www.youtube.com/watch?v={youtube_video_id}" if youtube_video_id and not youtube_video_id.startswith("cw_") else None)
        stmt = select(Video).where(Video.lecture_id == lecture_id)
        res = await self.session.execute(stmt)
        video = res.scalar_one_or_none()
        if not video:
            video = Video(
                lecture_id=lecture_id,
                youtube_video_id=youtube_video_id,
                youtube_channel_id=youtube_channel_id,
                youtube_account_id=youtube_account_id,
                youtube_url=clean_url,
                duration=duration,
                resolution=resolution,
                file_size=file_size,
                title=title,
                description=description,
                upload_completed_at=completed_time,
                metadata_json=metadata_json or {}
            )
            self.session.add(video)
        else:
            video.youtube_video_id = youtube_video_id
            if youtube_channel_id:
                video.youtube_channel_id = youtube_channel_id
            if youtube_account_id:
                video.youtube_account_id = youtube_account_id
            if clean_url:
                video.youtube_url = clean_url
            video.duration = duration
            video.resolution = resolution
            video.file_size = file_size
            video.upload_completed_at = completed_time
            if title:
                video.title = title
            if description:
                video.description = description
            if metadata_json:
                video.metadata_json = metadata_json

        # Mark lecture has_video True
        lecture = await self.session.get(Lecture, lecture_id)
        if lecture:
            lecture.has_video = True
            lecture.duration_seconds = int(duration)

        await self.session.flush()
        return video


    async def attach_pdf_to_lecture(
        self,
        lecture_id: str,
        b2_object_key: str,
        b2_bucket: str,
        file_name: str,
        file_size: int = 0,
        page_count: int = 0
    ) -> PDF:
        stmt = select(PDF).where(PDF.lecture_id == lecture_id)
        res = await self.session.execute(stmt)
        pdf = res.scalar_one_or_none()
        if not pdf:
            pdf = PDF(
                lecture_id=lecture_id,
                b2_object_key=b2_object_key,
                b2_bucket=b2_bucket,
                file_name=file_name,
                file_size=file_size,
                page_count=page_count
            )
            self.session.add(pdf)
        else:
            pdf.b2_object_key = b2_object_key
            pdf.b2_bucket = b2_bucket
            pdf.file_name = file_name
            pdf.file_size = file_size
            pdf.page_count = page_count

        # Mark lecture has_pdf True
        lecture = await self.session.get(Lecture, lecture_id)
        if lecture:
            lecture.has_pdf = True

        await self.session.flush()
        return pdf

    async def set_lecture_published(self, lecture_id: str) -> Lecture:
        lecture = await self.session.get(Lecture, lecture_id)
        if lecture:
            lecture.publication_status = PublicationStatus.PUBLISHED
            await self.session.flush()
            # Ensure in playlist
            await self.add_lecture_to_playlist(lecture.subject_id, lecture.id)
        return lecture

    async def set_lecture_failed(self, batch_id: str, lecture_index: int, error_message: Optional[str] = None) -> Optional[Lecture]:
        stmt = select(Lecture).where(and_(Lecture.batch_id == batch_id, Lecture.lecture_index == lecture_index))
        res = await self.session.execute(stmt)
        lecture = res.scalar_one_or_none()
        if lecture:
            lecture.publication_status = PublicationStatus.FAILED
            await self.session.flush()
        return lecture

    async def mark_lecture_failed_by_id(self, lecture_id: str, error_message: Optional[str] = None) -> Optional[Lecture]:
        lecture = await self.session.get(Lecture, lecture_id)
        if lecture:
            lecture.publication_status = PublicationStatus.FAILED
            await self.session.flush()
        return lecture

    # ==========================================
    # PLAYLISTS
    # ==========================================

    async def get_or_create_playlist(self, subject_id: str, batch_id: str, name: str) -> Playlist:
        slug = slugify(name)
        stmt = select(Playlist).where(and_(Playlist.subject_id == subject_id, Playlist.slug == slug))
        res = await self.session.execute(stmt)
        pl = res.scalar_one_or_none()
        if not pl:
            pl = Playlist(subject_id=subject_id, batch_id=batch_id, name=name, slug=slug)
            self.session.add(pl)
            await self.session.flush()
        return pl

    async def add_lecture_to_playlist(self, subject_id: str, lecture_id: str) -> Optional[PlaylistItem]:
        # Fetch playlist for subject
        stmt = select(Playlist).where(Playlist.subject_id == subject_id)
        res = await self.session.execute(stmt)
        pl = res.scalar_one_or_none()
        if not pl:
            lecture = await self.session.get(Lecture, lecture_id)
            if not lecture:
                return None
            pl = await self.get_or_create_playlist(subject_id, lecture.batch_id, "Main Playlist")

        # Check if item exists
        item_stmt = select(PlaylistItem).where(and_(PlaylistItem.playlist_id == pl.id, PlaylistItem.lecture_id == lecture_id))
        item_res = await self.session.execute(item_stmt)
        item = item_res.scalar_one_or_none()
        if not item:
            count_stmt = select(func.count(PlaylistItem.id)).where(PlaylistItem.playlist_id == pl.id)
            count = (await self.session.execute(count_stmt)).scalar() or 0
            item = PlaylistItem(playlist_id=pl.id, lecture_id=lecture_id, position=count + 1)
            self.session.add(item)
            pl.total_lectures = count + 1
            await self.session.flush()
        return item

    # ==========================================
    # JOBS & STEPS
    # ==========================================

    async def create_job(
        self,
        bot_id: str,
        user_id: int,
        batch_id: str,
        lecture_id: Optional[str] = None,
        provider: Optional[str] = None,
        telegram_chat_id: Optional[int] = None,
        telegram_message_id: Optional[int] = None
    ) -> Job:
        job = Job(
            bot_id=bot_id,
            user_id=user_id,
            batch_id=batch_id,
            lecture_id=lecture_id,
            provider=provider,
            status=JobStatus.QUEUED,
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def update_job_progress(
        self,
        job_id: str,
        status: JobStatus,
        current_step: str,
        progress_percent: float,
        download_progress: Optional[float] = None,
        watermark_progress: Optional[float] = None,
        youtube_progress: Optional[float] = None,
        pdf_progress: Optional[float] = None,
        b2_progress: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> Optional[Job]:
        job = await self.session.get(Job, job_id)
        if not job:
            return None
        job.status = status
        job.current_step = current_step
        job.progress_percent = progress_percent
        if download_progress is not None:
            job.download_progress = download_progress
        if watermark_progress is not None:
            job.watermark_progress = watermark_progress
        if youtube_progress is not None:
            job.youtube_progress = youtube_progress
        if pdf_progress is not None:
            job.pdf_progress = pdf_progress
        if b2_progress is not None:
            job.b2_progress = b2_progress
        if error_message:
            job.error_message = error_message
        await self.session.flush()
        return job

    # ==========================================
    # WATERMARK PROFILES
    # ==========================================

    async def get_default_watermark_profile(self) -> WatermarkProfile:
        stmt = select(WatermarkProfile).where(WatermarkProfile.is_default == True)
        res = await self.session.execute(stmt)
        prof = res.scalar_one_or_none()
        if not prof:
            prof = WatermarkProfile(
                name="Default Moving Watermark",
                is_default=True,
                enabled=True,
                text="COURSE WALLAH",
                opacity=0.45,
                animation_mode=WatermarkAnimationMode.CONTINUOUS_DRIFT,
                movement_interval=8,
                crf=26
            )
            self.session.add(prof)
            await self.session.flush()
        return prof

    # ==========================================
    # STUDENT MANAGEMENT & ACCESS
    # ==========================================

    async def find_students(self, query: str = "", limit: int = 20) -> List[Student]:
        stmt = select(Student).options(selectinload(Student.batch_accesses))
        if query:
            clean = f"%{query.strip()}%"
            stmt = stmt.where(or_(Student.name.ilike(clean), Student.email.ilike(clean)))
        stmt = stmt.order_by(Student.created_at.desc()).limit(limit)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_student_by_id(self, student_id: str) -> Optional[Student]:
        stmt = select(Student).options(selectinload(Student.batch_accesses)).where(Student.id == student_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_student_by_email(self, email: str) -> Optional[Student]:
        stmt = select(Student).options(selectinload(Student.batch_accesses)).where(Student.email == email.strip().lower())
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def grant_student_batch_access(self, student_id: str, batch_id: str, access_status: str = "ACTIVE") -> StudentBatchAccess:
        stmt = select(StudentBatchAccess).where(
            and_(StudentBatchAccess.student_id == student_id, StudentBatchAccess.batch_id == batch_id)
        )
        res = await self.session.execute(stmt)
        acc = res.scalar_one_or_none()
        if not acc:
            acc = StudentBatchAccess(
                student_id=student_id,
                batch_id=batch_id,
                status=access_status,
                granted_at=datetime.utcnow()
            )
            self.session.add(acc)
        else:
            acc.status = access_status
            acc.revoked_at = None
        await self.session.flush()
        return acc

    async def revoke_student_batch_access(self, student_id: str, batch_id: str) -> bool:
        stmt = select(StudentBatchAccess).where(
            and_(StudentBatchAccess.student_id == student_id, StudentBatchAccess.batch_id == batch_id)
        )
        res = await self.session.execute(stmt)
        acc = res.scalar_one_or_none()
        if acc:
            acc.status = "REVOKED"
            acc.revoked_at = datetime.utcnow()
            await self.session.flush()
            return True
        return False

    async def set_student_active_status(self, student_id: str, is_active: bool) -> bool:
        stmt = select(Student).where(Student.id == student_id)
        res = await self.session.execute(stmt)
        student = res.scalar_one_or_none()
        if student:
            student.is_active = is_active
            await self.session.flush()
            return True
        return False

    # ==========================================
    # MEDIA DIAGNOSTICS & HEALTH
    # ==========================================

    async def get_media_health_summary(self) -> Dict[str, Any]:
        total_lectures = (await self.session.execute(select(func.count(Lecture.id)))).scalar() or 0
        total_videos = (await self.session.execute(select(func.count(Video.id)))).scalar() or 0
        total_pdfs = (await self.session.execute(select(func.count(PDF.id)))).scalar() or 0
        total_batches = (await self.session.execute(select(func.count(Batch.id)))).scalar() or 0
        total_students = (await self.session.execute(select(func.count(Student.id)))).scalar() or 0
        
        # Check jobs
        active_jobs = (await self.session.execute(
            select(func.count(Job.id)).where(Job.status.in_([JobStatus.RUNNING, JobStatus.QUEUED]))
        )).scalar() or 0
        failed_jobs = (await self.session.execute(
            select(func.count(Job.id)).where(Job.status == JobStatus.FAILED)
        )).scalar() or 0

        return {
            "total_students": total_students,
            "total_batches": total_batches,
            "total_lectures": total_lectures,
            "total_videos": total_videos,
            "total_pdfs": total_pdfs,
            "active_jobs": active_jobs,
            "failed_jobs": failed_jobs,
            "video_coverage_pct": round((total_videos / max(1, total_lectures)) * 100, 1),
            "pdf_coverage_pct": round((total_pdfs / max(1, total_lectures)) * 100, 1)
        }

    # ==========================================
    # YOUTUBE ACCOUNT & MULTI-ACCOUNT FAILOVER
    # ==========================================

    async def get_youtube_account_by_id(self, account_id: str) -> Optional[YouTubeAccount]:
        stmt = select(YouTubeAccount).where(YouTubeAccount.id == account_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_all_youtube_accounts(self) -> List[YouTubeAccount]:
        stmt = select(YouTubeAccount).order_by(YouTubeAccount.priority.asc(), YouTubeAccount.created_at.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_active_youtube_accounts(self) -> List[YouTubeAccount]:
        stmt = select(YouTubeAccount).where(
            YouTubeAccount.status == YouTubeAccountStatus.ACTIVE.value
        ).order_by(YouTubeAccount.priority.asc(), YouTubeAccount.uploads_today.asc(), YouTubeAccount.created_at.asc())
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def create_or_update_youtube_account(
        self,
        name: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        refresh_token: Optional[str] = None,
        channel_id: Optional[str] = None,
        channel_title: Optional[str] = None,
        status: str = YouTubeAccountStatus.ACTIVE.value,
        priority: int = 1,
        account_id: Optional[str] = None
    ) -> YouTubeAccount:
        acc = None
        if account_id:
            acc = await self.get_youtube_account_by_id(account_id)
        elif client_id and refresh_token:
            stmt = select(YouTubeAccount).where(
                and_(YouTubeAccount.client_id == client_id, YouTubeAccount.refresh_token == refresh_token)
            )
            res = await self.session.execute(stmt)
            acc = res.scalar_one_or_none()

        if not acc:
            acc = YouTubeAccount(
                name=name,
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                channel_id=channel_id,
                channel_title=channel_title,
                status=status,
                priority=priority,
                uploads_today=0,
                quota_reset_date=datetime.utcnow()
            )
            self.session.add(acc)
        else:
            acc.name = name
            if client_id is not None:
                acc.client_id = client_id
            if client_secret is not None:
                acc.client_secret = client_secret
            if refresh_token is not None:
                acc.refresh_token = refresh_token
            if channel_id is not None:
                acc.channel_id = channel_id
            if channel_title is not None:
                acc.channel_title = channel_title
            acc.priority = priority
            if status:
                acc.status = status
        if status == YouTubeAccountStatus.ACTIVE.value:
            acc.cooldown_until = None
            acc.is_active = True
        else:
            acc.is_active = False

        await self.session.flush()
        return acc

    async def mark_youtube_account_status(
        self,
        account_id: str,
        status: str,
        last_error: Optional[str] = None,
        last_error_type: Optional[str] = None,
        cooldown_hours: Optional[float] = None
    ) -> Optional[YouTubeAccount]:
        acc = await self.get_youtube_account_by_id(account_id)
        if not acc:
            return None

        acc.status = status
        now = datetime.utcnow()
        if last_error is not None:
            acc.last_error = last_error
        if last_error_type is not None:
            acc.last_error_type = last_error_type

        if status == YouTubeAccountStatus.LIMIT_REACHED.value:
            acc.limit_detected_at = now
            acc.is_active = False
            hours = cooldown_hours if cooldown_hours is not None else 24.0
            from datetime import timedelta
            acc.cooldown_until = now + timedelta(hours=hours)
        elif status == YouTubeAccountStatus.ACTIVE.value:
            acc.cooldown_until = None
            acc.is_active = True
            acc.last_error = None
            acc.last_error_type = None
        else:
            acc.is_active = False

        await self.session.flush()
        return acc

    async def record_successful_youtube_upload(
        self,
        account_id: str,
        lecture_id: Optional[str] = None,
        video_id: Optional[str] = None,
        youtube_video_id: Optional[str] = None,
        youtube_channel_id: Optional[str] = None,
        youtube_url: Optional[str] = None,
        job_id: Optional[str] = None
    ) -> YouTubeUpload:
        now = datetime.utcnow()
        clean_url = youtube_url or (f"https://www.youtube.com/watch?v={youtube_video_id}" if youtube_video_id else None)
        upload_rec = YouTubeUpload(
            job_id=job_id,
            lecture_id=lecture_id,
            video_id=video_id,
            account_id=account_id,
            channel_id=youtube_channel_id,
            youtube_video_id=youtube_video_id,
            youtube_url=clean_url,
            upload_status="SUCCESS",
            upload_completed_at=now
        )
        self.session.add(upload_rec)

        # If lecture_id is provided, also attach/update Video record on the lecture
        if lecture_id and youtube_video_id:
            vid = await self.attach_video_to_lecture(
                lecture_id=lecture_id,
                youtube_video_id=youtube_video_id,
                duration=0.0,
                youtube_channel_id=youtube_channel_id,
                youtube_account_id=account_id,
                youtube_url=clean_url,
                upload_completed_at=now
            )
            upload_rec.video_id = vid.id

        # Increment upload count on account
        acc = await self.get_youtube_account_by_id(account_id)
        if acc:
            acc.uploads_today = (acc.uploads_today or 0) + 1
            acc.last_upload_at = now

        await self.session.flush()
        return upload_rec

    async def delete_youtube_account(self, account_id: str) -> bool:
        """Deletes a YouTube account by ID from the database."""
        acc = await self.get_youtube_account_by_id(account_id)
        if not acc:
            return False
        await self.session.delete(acc)
        await self.session.flush()
        return True

    async def reset_account_quotas_if_needed(self):
        """Resets uploads_today to 0 if a new UTC day has started, and restores expired cooldowns."""
        now = datetime.utcnow()
        accounts = await self.get_all_youtube_accounts()
        for acc in accounts:
            # 1. Daily quota counter reset
            reset_date = acc.quota_reset_date or acc.created_at or now
            if reset_date.date() < now.date():
                acc.uploads_today = 0
                acc.quota_reset_date = now

            # 2. Cooldown check & restoration
            if acc.status == YouTubeAccountStatus.LIMIT_REACHED.value and acc.cooldown_until and now >= acc.cooldown_until:
                acc.status = YouTubeAccountStatus.ACTIVE.value
                acc.cooldown_until = None
                acc.last_error = None
                acc.last_error_type = None

        await self.session.flush()



