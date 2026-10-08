import os
import re
import json
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple

from parsers.academic_parser import parse_course_txt, AcademicCourse, AcademicItem, normalize_title
from parsers.structured_batch_parser import detect_txt_format
from providers.router import MediaRouter, MediaType

@dataclass
class NormalizedLecture:
    index: int
    title: str
    video_url: Optional[str] = None
    pdf_url: Optional[str] = None
    provider: Optional[str] = None
    category: str = "video"
    raw_reference: str = ""
    extra_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NormalizedFolder:
    name: str
    unit_number: Optional[str] = None
    sort_order: int = 0
    lectures: List[NormalizedLecture] = field(default_factory=list)

@dataclass
class NormalizedSubject:
    name: str
    code: Optional[str] = None
    sort_order: int = 0
    folders: List[NormalizedFolder] = field(default_factory=list)

@dataclass
class NormalizedBatchTree:
    app_name: str
    batch_name: str
    category: Optional[str] = None
    branch: Optional[str] = None
    semester: Optional[str] = None
    academic_year: Optional[str] = None
    thumbnail_url: Optional[str] = None
    format_detected: str = "legacy_appx"
    subjects: List[NormalizedSubject] = field(default_factory=list)
    total_lectures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TxtIndexer:
    """
    Dedicated indexer and normalizer for Course Wallah platform.
    Transforms heterogeneous batch formats into a standardized, deterministic hierarchy.
    """

    @classmethod
    def index_txt(
        cls,
        file_content: str,
        filename: str = "",
        app_name: str = "Course Wallah",
        batch_override: Optional[str] = None
    ) -> NormalizedBatchTree:
        detected_fmt = detect_txt_format(file_content)
        academic_course = parse_course_txt(file_content, filename)

        batch_name = batch_override or academic_course.course or "General Batch"
        subject_name = academic_course.subject or "Core Subject"

        tree = NormalizedBatchTree(
            app_name=app_name,
            batch_name=batch_name,
            format_detected=detected_fmt
        )

        # Check for thumbnail metadata from academic course or structured batch
        if getattr(academic_course, "thumbnail_url", None):
            tree.thumbnail_url = academic_course.thumbnail_url
        elif hasattr(academic_course, "structured_batch") and academic_course.structured_batch:
            sb = academic_course.structured_batch
            if getattr(sb, "thumbnail", None):
                tree.thumbnail_url = sb.thumbnail

        subject_map: Dict[str, NormalizedSubject] = {}
        lecture_counter = 1

        for unit in academic_course.units:
            unit_folder_name = unit.title or f"Unit {unit.number}"
            unit_num_str = f"Unit {unit.number}" if unit.number else None

            for item in unit.items:
                cur_subj_name = item.subject_name or subject_name
                if cur_subj_name not in subject_map:
                    subj_obj = NormalizedSubject(
                        name=cur_subj_name,
                        sort_order=len(subject_map) + 1
                    )
                    subject_map[cur_subj_name] = subj_obj

                active_subject = subject_map[cur_subj_name]

                # Find or create folder in active subject
                active_folder = None
                for f in active_subject.folders:
                    if f.name == unit_folder_name:
                        active_folder = f
                        break
                if not active_folder:
                    active_folder = NormalizedFolder(
                        name=unit_folder_name,
                        unit_number=unit_num_str,
                        sort_order=len(active_subject.folders) + 1
                    )
                    active_subject.folders.append(active_folder)

                # Classify media & provider
                url = item.url
                media_type = MediaRouter.classify_url(url, category_hint=item.category)
                provider_name = media_type.value.lower()

                # Separate Video vs PDF vs Image
                is_image = media_type == MediaType.DIRECT_IMAGE or item.category == "image" or any(url.lower().split("?")[0].endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"])
                is_pdf = media_type == MediaType.DIRECT_PDF or item.category == "pdf" or ".pdf" in url.lower()

                # If this item is a batch thumbnail header that was captured, save as tree thumbnail and skip creating a lecture
                if is_image and any(k in item.title.lower() for k in ("thumbnail", "batch image", "course image", "batch thumbnail")):
                    if not tree.thumbnail_url:
                        tree.thumbnail_url = url
                    continue

                if is_pdf:
                    video_url = None
                    pdf_url = url
                    category_name = "pdf"
                elif is_image:
                    video_url = None
                    pdf_url = None
                    category_name = "image"
                else:
                    video_url = url
                    pdf_url = getattr(item, "pdf_url", None)
                    category_name = "video"

                # Check if this item is a companion PDF for the previous video lecture with same/similar title
                paired = False
                if is_pdf and active_folder.lectures:
                    last_lec = active_folder.lectures[-1]
                    # If last lecture has video and no PDF, and titles correlate
                    if last_lec.video_url and not last_lec.pdf_url:
                        norm_last = normalize_title(last_lec.title)
                        norm_curr = normalize_title(item.title)
                        if norm_curr in norm_last or norm_last in norm_curr or "pdf" in norm_curr or "notes" in norm_curr:
                            last_lec.pdf_url = pdf_url
                            paired = True

                if not paired:
                    norm_lec = NormalizedLecture(
                        index=item.index or lecture_counter,
                        title=item.title,
                        video_url=video_url,
                        pdf_url=pdf_url,
                        provider=provider_name,
                        category=category_name,
                        raw_reference=item.raw_line,
                        extra_metadata={
                            "topic": item.topic_title,
                            "parent_folder": item.parent_folder,
                            "subfolder": item.subfolder,
                            "image_url": url if is_image else None
                        }
                    )
                    active_folder.lectures.append(norm_lec)
                    lecture_counter += 1

        tree.subjects = list(subject_map.values())
        tree.total_lectures = sum(
            len(f.lectures) for s in tree.subjects for f in s.folders
        )

        return tree

    @classmethod
    def parse_custom_mapping(
        cls,
        text: str,
        delimiter: str = ":",
        folder_pattern: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Interactive fallback mapping parser for ambiguous TXT files.
        Allows custom delimiter and structure definition.
        """
        results = []
        lines = text.splitlines()
        current_folder = "General"

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            if folder_pattern and re.match(folder_pattern, line_str, re.IGNORECASE):
                current_folder = line_str
                continue

            if delimiter in line_str:
                parts = line_str.split(delimiter, 1)
                title = parts[0].strip()
                url = parts[1].strip()
                results.append({
                    "folder": current_folder,
                    "title": title,
                    "url": url
                })

        return results
