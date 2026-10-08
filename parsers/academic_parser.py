import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple

from config.settings import BOT_NAME

@dataclass
class AcademicItem:
    raw_line: str
    index: int                  # 1-based sequential or parsed index (e.g. 35)
    title: str                  # Clean title
    url: str                    # Full URL (with https:// or http://)
    url_without_scheme: str     # URL without '://'
    category: str               # 'video', 'pdf', 'image', 'zip', 'audio', 'html', 'other'
    unit_number: Optional[Any] = None
    unit_title: Optional[str] = None
    topic_title: Optional[str] = None
    course_name: Optional[str] = None
    subject_name: Optional[str] = None
    parent_folder: Optional[str] = None
    subfolder: Optional[str] = None
    pdf_url: Optional[str] = None

@dataclass
class AcademicTopic:
    title: str
    items: List[AcademicItem] = field(default_factory=list)

@dataclass
class AcademicUnit:
    number: Any                 # 1, 2, "1.1", "General", etc.
    title: str                  # "Logic and Proof Techniques"
    normalized_key: str         # Stable key: "mathematics_unit_1_logic_and_proof_techniques"
    display_header: str         # "📌 UNIT 1 — LOGIC AND PROOF TECHNIQUES"
    topics: List[AcademicTopic] = field(default_factory=list)
    items: List[AcademicItem] = field(default_factory=list)
    topic_thread_id: Optional[int] = None
    header_message_id: Optional[int] = None
    status_message_id: Optional[int] = None

@dataclass
class AcademicCourse:
    subject: str
    course: str
    units: List[AcademicUnit] = field(default_factory=list)
    all_items: List[AcademicItem] = field(default_factory=list)
    format_type: str = "legacy_appx"
    structured_batch: Optional[Any] = None
    thumbnail_url: Optional[str] = None

SUBJECT_MAP = {
    "math": "Mathematics",
    "maths": "Mathematics",
    "mathematics": "Mathematics",
    "cs": "Computer Science",
    "cse": "Computer Science",
    "it": "Information Technology",
    "ee": "Electrical Engineering",
    "ece": "Electronics and Communication Engineering",
    "me": "Mechanical Engineering",
    "ce": "Civil Engineering",
    "phy": "Physics",
    "physics": "Physics",
    "chem": "Chemistry",
    "chemistry": "Chemistry",
    "bio": "Biology",
    "biology": "Biology",
    "os": "Operating Systems",
    "cn": "Computer Networks",
    "dbms": "Database Management Systems",
    "toc": "Theory of Computation",
    "cd": "Compiler Design",
    "coa": "Computer Organization and Architecture",
    "cao": "Computer Architecture and Organization",
    "ds": "Discrete Structures",
    "dsa": "Data Structures and Algorithms",
    "ai": "Artificial Intelligence",
    "ml": "Machine Learning",
}

UNIT_REGEX = re.compile(
    r"^(?:[▶✔✓★●▪⭐📌📚📖📁⚡\s\-*#]*)(?:UNIT|Unit|unit|MODULE|Module|module|CHAPTER|Chapter|chapter|BLOCK|Block|block)[\s\-_:]*(\d+(?:\.\d+)?)[\s\-_:.]*(.*?)(?:[▶✔✓★●▪⭐📌📚📖📁⚡\s]*)$"
)

TOPIC_REGEX = re.compile(
    r"^(?:[▶✔✓★●▪⭐📌📚📖📁⚡\s\-*#]*)(?:TOPIC|Topic|topic|SECTION|Section|section)[\s\-_:]*(.*?)(?:[▶✔✓★●▪⭐📌📚📖📁⚡\s]*)$"
)

def normalize_title(title: str) -> str:
    """Normalize title for matching/keys: lowercase, alphanumeric and underscores only."""
    if not title:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", str(title).lower())
    return "_".join(cleaned.split())

