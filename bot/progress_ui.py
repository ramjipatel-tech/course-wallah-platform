import time
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from pyrogram.errors import FloodWait, MessageNotModified, RPCError

logger = logging.getLogger(__name__)

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

def get_spinner(index: int = 0) -> str:
    return SPINNER_FRAMES[index % len(SPINNER_FRAMES)]

def make_progress_bar(percent: float, bar_length: int = 10, style: str = "blocks") -> str:
    """
    Generates an authentic Unicode progress bar.
    style='blocks': [██████□□□□]
    style='smooth': [██████░░░░]
    """
    pct = max(0.0, min(100.0, float(percent)))
    filled = int(round(bar_length * pct / 100))
    empty = max(0, bar_length - filled)
    
    if style == "blocks":
        return "█" * filled + "□" * empty
    return "█" * filled + "░" * empty

class TelegramMessageThrottler:
    """
    Guarantees rate-limited single-message updates for Telegram.
    Throttles edits to ~1.5 - 2.0s, handles FloodWait, and suppresses duplicate edits.
    """
    def __init__(self, min_interval: float = 1.6):
        self.min_interval = min_interval
        self.last_edit_time = 0.0
        self._lock = asyncio.Lock()
        self.last_text = ""

    async def edit(self, message, text: str, reply_markup=None, force: bool = False) -> bool:
        async with self._lock:
            now = time.time()
            if not force and (now - self.last_edit_time < self.min_interval):
                return False
            
            # Telegram strict limit safety
            if len(text) > 3800:
                text = text[:3700] + "\n\n<i>[Content truncated for length]</i>"

            if text == self.last_text and reply_markup is None:
                return False

            try:
                if reply_markup is not None:
                    await message.edit_text(text, reply_markup=reply_markup)
                else:
                    await message.edit_text(text)
                self.last_edit_time = time.time()
                self.last_text = text
                return True
            except FloodWait as e:
                logger.warning(f"[TELEGRAM THROTTLER] FloodWait: sleeping {e.value}s")
                await asyncio.sleep(e.value)
                try:
                    await message.edit_text(text, reply_markup=reply_markup)
                    self.last_edit_time = time.time()
                    self.last_text = text
                    return True
                except Exception:
                    return False
            except MessageNotModified:
                self.last_text = text
                return True
            except RPCError as e:
                logger.debug(f"[TELEGRAM THROTTLER] RPC notice: {e}")
                return False
            except Exception as e:
                logger.debug(f"[TELEGRAM THROTTLER] Edit exception: {e}")
                return False


