import html
from typing import Optional, Dict, Any


def format_telegram_channel_caption(
    title: str,
    metadata: Optional[Dict[str, Any]] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    resolution: Optional[str] = None,
) -> str:
    """
    Formats a video caption for Telegram storage channel matching Course Wallah's
    signature blockquote aesthetic template.

    Template breakdown:
    <blockquote>——— ✦ 009 ✦——— ❞</blockquote>

    <blockquote>📚 Subject Name ❞</blockquote>
    <blockquote>📖 Batch Name ❞</blockquote>
    <blockquote>📌 Unit / Section ❞</blockquote>

    <blockquote>📝 Topic : Topic Name ❞</blockquote>

    <blockquote>🎬 Title : ) Lecture Title ❞</blockquote>

    <blockquote>├── Extention : ∮◯⚡ Course Wallah 🎓 🔥.mp4 ❞
    ├── Resolution : 720p (1280 × 720)</blockquote>

    <blockquote>📚 Subject » Subject Name ❞</blockquote>
    <blockquote>📚 Course » Batch Name ❞</blockquote>

    <blockquote>🌟 Extracted By : ∮◯⚡ 🅲🅾🆄🆁🆂🅴 🆆🅰🅻🅻🅰🅷 💻 ❞
    ∮◯🎓🔥</blockquote>
    """
    meta = metadata or {}

    # 1. Lecture Index formatting (3-digit e.g. 009 or 001)
    idx = meta.get("lecture_index") or meta.get("index") or 1
    try:
        idx_num = int(idx)
        idx_str = f"{idx_num:03d}"
    except (ValueError, TypeError):
        idx_str = str(idx)[:10]

    # 2. Subject & Batch
    subject_raw = (
        meta.get("subject_name")
        or meta.get("subject")
        or "Course Wallah Special"
    )
    batch_raw = (
        meta.get("batch_name")
        or meta.get("batch")
        or meta.get("course")
        or "Course Wallah Batch"
    )

    # 3. Unit & Topic
    folder_raw = (
        meta.get("folder_name")
        or meta.get("folder")
        or meta.get("unit")
        or "Lectures"
    )
    unit_num = meta.get("unit_number")
    if unit_num and not folder_raw.lower().startswith("unit"):
        unit_raw = f"Unit {unit_num} — {folder_raw}"
    else:
        unit_raw = folder_raw

    topic_raw = meta.get("topic_name") or meta.get("topic") or folder_raw

    # Clean strings and safely escape HTML entities
    title_clean = str(title).strip() if title else "Video Lecture"
    # Remove leading numbering if duplicated like "001 - Title"
    clean_title_no_num = title_clean
    if clean_title_no_num.startswith(f"{idx} ") or clean_title_no_num.startswith(f"{idx:03d} "):
        clean_title_no_num = clean_title_no_num.split(" ", 1)[-1].strip()

    title_esc = html.escape(clean_title_no_num)
    subject_esc = html.escape(str(subject_raw).strip())
    batch_esc = html.escape(str(batch_raw).strip())
    unit_esc = html.escape(str(unit_raw).strip())
    topic_esc = html.escape(str(topic_raw).strip())

    # 4. Dimensions & Resolution
    w = width or meta.get("width")
    h = height or meta.get("height")
    raw_res = resolution or meta.get("resolution") or (f"{h}p" if h else "720p")
    raw_res_str = str(raw_res).lower()

    if not w or not h:
        if "1080" in raw_res_str:
            w, h = 1920, 1080
            res_label = "1080p"
        elif "720" in raw_res_str:
            w, h = 1280, 720
            res_label = "720p"
        elif "480" in raw_res_str:
            w, h = 854, 480
            res_label = "480p"
        elif "360" in raw_res_str or "240" in raw_res_str:
            w, h = 640, 360
            res_label = "360p"
        else:
            w, h = 1280, 720
            res_label = "720p"
    else:
        res_label = f"{h}p" if not raw_res_str.endswith("p") else raw_res_str

    # 5. Build full caption
    def _build_caption(t_esc: str, s_esc: str, b_esc: str, u_esc: str, top_esc: str) -> str:
        lines = [
            f"<blockquote>——— ✦ {idx_str} ✦——— ❞</blockquote>",
            "",
            f"<blockquote>📚 {s_esc} ❞</blockquote>",
            f"<blockquote>📖 {b_esc} ❞</blockquote>",
            f"<blockquote>📌 {u_esc} ❞</blockquote>",
            "",
            f"<blockquote>📝 Topic : {top_esc} ❞</blockquote>",
            "",
            f"<blockquote>🎬 Title : ) {t_esc} ❞</blockquote>",
            "",
            f"<blockquote>├── Extention : ∮◯⚡ Course Wallah 🎓 🔥.mp4 ❞\n├── Resolution : {res_label} ({w} × {h})</blockquote>",
            "",
            f"<blockquote>📚 Subject » {s_esc} ❞</blockquote>",
            f"<blockquote>📚 Course » {b_esc} ❞</blockquote>",
            "",
            "<blockquote>🌟 Extracted By : ∮◯⚡ 🅲🅾🆄🆁🆂🅴 🆆🅰🅻🅻🅰🅷 💻 ❞\n∮◯🎓🔥</blockquote>",
        ]
        return "\n".join(lines)

    full_caption = _build_caption(title_esc, subject_esc, batch_esc, unit_esc, topic_esc)

    # Telegram hard limit for captions is 1024 characters. Ensure within 1020 chars.
    if len(full_caption) > 1020:
        excess = len(full_caption) - 1020 + 5
        truncated_title = title_esc[:-excess] + "..." if len(title_esc) > excess else title_esc[:20] + "..."
        full_caption = _build_caption(truncated_title, subject_esc, batch_esc, unit_esc, topic_esc)

    return full_caption