def detect_subject_and_course(filename: str, first_lines: Optional[List[str]] = None) -> Tuple[str, str]:
    base = os.path.splitext(os.path.basename(filename))[0] if filename else ""
    base_clean = re.sub(r"^\d+[\s\-_]+", "", base).strip()
    
    subject = ""
    course = ""
    
    paren_match = re.search(r"^(.*?)\((.*?)\)$", base_clean)
    if paren_match:
        c_part = paren_match.group(1).replace("_", " ").strip()
        s_part = paren_match.group(2).replace("_", " ").strip()
        course = c_part
        subject = SUBJECT_MAP.get(s_part.lower(), s_part.title())
    elif " - " in base_clean or " _ " in base_clean:
        parts = [p.strip() for p in re.split(r"[\-_]+", base_clean) if p.strip()]
        if len(parts) >= 2:
            p0_mapped = SUBJECT_MAP.get(parts[0].lower())
            p1_mapped = SUBJECT_MAP.get(parts[-1].lower())
            if p0_mapped:
                subject = p0_mapped
                course = " ".join(parts[1:])
            elif p1_mapped:
                subject = p1_mapped
                course = " ".join(parts[:-1])
            else:
                course = " ".join(parts)
                subject = course
        else:
            course = base_clean.replace("_", " ")
            subject = course
    else:
        course = base_clean.replace("_", " ") if base_clean else "General Course"
        subject = course

    if first_lines:
        for line in first_lines[:5]:
            l_str = line.strip()
            if l_str.startswith(("[Subject]", "# Subject:", "Subject:", "# SUBJECT:", "SUBJECT:")):
                subject = l_str.split(":", 1)[1].strip() if ":" in l_str else l_str.replace("[Subject]", "").strip()
            elif l_str.startswith(("[Course]", "# Course:", "Course:", "# COURSE:", "COURSE:")):
                course = l_str.split(":", 1)[1].strip() if ":" in l_str else l_str.replace("[Course]", "").strip()

    if not subject:
        subject = course if course else "General Studies"
    if not course:
        course = subject

    UPPER_ACRONYMS = {"os", "cs", "it", "ee", "ece", "me", "ce", "ds", "dsa", "ai", "ml", "dbms", "cn", "toc", "cd", "coa", "cao", "sql", "html", "css", "js", "ts", "php", "c", "cpp"}
    
    def format_title_words(text: str) -> str:
        words = text.split()
        res = []
        for w in words:
            if w.lower() in UPPER_ACRONYMS:
                res.append(w.upper())
            else:
                res.append(w.capitalize())
        return " ".join(res)

    course = format_title_words(course)
    subject = format_title_words(subject)
    return subject, course

def classify_item_url(url: str) -> str:
    url_lower = url.lower()
    if ".pdf" in url_lower or "utkarshapp.com/admin_v1/file_manager/pdf" in url_lower or "file_manager/pdf" in url_lower:
        return "pdf"
    elif any(url_lower.endswith(ext) or ext in url_lower for ext in [".jpg", ".jpeg", ".png", ".webp"]):
        return "image"
    elif "zip" in url_lower:
        return "zip"
    elif any(url_lower.endswith(ext) or ext in url_lower for ext in [".mp3", ".wav", ".m4a", ".audio"]):
        return "audio"
    elif ".ws" in url_lower or ".html" in url_lower:
        return "html"
    elif any(x in url_lower for x in ["youtu", "m3u8", "mpd", "fetch_video", "v2", "drm", "stream", "video", ".mp4", ".mkv"]):
        return "video"
    return "video"

