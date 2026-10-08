import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Set

from parsers.academic_parser import (
    AcademicItem,
    AcademicTopic,
    AcademicUnit,
    AcademicCourse,
    normalize_title,
    classify_item_url
)
from providers.router import MediaRouter, MediaType

@dataclass
class StructuredContentItem:
    parent_folder: str
    topic: str
    title: str
    url: str
    media_type: str
    sequence: int
    raw_line: str
    unit_number: Optional[Any] = None

@dataclass
class StructuredBatch:
    batch_name: str = ""
    batch_id: str = ""
    instructor: str = ""
    thumbnail: str = ""
    price: str = ""
    start_date: str = ""
    end_date: str = ""
    generated_on: str = ""
    topic_summary: List[Dict[str, Any]] = field(default_factory=list)
    link_summary: Dict[str, Any] = field(default_factory=dict)
    content_items: List[StructuredContentItem] = field(default_factory=list)
    raw_header: str = ""

    def to_academic_course(self) -> AcademicCourse:
        return structured_batch_to_academic_course(self)

STRUCTURED_SECTION_PATTERNS = [
    re.compile(r"[-=─━\s]*BATCH\s+DETAILS[-=─━\s]*", re.IGNORECASE),
    re.compile(r"[-=─━\s]*TOPIC\s+SUMMARY[-=─━\s]*", re.IGNORECASE),
    re.compile(r"[-=─━\s]*LINK\s+SUMMARY[-=─━\s]*", re.IGNORECASE),
    re.compile(r"^CONTENT\s*:", re.IGNORECASE | re.MULTILINE),
]

STRUCTURED_FIELD_PATTERNS = [
    re.compile(r"(?:🌟|\*|-)?\s*Batch\s*:", re.IGNORECASE),
    re.compile(r"(?:🪪|\*|-)?\s*ID\s*:\s*\d+", re.IGNORECASE),
    re.compile(r"(?:👨🏫|👨‍🏫|\*|-)?\s*Instructor\s*:", re.IGNORECASE),
    re.compile(r"(?:📸|\*|-)?\s*Thumbnail\s*:\s*https?://", re.IGNORECASE),
    re.compile(r"Total\s+Number\s+of\s+Links\s*:", re.IGNORECASE),
    re.compile(r"Total\s+Videos\s*:", re.IGNORECASE),
    re.compile(r"Total\s+PDFs\s*:", re.IGNORECASE),
    re.compile(r"📁\s*[^|\n]+\|\|", re.IGNORECASE),
    re.compile(r"\[[^\]]+\]\s*\([^\)]+\)\s*Class", re.IGNORECASE),
]

