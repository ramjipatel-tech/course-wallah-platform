import re
import time
import logging
from collections import deque
from datetime import datetime
from typing import List, Dict, Any, Optional

class InMemoryLogHandler(logging.Handler):
    """
    Thread-safe in-memory ring buffer that captures system and operational logs
    for the real-time web developer diagnostic console.
    """
    def __init__(self, capacity: int = 2500):
        super().__init__()
        self.capacity = capacity
        self.buffer = deque(maxlen=capacity)
        self._counter = 0

    def _classify_category(self, msg: str, level: str) -> str:
        msg_u = msg.upper()
        if level in ("ERROR", "CRITICAL"):
            return "ERROR"
        if "YOUTUBE" in msg_u or "OAUTH" in msg_u:
            return "YOUTUBE"
        if "PDF" in msg_u or "NOTES" in msg_u or "DOCUMENT" in msg_u:
            return "PDF"
        if "DOWNLOAD" in msg_u or "APPX" in msg_u or "HLS" in msg_u or "STREAM" in msg_u or "YT-DLP" in msg_u:
            return "DOWNLOAD"
        if "AUTH" in msg_u or "TOKEN" in msg_u or "LOGIN" in msg_u:
            return "AUTH"
        if "JOB" in msg_u or "BATCH" in msg_u or "LECTURE" in msg_u:
            return "JOB"
        return "SYSTEM"

    def _generate_diagnostic_hint(self, msg: str, level: str) -> Optional[str]:
        msg_l = msg.lower()
        if "invalid_client" in msg_l or "oauth client was not found" in msg_l:
            return "YouTube OAuth Error: Client ID/Secret not found in Google Cloud Console or mismatched. Check Settings > YouTube Accounts."
        if "foreign key constraint" in msg_l and "youtube_uploads_job_id" in msg_l:
            return "Database Foreign Key resolved: Job ID was linked to batch instead of job. Fixed in system update."
        if "uploadlimitexceeded" in msg_l or "channel_upload_limit" in msg_l:
            return "YouTube daily upload limit reached on this account. Automatic failover will route subsequent uploads to secondary accounts."
        if "http error 404" in msg_l and ".pdf" in msg_l:
            return "AppX Study Material / PDF Note: The resource is a document rather than a video stream. System now automatically routes to PDF downloader."
        if "exit 8" in msg_l or "ffmpeg" in msg_l:
            return "Video Transcoder notice: Stream may be encrypted or unreachable. Check provider stream validity."
        return None

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record) if self.formatter else record.getMessage()
            self._counter += 1
            
            # Extract bracket tag e.g. [PROVIDER:APPX]
            tag_match = re.search(r'\[([A-Z0-9_:\-]+)\]', msg)
            tag = tag_match.group(1) if tag_match else record.levelname

            category = self._classify_category(msg, record.levelname)
            hint = self._generate_diagnostic_hint(msg, record.levelname)

            log_entry = {
                "id": self._counter,
                "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "iso_time": datetime.fromtimestamp(record.created).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "tag": tag,
                "category": category,
                "message": msg,
                "hint": hint
            }
            self.buffer.append(log_entry)
        except Exception:
            self.handleError(record)

    def get_logs(
        self,
        limit: int = 200,
        level: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        since_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        entries = list(self.buffer)
        
        if since_id is not None:
            entries = [e for e in entries if e["id"] > since_id]

        if level and level.upper() != "ALL":
            lvl = level.upper()
            entries = [e for e in entries if e["level"] == lvl]

        if category and category.upper() != "ALL":
            cat = category.upper()
            entries = [e for e in entries if e["category"] == cat]

        if search:
            q = search.lower()
            entries = [e for e in entries if q in e["message"].lower() or q in e["tag"].lower()]

        return entries[-limit:]

    def clear(self):
        self.buffer.clear()

    def get_summary(self) -> Dict[str, Any]:
        entries = list(self.buffer)
        total = len(entries)
        errors = sum(1 for e in entries if e["level"] in ("ERROR", "CRITICAL"))
        warnings = sum(1 for e in entries if e["level"] == "WARNING")
        youtube_events = sum(1 for e in entries if e["category"] == "YOUTUBE")
        download_events = sum(1 for e in entries if e["category"] == "DOWNLOAD")

        return {
            "total_logs": total,
            "error_count": errors,
            "warning_count": warnings,
            "youtube_events": youtube_events,
            "download_events": download_events,
            "buffer_capacity": self.capacity,
            "last_log_id": self._counter
        }

# Global Singleton Handler
GLOBAL_LOG_HANDLER = InMemoryLogHandler(capacity=2500)
GLOBAL_LOG_HANDLER.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] [%(name)s] %(message)s")
)

# Automatically attach to root logger
root_logger = logging.getLogger()
if GLOBAL_LOG_HANDLER not in root_logger.handlers:
    root_logger.addHandler(GLOBAL_LOG_HANDLER)