class TelegramProgressUI:
    """
    Central Presentation & Animation Engine for Course Wallah Platform.
    Renders rich, premium, rate-limited UI cards for welcome screens,
    admin dashboard, batch wizard steps, live pipeline monitoring, and summaries.
    """

    # ==========================================
    # WELCOME, HELP & ID SCREENS
    # ==========================================

    @classmethod
    def render_welcome_screen(cls, first_name: str, is_admin: bool) -> str:
        if is_admin:
            return (
                f"🎓 <b>COURSE WALLAH</b>\n\n"
                f"Welcome to Course Wallah.\n\n"
                f"Manage your educational content directly from Telegram.\n\n"
                f"<b>Choose an action:</b>"
            )
        else:
            return (
                f"🎓 <b>COURSE WALLAH</b>\n\n"
                f"Welcome.\n\n"
                f"Your account does not have administrator access to batch management.\n\n"
                f"Use /help to see available commands."
            )

    @classmethod
    def render_help_screen(cls, is_admin: bool) -> str:
        if is_admin:
            return (
                f"🎓 <b>COURSE WALLAH HELP & COMMANDS</b>\n\n"
                f"<b>General Commands:</b>\n"
                f"• /start — Welcome screen & actions\n"
                f"• /help — Show help & command reference\n"
                f"• /id — Show your Telegram ID & authorization\n\n"
                f"<b>👑 Administrator Commands:</b>\n"
                f"• /admin — Open complete Admin Dashboard\n"
                f"• /batch or /uploadbatch — Start TXT Batch Upload Wizard\n"
                f"• /batchstatus — View current batch processing status\n"
                f"• /batchjobs — View recent database batches & jobs\n"
                f"• /batchretry — Reprocess failed lectures in active batch\n"
                f"• /batchresume — Resume paused or interrupted batch\n"
                f"• /batchpause — Safely pause current batch\n"
                f"• /batchcancel — Cancel current batch with scratch cleanup\n"
                f"• /batchlogs — Show operational processing logs"
            )
        else:
            return (
                f"🎓 <b>COURSE WALLAH HELP</b>\n\n"
                f"<b>Available Commands:</b>\n"
                f"• /start — Welcome menu\n"
                f"• /help — Show this help menu\n"
                f"• /id — Show your Telegram ID"
            )

    @classmethod
    def render_id_screen(cls, user_id: int, is_admin: bool, bot_username: str) -> str:
        admin_str = "✅ YES (Administrator)" if is_admin else "❌ NO (Standard User)"
        return (
            f"🆔 <b>YOUR TELEGRAM ID</b>\n\n"
            f"<code>{user_id}</code>\n\n"
            f"<b>Admin Access:</b> {admin_str}\n"
            f"<b>Bot:</b> {bot_username}"
        )

    # ==========================================
    # ADMIN DASHBOARD
    # ==========================================

    @classmethod
    def render_admin_dashboard(cls, stats: Dict[str, Any]) -> str:
        active_apps = stats.get("active_apps", 0)
        total_batches = stats.get("total_batches", 0)
        total_lectures = stats.get("total_lectures", 0)
        active_jobs = stats.get("active_jobs", 0)

        return (
            f"╭━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            f"      👑 <b>COURSE WALLAH ADMIN</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"<b>System Status:</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🟢 <b>Bot:</b> ONLINE\n"
            f"🟢 <b>Worker:</b> ONLINE ({active_jobs} Active)\n"
            f"🟢 <b>Database:</b> ONLINE ({active_apps} Apps, {total_batches} Batches)\n"
            f"🟢 <b>API:</b> ONLINE\n\n"
            f"<b>Choose an action:</b>"
        )

    # ==========================================
    # BATCH UPLOAD WIZARD SCREENS
    # ==========================================

    @classmethod
    def render_batch_start(cls, step: int, percent: int, label: str) -> str:
        bar = make_progress_bar(percent, bar_length=10, style="blocks")
        return (
            f"🚀 <b>INITIALIZING BATCH UPLOADER</b>\n\n"
            f"[{bar}] {percent}%\n\n"
            f"{label}"
        )

    @classmethod
    def render_analysis(cls, stats: Dict[str, Any]) -> str:
        filename = stats.get("filename", "course_links.txt")
        batch_name = stats.get("batch_name", "Academic Batch")
        total = stats.get("total_lectures", 0)
        videos = stats.get("video_count", 0)
        pdfs = stats.get("pdf_count", 0)
        combo = stats.get("combo_count", 0)
        units = stats.get("unit_count", 0)
        subjects = stats.get("subject_count", 0)
        new_count = stats.get("new_count", total)
        existing_count = stats.get("already_processed_count", 0)
        invalid_count = stats.get("invalid_count", 0)

        return (
            f"📄 <b>TXT ANALYSIS COMPLETE</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📄 <b>File:</b>\n"
            f"<code>{filename}</code>\n\n"
            f"📚 <b>Detected content:</b>\n"
            f"• Lectures: <b>{total}</b>\n"
            f"• Subjects: <b>{subjects}</b>\n"
            f"• Folders: <b>{units}</b>\n"
            f"• Videos: <b>{videos}</b>\n"
            f"• PDFs: <b>{pdfs}</b>\n"
            f"• Combo (Video+PDF): <b>{combo}</b>\n\n"
            f"<b>Choose where this content should go:</b>"
        )

    @classmethod
    def render_existing_app_found(cls, app_name: str, stats: Dict[str, Any]) -> str:
        total = stats.get("total_lectures", 0)
        videos = stats.get("video_count", 0)
        pdfs = stats.get("pdf_count", 0)
        units = stats.get("unit_count", 0)
        subjects = stats.get("subject_count", 0)

        return (
            f"🎓 <b>EXISTING APP FOUND</b>\n\n"
            f"<b>App:</b>\n"
            f"<b>{app_name}</b>\n\n"
            f"<b>Detected Content:</b>\n"
            f"• Lectures: <b>{total}</b>\n"
            f"• Subjects: <b>{subjects}</b>\n"
            f"• Folders: <b>{units}</b>\n"
            f"• Videos: <b>{videos}</b>\n"
            f"• PDFs: <b>{pdfs}</b>\n\n"
            f"<i>Choose whether to use this App or select/create another:</i>"
        )

    @classmethod
    def render_app_not_found(cls, detected_app_name: str, stats: Dict[str, Any]) -> str:
        total = stats.get("total_lectures", 0)
        videos = stats.get("video_count", 0)
        pdfs = stats.get("pdf_count", 0)
        units = stats.get("unit_count", 0)
        subjects = stats.get("subject_count", 0)

        return (
            f"📱 <b>APP NOT FOUND</b>\n\n"
            f"<b>Detected App:</b>\n"
            f"<b>{detected_app_name}</b>\n\n"
            f"<b>Detected Content:</b>\n"
            f"• Lectures: <b>{total}</b>\n"
            f"• Subjects: <b>{subjects}</b>\n"
            f"• Folders: <b>{units}</b>\n"
            f"• Videos: <b>{videos}</b>\n"
            f"• PDFs: <b>{pdfs}</b>\n\n"
            f"<i>Create a new App for this content or select an existing one:</i>"
        )

    @classmethod
    def render_existing_batch_found(cls, batch_name: str, stats: Dict[str, Any]) -> str:
        total = stats.get("total_lectures", 0)
        videos = stats.get("video_count", 0)
        pdfs = stats.get("pdf_count", 0)
        units = stats.get("unit_count", 0)
        subjects = stats.get("subject_count", 0)

        return (
            f"📦 <b>EXISTING BATCH FOUND</b>\n\n"
            f"<b>Batch:</b>\n"
            f"<b>{batch_name}</b>\n\n"
            f"<b>Detected Content:</b>\n"
            f"• Lectures: <b>{total}</b>\n"
            f"• Subjects: <b>{subjects}</b>\n"
            f"• Folders: <b>{units}</b>\n"
            f"• Videos: <b>{videos}</b>\n"
            f"• PDFs: <b>{pdfs}</b>\n\n"
            f"<i>Choose whether to use this Batch or create a new one:</i>"
        )

    @classmethod
    def render_new_batch_prompt(cls, detected_batch_name: str, stats: Dict[str, Any]) -> str:
        total = stats.get("total_lectures", 0)
        videos = stats.get("video_count", 0)
        pdfs = stats.get("pdf_count", 0)
        units = stats.get("unit_count", 0)
        subjects = stats.get("subject_count", 0)

        return (
            f"📦 <b>NEW BATCH</b>\n\n"
            f"<b>Detected:</b>\n"
            f"<b>{detected_batch_name}</b>\n\n"
            f"<b>Detected Content:</b>\n"
            f"• Lectures: <b>{total}</b>\n"
            f"• Subjects: <b>{subjects}</b>\n"
            f"• Folders: <b>{units}</b>\n"
            f"• Videos: <b>{videos}</b>\n"
            f"• PDFs: <b>{pdfs}</b>\n\n"
            f"<i>Create this batch or select an existing batch:</i>"
        )

    @classmethod
    def render_app_selection(cls, apps: List[Any]) -> str:
        count = len(apps)
        return (
            f"📱 <b>SELECT EXISTING APP</b>\n\n"
            f"Found <b>{count}</b> registered App(s) in database.\n\n"
            f"Choose an existing App destination below, or create a new one:"
        )

    @classmethod
    def render_app_create_prompt(cls, step_name: str, app_data: Dict[str, Any]) -> str:
        name = app_data.get("name", "<i>Not set</i>")
        desc = app_data.get("description", "<i>None</i>")
        icon = app_data.get("icon_url", "<i>None</i>")

        if step_name == "NAME":
            return (
                f"➕ <b>CREATE NEW APP</b> (Step 1/3)\n\n"
                f"Please reply with the <b>App Name</b>.\n\n"
                f"<i>Example: Course Wallah, GATE Academy, B.Tech Hub</i>"
            )
        elif step_name == "DESC":
            return (
                f"📱 <b>APP NAME:</b> {name}\n\n"
                f"Please reply with the <b>App Description</b> or click Skip."
            )
        elif step_name == "ICON":
            return (
                f"📱 <b>APP NAME:</b> {name}\n"
                f"📝 <b>DESCRIPTION:</b> {desc}\n\n"
                f"🖼 <b>APP IMAGE URL</b> (Step 3/3)\n"
                f"Please reply with a valid public <b>Image URL</b> (JPEG, PNG, WebP).\n\n"
                f"<i>Example: https://example.com/logo.png</i>\n\n"
                f"<i>Click Skip if you do not want to set an image URL right now.</i>"
            )
        else:
            return (
                f"📱 <b>APP READY FOR CREATION</b>\n\n"
                f"• <b>Name:</b> {name}\n"
                f"• <b>Description:</b> {desc}\n"
                f"• <b>Icon:</b> {icon}\n\n"
                f"<i>Confirm to save this App to the database:</i>"
            )

    @classmethod
    def render_app_edit_prompt(cls, app_data: Dict[str, Any]) -> str:
        name = app_data.get("name", "Unknown")
        desc = app_data.get("description", "None")
        icon = app_data.get("icon_url", "None")

        return (
            f"✏️ <b>EDIT APP</b>\n\n"
            f"• <b>Current App:</b> <b>{name}</b>\n"
            f"• <b>Description:</b> {desc}\n"
            f"• <b>Icon:</b> {icon}\n\n"
            f"<i>Choose a field to modify or save changes:</i>"
        )

    @classmethod
    def render_batch_selection(cls, app_name: str, batches: List[Any]) -> str:
        count = len(batches)
        return (
            f"🎓 <b>APP:</b> <b>{app_name}</b>\n\n"
            f"📦 <b>SELECT EXISTING BATCH</b>\n"
            f"Found <b>{count}</b> existing batch(es) in this App.\n\n"
            f"Where should the TXT content go?"
        )

    @classmethod
    def render_existing_batch_selected(
        cls,
        batch_name: str,
        new_count: int,
        existing_count: int,
        dup_count: int
    ) -> str:
        return (
            f"📦 <b>BATCH SELECTED</b>\n\n"
            f"📚 <b>Batch:</b> <b>{batch_name}</b>\n\n"
            f"<b>Detected TXT Status:</b>\n"
            f"• 🆕 <b>New lectures:</b> {new_count}\n"
            f"• ✅ <b>Already in DB:</b> {existing_count}\n"
            f"• ⏭️ <b>Duplicate (Skip):</b> {dup_count}\n\n"
            f"<b>Choose execution mode:</b>"
        )

    @classmethod
    def render_batch_create_wizard(cls, step_name: str, batch_data: Dict[str, Any]) -> str:
        app_name = batch_data.get("app_name", "Course Wallah")
        name = batch_data.get("name", "New Batch")
        cat = batch_data.get("category", "B.Tech")
        branch = batch_data.get("branch", "CSE")
        sem = batch_data.get("semester", "3rd Semester")
        year = batch_data.get("academic_year", "2026")
        quality = batch_data.get("quality_pref", "AUTO / BEST")
        wm = batch_data.get("watermark_enabled", True)
        wm_str = "✅ ENABLED (Moving Drift)" if wm else "❌ DISABLED"

        if step_name == "NAME":
            return (
                f"➕ <b>CREATE NEW BATCH</b>\n\n"
                f"🎓 <b>App:</b> {app_name}\n\n"
                f"Please reply with the <b>Batch Name</b>.\n\n"
                f"<i>Current detected name: <code>{name}</code></i>"
            )
        elif step_name == "CATEGORY":
            return (
                f"📦 <b>BATCH:</b> {name}\n\n"
                f"Choose <b>Academic Type / Category:</b>"
            )
        elif step_name == "BRANCH":
            return (
                f"📦 <b>BATCH:</b> {name}\n"
                f"🏷 <b>Category:</b> {cat}\n\n"
                f"Choose <b>Branch / Stream:</b>"
            )
        elif step_name == "SEMESTER":
            return (
                f"📦 <b>BATCH:</b> {name}\n"
                f"🎓 <b>Branch:</b> {branch}\n\n"
                f"Choose <b>Semester / Year:</b>"
            )
        elif step_name == "SETTINGS":
            return (
                f"⚙️ <b>PROCESSING SETTINGS</b>\n\n"
                f"• <b>Quality Preference:</b> {quality}\n"
                f"• <b>Moving Watermark:</b> {wm_str}\n\n"
                f"<i>Configure video and watermark settings:</i>"
            )
        else:
            return (
                f"📦 <b>BATCH READY FOR CONFIRMATION</b>\n\n"
                f"• <b>App:</b> {app_name}\n"
                f"• <b>Batch Name:</b> {name}\n"
                f"• <b>Category:</b> {cat}\n"
                f"• <b>Branch:</b> {branch}\n"
                f"• <b>Semester:</b> {sem}\n"
                f"• <b>Academic Year:</b> {year}\n"
                f"• <b>Quality:</b> {quality}\n"
                f"• <b>Watermark:</b> {wm_str}\n\n"
                f"<i>Confirm to save this batch and proceed to mapping:</i>"
            )

    @classmethod
    def render_mapping_menu(cls, mapping_summary: Dict[str, Any]) -> str:
        app_name = mapping_summary.get("app_name", "Course Wallah")
        batch_name = mapping_summary.get("batch_name", "Academic Batch")
        total = mapping_summary.get("total_lectures", 0)
        subjects = mapping_summary.get("subject_count", 0)
        folders = mapping_summary.get("unit_count", 0)

        return (
            f"✏️ <b>EDIT / MAP TXT</b>\n\n"
            f"<b>Detected Structure:</b>\n"
            f"<code>📱 APP       : {app_name}\n"
            f" └── 📦 BATCH : {batch_name}\n"
            f"      └── 📚 SUBJECTS : {subjects}\n"
            f"           └── 📁 FOLDERS  : {folders}\n"
            f"                └── 🎬 LECTURES : {total}</code>\n\n"
            f"<b>Choose what to customize before launching ingestion:</b>"
        )

    @classmethod
    def render_parsed_preview(cls, items: List[Dict[str, Any]], page: int = 1) -> str:
        if not items:
            return "📋 <b>PARSED PREVIEW</b>\n\n<i>No items detected in TXT file.</i>"

        lines = [f"📋 <b>PARSED PREVIEW (First {len(items)} items)</b>\n"]
        for it in items:
            idx = it.get("index", 1)
            subj = it.get("subject", "General")
            folder = it.get("folder", "Unit 01")
            title = it.get("title", "Lecture")
            v_url = it.get("video_url") or "❌ None"
            if len(v_url) > 45:
                v_url = v_url[:42] + "..."
            p_url = it.get("pdf_url") or "❌ None"
            if len(p_url) > 45:
                p_url = p_url[:42] + "..."

            lines.append(
                f"<b>{idx}.</b>\n"
                f"• <b>Subject:</b> {subj}\n"
                f"• <b>Folder:</b> {folder}\n"
                f"• <b>Lecture:</b> {title}\n"
                f"• <b>Video:</b> <code>{v_url}</code>\n"
                f"• <b>PDF:</b> <code>{p_url}</code>\n"
            )

        return "\n".join(lines)

    @classmethod
    def render_final_confirmation(cls, session_data: Dict[str, Any]) -> str:
        app_name = session_data.get("app_name", "Course Wallah")
        batch_name = session_data.get("batch_name", "New Batch")
        stats = session_data.get("analysis_stats", {})
        total_v = stats.get("video_count", 0)
        total_p = stats.get("pdf_count", 0)
        total_s = stats.get("subject_count", 0)
        total_f = stats.get("unit_count", 0)
        pub_cnt = stats.get("already_processed_count", 0)
        new_cnt = stats.get("new_count", stats.get("total_lectures", 0))
        fail_cnt = stats.get("failed_count", 0)

        quality = session_data.get("quality_pref", "AUTO / BEST")
        wm = session_data.get("watermark_enabled", True)
        wm_str = "ENABLED (Continuous Drift)" if wm else "DISABLED"
        mode = session_data.get("execution_mode", "APPEND NEW CONTENT")

        return (
            f"🚀 <b>READY TO PROCESS</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"📱 <b>App:</b> <b>{app_name}</b>\n"
            f"📦 <b>Batch:</b> <b>{batch_name}</b>\n\n"
            f"🎬 <b>Detected:</b>\n"
            f"• Videos: <b>{total_v}</b>\n"
            f"• PDFs: <b>{total_p}</b>\n"
            f"• Subjects: <b>{total_s}</b>\n"
            f"• Folders: <b>{total_f}</b>\n\n"
            f"📊 <b>Status:</b>\n"
            f"• ⏭️ Already Published: <b>{pub_cnt}</b>\n"
            f"• 🔁 Failed Retryable: <b>{fail_cnt}</b>\n"
            f"• 🆕 New to Process: <b>{new_cnt}</b>\n\n"
            f"⚙️ <b>Pipeline Config:</b>\n"
            f"• Mode: <b>{mode}</b>\n"
            f"• Quality: <b>{quality}</b>\n"
            f"• Watermark: <b>{wm_str}</b>\n"
            f"• YouTube: <b>Unlisted Resumable</b>\n"
            f"• PDF Storage: <b>Private B2 S3</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"<i>Click 'START PROCESSING' to begin automated ingestion:</i>"
        )

    # ==========================================
    # PIPELINE PROGRESS RENDERING
    # ==========================================

    @classmethod
    def render_phase_pipeline(cls, phase_states: Dict[str, str]) -> str:
        phases = [
            ("📥 Download", phase_states.get("download", "⏳")),
            ("💧 Watermark", phase_states.get("watermark", "⏳")),
            ("🖼 Thumbnail", phase_states.get("thumbnail", "⏳")),
            ("☁️ YouTube", phase_states.get("youtube", "⏳")),
            ("📄 PDF", phase_states.get("pdf", "⏳")),
            ("☁️ B2", phase_states.get("b2", "⏳")),
            ("🗄 Database", phase_states.get("database", "⏳")),
            ("📚 Playlist", phase_states.get("playlist", "⏳")),
            ("🌐 Publish", phase_states.get("publish", "⏳"))
        ]
        lines = [f"{name:<13} : {status}" for name, status in phases]
        return "\n".join(lines)

    @classmethod
    def render_live_card(
        cls,
        batch_name: str,
        folder_name: str,
        lecture_index: int,
        lecture_title: str,
        total_lectures: int,
        completed_count: int,
        failed_count: int,
        skipped_count: int,
        current_step: str,
        download_pct: float = 0.0,
        watermark_pct: float = 0.0,
        youtube_pct: float = 0.0,
        pdf_pct: float = 0.0,
        b2_pct: float = 0.0,
        phase_states: Optional[Dict[str, str]] = None,
        spinner_idx: int = 0
    ) -> str:
        pending_count = max(0, total_lectures - completed_count - failed_count - skipped_count - 1)
        spinner = get_spinner(spinner_idx)

        active_prog_str = ""
        if "download" in current_step.lower():
            active_prog_str = f"📥 <b>Downloading:</b> [{make_progress_bar(download_pct)}] {download_pct:5.1f}%\n"
        elif "watermark" in current_step.lower():
            active_prog_str = f"💧 <b>Watermarking:</b> [{make_progress_bar(watermark_pct)}] {watermark_pct:5.1f}%\n"
        elif "youtube" in current_step.lower():
            active_prog_str = f"☁️ <b>YouTube Upload:</b> [{make_progress_bar(youtube_pct)}] {youtube_pct:5.1f}%\n"
        elif "pdf" in current_step.lower():
            active_prog_str = f"📄 <b>PDF Processing:</b> [{make_progress_bar(pdf_pct)}] {pdf_pct:5.1f}%\n"
        elif "b2" in current_step.lower():
            active_prog_str = f"☁️ <b>B2 Storage:</b> [{make_progress_bar(b2_pct)}] {b2_pct:5.1f}%\n"

        overall_pct = (completed_count / max(1, total_lectures)) * 100.0
        overall_bar = make_progress_bar(overall_pct, bar_length=12, style="smooth")

        if phase_states is None:
            phase_states = {
                "download": "🔄" if "download" in current_step.lower() else "⏳",
                "watermark": "🔄" if "watermark" in current_step.lower() else "⏳",
                "thumbnail": "🔄" if "thumb" in current_step.lower() else "⏳",
                "youtube": "🔄" if "youtube" in current_step.lower() else "⏳",
                "pdf": "🔄" if "pdf" in current_step.lower() else "⏳",
                "b2": "🔄" if "b2" in current_step.lower() else "⏳",
                "database": "🔄" if "data" in current_step.lower() else "⏳",
                "playlist": "🔄" if "play" in current_step.lower() else "⏳",
                "publish": "🔄" if "pub" in current_step.lower() else "⏳"
            }
        phase_table = cls.render_phase_pipeline(phase_states)

        return (
            f"╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            f"  {spinner} <b>COURSE WALLAH INGESTION</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"📚 <b>Batch:</b> {batch_name}\n"
            f"📁 <b>Unit:</b> {folder_name}\n"
            f"🎬 <b>Current:</b> #{lecture_index} — <b>{lecture_title}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"<code>{phase_table}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{active_prog_str}"
            f"📊 <b>BATCH PROGRESS:</b> [{overall_bar}] {overall_pct:5.1f}%\n"
            f"✅ Success : <b>{completed_count}</b>\n"
            f"⏭️ Skipped : <b>{skipped_count}</b>\n"
            f"❌ Failed  : <b>{failed_count}</b>\n"
            f"⏳ Pending : <b>{pending_count}</b> / {total_lectures}\n\n"
            f"⚡ <i>Current Step: {current_step}</i>"
        )

    @classmethod
    def format_live_card(
        cls,
        batch_name: str,
        folder_name: str,
        lecture_index: int,
        lecture_title: str,
        total_lectures: int,
        completed_count: int,
        download_pct: float = 0.0,
        download_status: str = "Ready",
        watermark_pct: float = 0.0,
        watermark_status: str = "Ready",
        thumbnail_ready: bool = False,
        youtube_pct: float = 0.0,
        youtube_status: str = "Ready",
        youtube_video_id: str = "",
        has_pdf: bool = False,
        pdf_pct: float = 0.0,
        pdf_status: str = "Ready",
        b2_pct: float = 0.0,
        b2_status: str = "Ready",
        db_status: str = "Ready",
        playlist_status: str = "Ready",
        failed_count: int = 0,
        skipped_count: int = 0
    ) -> str:
        bar = make_progress_bar((completed_count / max(1, total_lectures)) * 100.0, bar_length=10)
        return (
            f"╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
            f"  ⚡ <b>COURSE WALLAH INGESTION</b>\n"
            f"╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
            f"📚 <b>Batch:</b> {batch_name}\n"
            f"📁 <b>Unit:</b> {folder_name}\n"
            f"🎬 <b>Current:</b> #{lecture_index} — <b>{lecture_title}</b>\n\n"
            f"📊 <b>BATCH PROGRESS:</b> [{bar}] {completed_count} / {total_lectures} completed\n"
            f"• Download   : [{make_progress_bar(download_pct)}] {download_status}\n"
            f"• Watermark  : [{make_progress_bar(watermark_pct)}] {watermark_status}\n"
            f"• YouTube    : [{make_progress_bar(youtube_pct)}] {youtube_status}\n"
            f"• PDF Storage: [{make_progress_bar(b2_pct)}] {b2_status}\n"
            f"• Failed     : <b>{failed_count}</b> | Skipped: <b>{skipped_count}</b>\n"
        )

    # ==========================================
    # SUMMARIES, PAUSE, CANCEL & REPORTING
    # ==========================================

    @classmethod
    def render_batch_summary(cls, summary: Dict[str, Any]) -> str:
        batch_name = summary.get("batch_name", "Academic Batch")
        total = summary.get("total", 0)
        success = summary.get("success", 0)
        failed = summary.get("failed", 0)
        skipped = summary.get("skipped", 0)
        pending = summary.get("pending", 0)
        videos = summary.get("videos_count", success)
        pdfs = summary.get("pdfs_count", 0)
        start_time = summary.get("start_time", "Earlier")
        end_time = summary.get("end_time", "Now")

        if summary.get("youtube_limit_reached"):
            return (
                f"⚠️ <b>YOUTUBE UPLOAD LIMIT REACHED</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📚 <b>Batch:</b>\n"
                f"<b>{batch_name}</b>\n\n"
                f"📊 <b>STATUS & PROGRESS</b>\n\n"
                f"🎬 Total       <b>{total}</b>\n"
                f"✅ Published   <b>{success}</b>\n"
                f"🛑 Quota Pause <b>{failed}</b>\n"
                f"⏭️ Skipped     <b>{skipped}</b>\n"
                f"⏳ Pending     <b>{pending}</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"ℹ️ <b>Note:</b>\n"
                f"YouTube upload limit reached. Download/processing is complete, but publishing is temporarily blocked by YouTube.\n\n"
                f"💾 <i>Prepared watermarked artifacts have been safely checkpointed on disk. Use <b>Resume</b> when your YouTube upload quota resets.</i>"
            )

        return (
            f"🎉 <b>BATCH PROCESSING COMPLETED</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📚 <b>Batch:</b>\n"
            f"<b>{batch_name}</b>\n\n"
            f"📊 <b>SUMMARY</b>\n\n"
            f"🎬 Total       <b>{total}</b>\n"
            f"✅ Success     <b>{success}</b>\n"
            f"❌ Failed      <b>{failed}</b>\n"
            f"⏭️ Skipped     <b>{skipped}</b>\n"
            f"⏳ Pending     <b>{pending}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎥 Videos     <b>{videos}</b>\n"
            f"📄 PDFs       <b>{pdfs}</b>\n"
            f"☁️ YouTube    <b>{videos}</b>\n"
            f"☁️ B2         <b>{pdfs}</b>\n"
            f"📚 Playlist   <b>{success}</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"⏱ <b>Started:</b> {start_time}\n"
            f"🏁 <b>Finished:</b> {end_time}\n\n"
            f"🌐 <i>All content is now live and published on Course Wallah Platform!</i>"
        )

    @classmethod
    def render_failed_summary(cls, failed_items: List[Dict[str, Any]], batch_name: str) -> str:
        if not failed_items:
            return (
                f"✅ <b>NO FAILED ITEMS</b>\n\n"
                f"All lectures in <b>{batch_name}</b> were processed successfully without errors!"
            )

        items_str = []
        for it in failed_items[:10]:
            idx = it.get("index", 0)
            title = it.get("title", "Lecture")
            err = it.get("error", "Unknown error")
            clean_err = str(err).replace("https://", "").replace("http://", "")[:60]
            items_str.append(f"• <b>#{idx}</b> {title}\n  ↳ <i>Error: {clean_err}</i>")

        more_str = f"\n<i>...and {len(failed_items) - 10} more</i>" if len(failed_items) > 10 else ""
        list_block = "\n\n".join(items_str) + more_str

        return (
            f"❌ <b>FAILED ITEMS IN BATCH ({len(failed_items)})</b>\n\n"
            f"📚 <b>Batch:</b> {batch_name}\n\n"
            f"{list_block}\n\n"
            f"<i>Click 'Retry Failed' below to reprocess failed lectures safely.</i>"
        )

    @classmethod
    def render_paused_summary(cls, batch_name: str, completed: int, total: int) -> str:
        pending = max(0, total - completed)
        return (
            f"⏸ <b>BATCH PAUSED</b>\n\n"
            f"📚 <b>Batch:</b> {batch_name}\n\n"
            f"✅ <b>Completed:</b> {completed} / {total}\n"
            f"⏳ <b>Pending:</b> {pending}\n\n"
            f"<i>The batch pipeline was safely paused. Checkpoints have been persisted in database.</i>\n"
            f"<i>Use /batchresume or click Resume to continue.</i>"
        )

    @classmethod
    def render_cancel_prompt(cls, batch_name: str, completed: int, total: int) -> str:
        return (
            f"⚠️ <b>CANCEL BATCH INGESTION?</b>\n\n"
            f"📚 <b>Batch:</b> {batch_name}\n\n"
            f"✅ <b>Completed so far:</b> {completed} / {total}\n\n"
            f"<i>Cancelling will safely finish current atomic steps, clean scratch files, and preserve all already published content.</i>\n\n"
            f"Are you sure you want to cancel?"
        )

    @classmethod
    def render_cancelled_summary(cls, batch_name: str, completed: int, total: int) -> str:
        return (
            f"🛑 <b>BATCH INGESTION CANCELLED</b>\n\n"
            f"📚 <b>Batch:</b> {batch_name}\n\n"
            f"✅ <b>Preserved Published Lectures:</b> {completed} / {total}\n"
            f"🧹 <b>Temporary scratch files:</b> Cleaned up\n\n"
            f"<i>All successfully uploaded videos and PDFs remain published and accessible on Course Wallah Platform.</i>"
        )

    @classmethod
    def render_batch_status_screen(cls, controllers: Dict[str, Any]) -> str:
        if not controllers:
            return (
                f"📊 <b>BATCH STATUS</b>\n\n"
                f"Active Jobs: <b>0</b>\n\n"
                f"<i>No active batch jobs currently running.</i>\n"
                f"Use /batch or /uploadbatch to start a new batch."
            )

        lines = [
            f"📊 <b>BATCH STATUS</b>\n",
            f"Active Jobs: <b>{len(controllers)}</b>\n",
            f"━━━━━━━━━━━━━━━━━━\n"
        ]
        for j_id, ctrl in controllers.items():
            st_icon = "⏸ PAUSED" if ctrl.is_paused else "🔄 PROCESSING"
            bar = make_progress_bar((ctrl.completed_count / max(1, ctrl.total_lectures)) * 100.0, bar_length=8)
            lines.append(
                f"📚 <b>{ctrl.batch_name}</b>\n"
                f"• Status    : <b>{st_icon}</b>\n"
                f"• Progress  : [{bar}] {ctrl.completed_count} / {ctrl.total_lectures}\n"
                f"• Failed    : <b>{ctrl.failed_count}</b> | Skipped: <b>{ctrl.skipped_count}</b>\n"
                f"• Job ID    : <code>{j_id}</code>\n"
            )
        lines.append("🟢 <b>Worker:</b> ONLINE")
        return "\n".join(lines)

    @classmethod
    def render_batch_jobs_screen(cls, jobs_data: List[Dict[str, Any]]) -> str:
        if not jobs_data:
            return (
                f"📋 <b>RECENT BATCH JOBS</b>\n\n"
                f"<i>No recent batch jobs recorded in database.</i>"
            )

        lines = ["📋 <b>RECENT BATCH JOBS</b>\n\n"]
        for idx, job in enumerate(jobs_data, 1):
            name = job.get("name", "Academic Batch")
            status = job.get("status", "COMPLETED")
            prog = job.get("progress", "Done")
            st_icon = "🟢" if "RUNNING" in status or "PROCESSING" in status else ("✅" if "COMPLETED" in status or "READY" in status else "❌")
        return "\n".join(lines)

    @classmethod
    def render_student_list(cls, students: List[Any]) -> str:
        if not students:
            return (
                "👥 <b>STUDENTS DIRECTORY</b>\n\n"
                "<i>No registered students found matching query.</i>"
            )

        lines = [
            f"👥 <b>STUDENT DIRECTORY ({len(students)})</b>\n",
            "━━━━━━━━━━━━━━━━━━━━\n"
        ]
        for idx, s in enumerate(students[:15], 1):
            status = "🟢 Active" if s.is_active else "🔴 Disabled"
            acc_count = len(s.batch_accesses) if hasattr(s, "batch_accesses") and s.batch_accesses else 0
            lines.append(
                f"<b>{idx}. {s.name}</b> ({status})\n"
                f"   📧 <code>{s.email}</code>\n"
                f"   📚 Batches: <b>{acc_count}</b> | ID: <code>{s.id[:8]}</code>\n"
            )

        if len(students) > 15:
            lines.append(f"\n<i>...and {len(students) - 15} more</i>")

        lines.append("\n<i>Use /grant &lt;email&gt; &lt;batch_slug&gt; to grant access.</i>")
        return "\n".join(lines)

    @classmethod
    def render_student_detail(cls, student: Any) -> str:
        status = "🟢 Active" if student.is_active else "🔴 Disabled"
        access_lines = []
        if hasattr(student, "batch_accesses") and student.batch_accesses:
            for acc in student.batch_accesses:
                b_name = acc.batch.name if acc.batch else acc.batch_id
                access_lines.append(f"• <b>{b_name}</b> [{acc.status}]")
        else:
            access_lines.append("<i>No active batch enrollments</i>")

        return (
            f"👤 <b>STUDENT PROFILE</b>\n\n"
            f"• <b>Name:</b> {student.name}\n"
            f"• <b>Email:</b> <code>{student.email}</code>\n"
            f"• <b>Status:</b> {status}\n"
            f"• <b>Student ID:</b> <code>{student.id}</code>\n\n"
            f"📚 <b>Enrolled Batches:</b>\n" + "\n".join(access_lines)
        )

    @classmethod
    def render_media_health(cls, health: Dict[str, Any]) -> str:
        return (
            f"🩺 <b>COURSE WALLAH — MEDIA HEALTH & DIAGNOSTICS</b>\n\n"
            f"👥 <b>Students:</b> {health.get('total_students', 0)}\n"
            f"📚 <b>Batches:</b> {health.get('total_batches', 0)}\n"
            f"📖 <b>Lectures:</b> {health.get('total_lectures', 0)}\n\n"
            f"🎥 <b>Video Coverage:</b> {health.get('total_videos', 0)} ({health.get('video_coverage_pct', 0)}%)\n"
            f"📄 <b>PDF Notes:</b> {health.get('total_pdfs', 0)} ({health.get('pdf_coverage_pct', 0)}%)\n\n"
            f"⚡ <b>Active Jobs:</b> {health.get('active_jobs', 0)}\n"
            f"⚠️ <b>Failed Jobs:</b> {health.get('failed_jobs', 0)}\n\n"
            f"🟢 <b>Status:</b> All Services Operational"
        )

    # ==========================================
    # YOUTUBE MULTI-ACCOUNT & FAILOVER SCREENS
    # ==========================================

    @classmethod
    def render_youtube_accounts_screen(cls, diag_data: Dict[str, Any], selected_account_id: Optional[str] = None) -> str:
        accounts = diag_data.get("accounts", [])
        total_accounts = diag_data.get("total_accounts", 0)
        active_accounts = diag_data.get("active_accounts", 0)
        limit_reached = diag_data.get("limit_reached_accounts", 0)
        auth_error = diag_data.get("auth_error_accounts", 0)
        blocked_ckpts = diag_data.get("blocked_checkpoints_count", 0)

        lines = [
            "🎬 <b>YOUTUBE ACCOUNTS & MULTI-CHANNEL POOL</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"📊 <b>Total Channels:</b> {total_accounts} | 🟢 Active: <b>{active_accounts}</b> | ⚠️ Limit: <b>{limit_reached}</b> | 🔴 Auth Error: <b>{auth_error}</b>",
            f"💾 <b>Durable Checkpoints on Disk:</b> <b>{blocked_ckpts}</b>\n"
        ]

        if not accounts:
            lines.append("<i>⚠️ No YouTube accounts registered yet. Click '➕ Add Account' or use /yt_add to link a channel.</i>\n")
        else:
            for idx, acc in enumerate(accounts, 1):
                status_raw = acc.get("status", "ACTIVE")
                if status_raw == "ACTIVE":
                    status_icon = "🟢"
                    status_label = "ACTIVE"
                elif status_raw == "LIMIT_REACHED":
                    status_icon = "🟡"
                    status_label = "DAILY LIMIT REACHED"
                elif status_raw == "AUTH_ERROR":
                    status_icon = "🔴"
                    status_label = "AUTH / TOKEN ERROR"
                else:
                    status_icon = "⚪"
                    status_label = status_raw

                priority = acc.get("priority", 1)
                pri_label = " 🌟 [PRIMARY #1]" if priority == 1 else f" [PRIORITY #{priority}]"
                
                ch_id = acc.get("channel_id")
                ch_title = acc.get("channel_title") or acc.get("name") or f"Channel {idx}"
                ch_link = f"<a href='https://youtube.com/channel/{ch_id}'>{ch_title}</a>" if ch_id and ch_id != "Not Detected" else f"<b>{ch_title}</b>"

                uploads = acc.get("uploads_today", 0)
                est_limit = acc.get("estimated_daily_limit", 20)
                remaining = acc.get("estimated_remaining_today", max(0, est_limit - uploads))

                lines.append(
                    f"<b>{idx}. {status_icon} {ch_link}</b>{pri_label}\n"
                    f"   • <b>Status:</b> <code>{status_label}</code>\n"
                    f"   • <b>Today's Uploads:</b> <b>{uploads}</b> / ~{est_limit} videos (<b>{remaining}</b> left)\n"
                    f"   • <b>Channel ID:</b> <code>{ch_id or 'Auto-Detect'}</code>\n"
                    f"   • <b>Client ID:</b> <code>{acc.get('client_id_masked')}</code>\n"
                    f"   • <b>Account ID:</b> <code>{acc.get('id')}</code>"
                )
                if acc.get("cooldown_until"):
                    lines.append(f"   • ⏳ <b>Limit Cooldown Until:</b> <code>{acc.get('cooldown_until')}</code>")
                if acc.get("last_error"):
                    lines.append(f"   • ⚠️ <b>Last Issue:</b> <i>{acc.get('last_error')[:80]}</i>")
                lines.append("")

        lines.append("<i>💡 Auto Failover: Jab kisi channel ka 20 videos/day limit poora hoga, bot bina video dubara download kiye agle channel par auto-switch karega.</i>\n")
        lines.append("<b>Commands:</b>\n• <code>/yt_add</code> — Link new channel\n• <code>/yt_list</code> — View all channels & quotas\n• <code>/yt_del &lt;id&gt;</code> — Remove channel\n• <code>/yt_test &lt;id&gt;</code> — Test token\n• <code>/yt_primary &lt;id&gt;</code> — Set as primary")
        return "\n".join(lines)

    @classmethod
    def render_youtube_account_detail(cls, acc: Dict[str, Any]) -> str:
        status_raw = acc.get("status", "ACTIVE")
        status_icon = "🟢" if status_raw == "ACTIVE" else ("🟡" if status_raw == "LIMIT_REACHED" else "🔴")
        ch_id = acc.get("channel_id")
        ch_title = acc.get("channel_title") or acc.get("name")
        ch_link = f"<a href='https://youtube.com/channel/{ch_id}'>{ch_title}</a>" if ch_id else ch_title

        uploads = acc.get("uploads_today", 0)
        est_limit = acc.get("estimated_daily_limit", 20)
        remaining = acc.get("estimated_remaining_today", max(0, est_limit - uploads))

        return (
            f"🎬 <b>YOUTUBE CHANNEL DETAILS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📺 <b>Channel Name:</b> {ch_link}\n"
            f"🆔 <b>Channel ID:</b> <code>{ch_id or 'Not Detected'}</code>\n"
            f"🔑 <b>Internal ID:</b> <code>{acc.get('id')}</code>\n"
            f"📶 <b>Status:</b> {status_icon} <b>{status_raw}</b>\n"
            f"⭐ <b>Priority Rank:</b> <b>#{acc.get('priority', 1)}</b>\n"
            f"📊 <b>Uploads Today:</b> <b>{uploads}</b> / ~{est_limit} videos\n"
            f"🎯 <b>Estimated Left:</b> <b>{remaining}</b> videos\n"
            f"🔒 <b>Client ID:</b> <code>{acc.get('client_id_masked')}</code>\n\n"
            f"<i>Select an action below to manage this account:</i>"
        )

    @classmethod
    def build_youtube_accounts_markup(cls, accounts: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
        buttons = []
        
        # Row 1: Add Account & Refresh All
        buttons.append([
            InlineKeyboardButton("➕ Add YouTube Channel", callback_data="yt:add_prompt"),
            InlineKeyboardButton("🔄 Refresh Diagnostics", callback_data="admin:youtube_accounts")
        ])

        # Individual Channel Management Buttons
        for acc in accounts[:6]:
            ch_title = (acc.get("channel_title") or acc.get("name") or "Channel")[:18]
            pri = acc.get("priority", 1)
            st_icon = "🟢" if acc.get("status") == "ACTIVE" else ("🟡" if acc.get("status") == "LIMIT_REACHED" else "🔴")
            pri_tag = "⭐" if pri == 1 else f"#{pri}"
            buttons.append([
                InlineKeyboardButton(f"{st_icon} {pri_tag} {ch_title}", callback_data=f"yt:view:{acc['id']}")
            ])

        # Pipeline Controls
        buttons.append([
            InlineKeyboardButton("▶️ Resume Pipeline", callback_data="job:resume_active"),
            InlineKeyboardButton("⏸️ Pause Pipeline", callback_data="job:pause_active")
        ])

        # Admin panel back
        buttons.append([
            InlineKeyboardButton("🛠️ Back to Admin Panel", callback_data="admin:dashboard")
        ])
        return InlineKeyboardMarkup(buttons)

    @classmethod
    def build_youtube_account_manage_markup(cls, account_id: str, is_active: bool) -> InlineKeyboardMarkup:
        toggle_label = "🚫 Disable Account" if is_active else "✅ Enable Account"
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Test & Refresh Token", callback_data=f"yt:test:{account_id}"),
                InlineKeyboardButton("⭐ Set as Primary (#1)", callback_data=f"yt:primary:{account_id}")
            ],
            [
                InlineKeyboardButton(toggle_label, callback_data=f"yt:toggle:{account_id}"),
                InlineKeyboardButton("🗑️ Remove / Delete", callback_data=f"yt:del_confirm:{account_id}")
            ],
            [
                InlineKeyboardButton("🔙 Back to YouTube Accounts", callback_data="admin:youtube_accounts")
            ]
        ])

    @classmethod
    def render_youtube_status_screen(cls, diag_data: Dict[str, Any], active_jobs_count: int = 0, paused_jobs_count: int = 0) -> str:
        total_accounts = diag_data.get("total_accounts", 0)
        active_accounts = diag_data.get("active_accounts", 0)
        blocked_ckpts = diag_data.get("blocked_checkpoints_count", 0)
        accounts = diag_data.get("accounts", [])

        total_uploads_today = sum(a.get("uploads_today", 0) for a in accounts)
        total_est_remaining = sum(a.get("estimated_remaining_today", 0) for a in accounts)

        return (
            f"🎬 <b>YOUTUBE PIPELINE & QUEUE STATUS</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🟢 <b>Active YouTube Accounts:</b> {active_accounts} / {total_accounts}\n"
            f"📊 <b>Total Uploads Today:</b> {total_uploads_today}\n"
            f"🎯 <b>Estimated Remaining Quota:</b> ~{total_est_remaining} videos today\n\n"
            f"⚡ <b>Active YouTube Upload Jobs:</b> {active_jobs_count}\n"
            f"⏸ <b>Paused YouTube Jobs:</b> {paused_jobs_count}\n"
            f"💾 <b>Preserved Checkpoints:</b> {blocked_ckpts}\n\n"
            f"🛡️ <b>Failover Engine:</b> Automatic limit failover enabled\n"
            f"🧹 <b>Server Disk Policy:</b> Local videos removed after upload\n"
            f"🔒 <b>Security:</b> Tokens encrypted / masked at rest"
        )