LEGACY_PATTERNS = [
    re.compile(r"^(?:[▶✔✓★●▪⭐📌📚📖📁⚡\s\-*#]*)(?:UNIT|MODULE|CHAPTER|BLOCK)[\s\-_:]*(\d+(?:\.\d+)?)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:\[Subject\]|# Subject:|Subject:)", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^(?:\[Course\]|# Course:|Course:)", re.IGNORECASE | re.MULTILINE),
]

def detect_txt_format(text: str) -> str:
    if not text or not text.strip():
        return "unknown"

    from parsers.bracket_topic_parser import is_bracket_topic_format

    structured_score = 0
    for pat in STRUCTURED_SECTION_PATTERNS:
        if pat.search(text):
            structured_score += 2

    for pat in STRUCTURED_FIELD_PATTERNS:
        if pat.search(text):
            structured_score += 1

    if re.search(r"^CONTENT\s*:", text, re.IGNORECASE | re.MULTILINE):
        structured_score += 3

    if re.search(r"Careerwill", text, re.IGNORECASE):
        structured_score += 1

    if structured_score >= 3:
        return "structured_batch"

    if is_bracket_topic_format(text):
        return "bracket_topic"

    legacy_score = 0
    for pat in LEGACY_PATTERNS:
        if pat.search(text):
            legacy_score += 2

    has_urls = bool(re.search(r"https?://", text))
    if legacy_score >= 2 or has_urls:
        return "legacy_appx"
    else:
        return "unknown"

def sanitize_folder_name(name: str) -> str:
    if not name:
        return ""
    cleaned = name.strip()
    cleaned = re.sub(r"^[📁📂📌▶✔✓★●▪⭐⚡\s\-_:]+", "", cleaned)
    cleaned = re.sub(r"[📁📂📌▶✔✓★●▪⭐⚡\s\-_:]+$", "", cleaned).strip()
    cleaned = re.sub(r'[<>:"/\\|?*]', ' ', cleaned)
    cleaned = re.sub(r"\.\.+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    reserved = {
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    }
    if cleaned.upper() in reserved:
        cleaned = f"{cleaned}_folder"
    return cleaned

def extract_hierarchy_and_title(left_part: str) -> Tuple[str, str, str]:
    cleaned = left_part.strip()
    parent = ""
    topic = ""
    title = cleaned
    
    bracket_match = re.match(r"^\[(.*?)\]\s*(.*)$", cleaned)
    if bracket_match:
        parent = sanitize_folder_name(bracket_match.group(1))
        rem = bracket_match.group(2).strip()
        paren_match = re.match(r"^\((.*?)\)\s*(.*)$", rem)
        if paren_match:
            topic = sanitize_folder_name(paren_match.group(1))
            title = paren_match.group(2).strip()
        else:
            title = rem
    else:
        paren_match = re.match(r"^\((.*?)\)\s*(.*)$", cleaned)
        if paren_match:
            topic = sanitize_folder_name(paren_match.group(1))
            title = paren_match.group(2).strip()
            parent = topic

    title = re.sub(r"[\s:—\-]+$", "", title).strip()
    if not title:
        title = left_part.strip()
    return parent, topic, title

def parse_structured_batch_raw(file_content: str) -> StructuredBatch:
    batch = StructuredBatch()
    lines = file_content.splitlines()
    current_section = "HEADER"
    content_sequence = 1
    seen_content_keys: Set[Tuple[str, str]] = set()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if re.search(r"[-=─━\s]*BATCH\s+DETAILS[-=─━\s]*", line, re.I):
            current_section = "BATCH_DETAILS"
            continue
        elif re.search(r"[-=─━\s]*TOPIC\s+SUMMARY[-=─━\s]*", line, re.I):
            current_section = "TOPIC_SUMMARY"
            continue
        elif re.search(r"[-=─━\s]*LINK\s+SUMMARY[-=─━\s]*", line, re.I):
            current_section = "LINK_SUMMARY"
            continue
        elif re.search(r"[-=─━\s]*CONTENT(?:\s*[:\-]|\s*$)", line, re.I):
            current_section = "CONTENT"
            continue

        if current_section in ("HEADER", "BATCH_DETAILS"):
            m_batch = re.search(r"(?:🌟|\*|-)?\s*Batch\s*:\s*(.*)$", line, re.I)
            if m_batch and not batch.batch_name:
                batch.batch_name = m_batch.group(1).strip()
                continue
            m_id = re.search(r"(?:🪪|\*|-)?\s*ID\s*:\s*(.*)$", line, re.I)
            if m_id and not batch.batch_id:
                batch.batch_id = m_id.group(1).strip()
                continue
            m_inst = re.search(r"(?:👨🏫|👨‍🏫|\*|-)?\s*Instructor\s*:\s*(.*)$", line, re.I)
            if m_inst and not batch.instructor:
                batch.instructor = m_inst.group(1).strip()
                continue
            m_thumb = re.search(r"(?:📸|\*|-)?\s*Thumbnail\s*:\s*(https?://\S+)", line, re.I)
            if m_thumb and not batch.thumbnail:
                batch.thumbnail = m_thumb.group(1).strip()
                continue
            m_price = re.search(r"(?:💰|\*|-)?\s*Price\s*:\s*(.*)$", line, re.I)
            if m_price and not batch.price:
                batch.price = m_price.group(1).strip()
                continue
            m_start = re.search(r"(?:📅|\*|-)?\s*Start\s*Date\s*:\s*(.*)$", line, re.I)
            if m_start and not batch.start_date:
                batch.start_date = m_start.group(1).strip()
                continue
            m_end = re.search(r"(?:📅|\*|-)?\s*End\s*Date\s*:\s*(.*)$", line, re.I)
            if m_end and not batch.end_date:
                batch.end_date = m_end.group(1).strip()
                continue
            m_gen = re.search(r"(?:🕒|\*|-)?\s*Generated\s*(?:On|At)\s*:\s*(.*)$", line, re.I)
            if m_gen and not batch.generated_on:
                batch.generated_on = m_gen.group(1).strip()
                continue

        if current_section == "TOPIC_SUMMARY":
            clean_tline = re.sub(r"^[📁📂📌▶✔✓★●▪⭐⚡\s\-_:]+", "", line).strip()
            if "||" in clean_tline:
                p_part, sub_part = clean_tline.split("||", 1)
                parent_name = sanitize_folder_name(p_part)
                count = 0
                topic_name = ""
                if ":" in sub_part:
                    t_part, c_part = sub_part.split(":", 1)
                    topic_name = sanitize_folder_name(t_part)
                    c_match = re.search(r"(\d+)", c_part)
                    if c_match:
                        count = int(c_match.group(1))
                else:
                    topic_name = sanitize_folder_name(sub_part)
                batch.topic_summary.append({
                    "parent": parent_name,
                    "topic": topic_name,
                    "count": count,
                    "raw": line
                })
                continue
            elif ":" in clean_tline and not clean_tline.lower().startswith("http"):
                p_part, c_part = clean_tline.split(":", 1)
                parent_name = sanitize_folder_name(p_part)
                c_match = re.search(r"(\d+)", c_part)
                count = int(c_match.group(1)) if c_match else 0
                batch.topic_summary.append({
                    "parent": parent_name,
                    "topic": "",
                    "count": count,
                    "raw": line
                })
                continue

        if current_section == "LINK_SUMMARY":
            if "Total Number of Links" in line or "Total Links" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    batch.link_summary["total_links"] = int(m.group(1))
            elif "Total Videos" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    batch.link_summary["total_videos"] = int(m.group(1))
            elif ".m3u8" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    batch.link_summary["total_m3u8"] = int(m.group(1))
            elif ".mpd" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    batch.link_summary["total_mpd"] = int(m.group(1))
            elif "Youtube" in line or "YouTube" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    batch.link_summary["total_youtube"] = int(m.group(1))
            elif "Total PDFs" in line or "Total PDF" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    batch.link_summary["total_pdfs"] = int(m.group(1))
            continue

        thumb_match = re.search(r"^(?:[📸📷🖼️★●▪⭐📌📚📖📁⚡\s\-*#]*|\[)?(?:Thumbnail|Thumb|Batch\s*Thumbnail|Course\s*Thumbnail)(?:\])?[\s\-_:]*(https?://\S+)", line, re.I)
        if thumb_match:
            if not batch.thumbnail:
                batch.thumbnail = thumb_match.group(1).strip()
            continue

        url_match = re.search(r"(https?://\S+)", line)
        if url_match:
            full_url = url_match.group(1).strip()
            left_part = line[:url_match.start()].strip()
            
            p_folder, topic_title, item_title = extract_hierarchy_and_title(left_part)
            
            if not p_folder and topic_title:
                for ts in batch.topic_summary:
                    if ts["topic"].lower() == topic_title.lower() and ts["parent"]:
                        p_folder = ts["parent"]
                        break
            
            if not p_folder:
                p_folder = batch.batch_name or "General"

            dedup_key = (full_url, item_title)
            if dedup_key in seen_content_keys:
                continue
            seen_content_keys.add(dedup_key)

            m_type = classify_item_url(full_url)
            
            item = StructuredContentItem(
                parent_folder=p_folder,
                topic=topic_title,
                title=item_title,
                url=full_url,
                media_type=m_type,
                sequence=content_sequence,
                raw_line=line
            )
            batch.content_items.append(item)
            content_sequence += 1

    return batch

def structured_batch_to_academic_course(batch: StructuredBatch) -> AcademicCourse:
    course_name = batch.batch_name or "Structured Batch Course"
    subject_name = batch.instructor or "Careerwill"

    course_obj = AcademicCourse(
        subject=subject_name,
        course=course_name,
        thumbnail_url=batch.thumbnail
    )
    setattr(course_obj, "format_type", "structured_batch")
    setattr(course_obj, "structured_batch", batch)

    unit_map: Dict[Tuple[str, str], AcademicUnit] = {}
    unit_list: List[AcademicUnit] = []
    unit_counter = 1

    for item in batch.content_items:
        p_folder = item.parent_folder or course_name
        topic = item.topic or ""
        group_key = (p_folder, topic)

        if group_key not in unit_map:
            if topic:
                unit_title = f"{p_folder} — {topic}"
                display_hdr = f"📌 {p_folder.upper()} — {topic.upper()}"
                norm_key = f"{normalize_title(p_folder)}_{normalize_title(topic)}"
            else:
                unit_title = p_folder
                display_hdr = f"📌 {p_folder.upper()}"
                norm_key = normalize_title(p_folder)

            acad_unit = AcademicUnit(
                number=unit_counter,
                title=unit_title,
                normalized_key=norm_key,
                display_header=display_hdr
            )
            unit_counter += 1
            unit_map[group_key] = acad_unit
            unit_list.append(acad_unit)

        target_unit = unit_map[group_key]
        url_no_scheme = re.sub(r"^https?://", "", item.url)

        acad_item = AcademicItem(
            raw_line=item.raw_line,
            index=item.sequence,
            title=item.title,
            url=item.url,
            url_without_scheme=url_no_scheme,
            category=item.media_type,
            unit_number=target_unit.number,
            unit_title=target_unit.title,
            topic_title=topic or None,
            course_name=course_name,
            subject_name=p_folder,
            parent_folder=p_folder,
            subfolder=topic
        )
        target_unit.items.append(acad_item)
        course_obj.all_items.append(acad_item)

    course_obj.units = unit_list
    return course_obj

def parse_structured_batch_txt(file_content: str, filename: str = "") -> AcademicCourse:
    raw_batch = parse_structured_batch_raw(file_content)
    if not raw_batch.batch_name and filename:
        base = os.path.splitext(os.path.basename(filename))[0]
        base_clean = re.sub(r"^\d+[\s\-_]+", "", base).strip().replace("_", " ")
        raw_batch.batch_name = base_clean
    return raw_batch.to_academic_course()