def parse_academic_txt(file_content: str, filename: str = "") -> AcademicCourse:
    lines = [line.strip() for line in file_content.splitlines() if line.strip()]
    subject, course = detect_subject_and_course(filename, lines)
    
    course_obj = AcademicCourse(subject=subject, course=course)
    
    general_unit = AcademicUnit(
        number=0,
        title="General",
        normalized_key=f"{normalize_title(subject)}_general",
        display_header=f"📁 GENERAL — {subject.upper()}"
    )
    
    current_unit: Optional[AcademicUnit] = None
    current_topic_title: Optional[str] = None
    current_subject: str = subject
    item_counter = 1

    for line in lines:
        l_str = line.strip()
        if l_str.startswith(("[Subject]", "# Subject:", "Subject:", "# SUBJECT:", "SUBJECT:")):
            raw_s = l_str.split(":", 1)[1].strip() if ":" in l_str else l_str.replace("[Subject]", "").strip()
            if raw_s:
                current_subject = SUBJECT_MAP.get(raw_s.lower(), raw_s.title())
                current_unit = None
                continue
        elif l_str.startswith(("[Course]", "# Course:", "Course:", "# COURSE:", "COURSE:")):
            raw_c = l_str.split(":", 1)[1].strip() if ":" in l_str else l_str.replace("[Course]", "").strip()
            if raw_c:
                course = raw_c
                continue

        # Check for batch thumbnail header line
        thumb_match = re.search(r"^(?:[📸📷🖼️★●▪⭐📌📚📖📁⚡\s\-*#]*|\[)?(?:Thumbnail|Thumb|Batch\s*Thumbnail|Course\s*Thumbnail)(?:\])?[\s\-_:]*(https?://\S+)", l_str, re.IGNORECASE)
        if thumb_match:
            course_obj.thumbnail_url = thumb_match.group(1).strip()
            continue

        urls = re.findall(r"https?://[^\s\)\>]+", line)
        if urls:
            full_url = urls[0].strip()
            pdf_url = urls[1].strip() if len(urls) > 1 and (".pdf" in urls[1].lower() or "file_manager" in urls[1].lower() or len(urls) == 2) else None
            first_url_pos = line.find(full_url)
            title_part = line[:first_url_pos].strip() if first_url_pos != -1 else ""
            title_part = re.sub(r"[\s:—\-]+$", "", title_part).strip()

            idx_match = re.match(r"^(\d+)[\.\s\-_:]+(.*)$", title_part)
            if idx_match:
                item_idx = int(idx_match.group(1))
                item_title = idx_match.group(2).strip() or title_part
            else:
                item_idx = item_counter
                item_title = title_part

            if not item_title:
                item_title = f"Item {item_idx}"

            url_no_scheme = re.sub(r"^https?://", "", full_url)
            category = classify_item_url(full_url)

            target_unit = current_unit if current_unit is not None else general_unit

            item = AcademicItem(
                raw_line=line,
                index=item_idx,
                title=item_title,
                url=full_url,
                url_without_scheme=url_no_scheme,
                category=category,
                unit_number=target_unit.number if target_unit.number != 0 else None,
                unit_title=target_unit.title,
                topic_title=current_topic_title,
                course_name=course,
                subject_name=current_subject,
                pdf_url=pdf_url
            )

            if current_topic_title and target_unit.topics:
                target_unit.topics[-1].items.append(item)

            target_unit.items.append(item)
            course_obj.all_items.append(item)
            item_counter += 1
            continue

        unit_match = UNIT_REGEX.match(line)
        if unit_match:
            num_str, u_title = unit_match.groups()
            u_title = u_title.strip()
            u_title = re.sub(r"^[▶✔✓★●▪⭐📌📚📖📁⚡\s\-_:]+", "", u_title)
            u_title = re.sub(r"[▶✔✓★●▪⭐📌📚📖📁⚡\s\-_:]+$", "", u_title).strip()
            
            try:
                num_f = float(num_str)
                u_num = int(num_f) if num_f.is_integer() else num_f
            except ValueError:
                u_num = num_str
                
            if not u_title:
                u_title = f"Unit {u_num}"
                
            norm_key = f"{normalize_title(subject)}_unit_{u_num}_{normalize_title(u_title)}"
            display_hdr = f"📌 UNIT {u_num} — {u_title.upper()}"
            
            current_unit = AcademicUnit(
                number=u_num,
                title=u_title,
                normalized_key=norm_key,
                display_header=display_hdr
            )
            course_obj.units.append(current_unit)
            current_topic_title = None
            continue

        topic_match = TOPIC_REGEX.match(line)
        if topic_match:
            t_title = topic_match.group(1).strip()
            t_title = re.sub(r"^[▶✔✓★●▪⭐📌📚📖📁⚡\s\-_:]+", "", t_title)
            t_title = re.sub(r"[▶✔✓★●▪⭐📌📚📖📁⚡\s\-_:]+$", "", t_title).strip()
            if t_title:
                current_topic_title = t_title
                if current_unit is not None:
                    topic_obj = AcademicTopic(title=t_title)
                    current_unit.topics.append(topic_obj)
            continue

    if general_unit.items:
        course_obj.units.insert(0, general_unit)

    return course_obj

def parse_course_txt(file_content: str, filename: str = "") -> AcademicCourse:
    """
    Unified router that detects format and parses appropriately.
    """
    from parsers.structured_batch_parser import detect_txt_format, parse_structured_batch_txt
    from parsers.bracket_topic_parser import parse_bracket_topic_txt
    fmt = detect_txt_format(file_content)
    if fmt == "structured_batch":
        return parse_structured_batch_txt(file_content, filename)
    elif fmt == "bracket_topic":
        return parse_bracket_topic_txt(file_content, filename)
    else:
        return parse_academic_txt(file_content, filename)

