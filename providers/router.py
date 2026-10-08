import os
import re
import enum
import logging
from pathlib import Path
from urllib.parse import urlparse, unquote
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

class MediaType(str, enum.Enum):
    DIRECT_IMAGE = "DIRECT_IMAGE"
    DIRECT_PDF = "DIRECT_PDF"
    APPX_LECTURE = "APPX_LECTURE"
    KGS_HLS = "KGS_HLS"
    SPAYEE_HLS = "SPAYEE_HLS"
    GO_CLASSES = "GO_CLASSES"
    ENCRYPTED_STREAM = "ENCRYPTED_STREAM"
    DIRECT_M3U8 = "DIRECT_M3U8"
    DIRECT_VIDEO = "DIRECT_VIDEO"
    YOUTUBE = "YOUTUBE"
    ZIP = "ZIP"
    AUDIO = "AUDIO"
    UNKNOWN = "UNKNOWN"

def parse_pdf_input(value: Optional[str]) -> Dict[str, Any]:
    if not value or not isinstance(value, str):
        return {"url": "", "password": None, "has_password": False}
    clean = value.strip()
    if not clean:
        return {"url": "", "password": None, "has_password": False}
    if "*" in clean:
        parts = clean.split("*", 1)
        url_part = parts[0].strip()
        pwd_part = parts[1].strip() if len(parts) > 1 else ""
        return {"url": url_part, "password": pwd_part if pwd_part else None, "has_password": bool(pwd_part)}
    return {"url": clean, "password": None, "has_password": False}

def is_direct_image_url(url: str, category_hint: Optional[str] = None) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    if category_hint and str(category_hint).strip().lower() in ("image", "photo", "img", "thumb", "thumbnail"):
        return True
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    img_exts = (r'\.jpg', r'\.jpeg', r'\.png', r'\.webp', r'\.gif', r'\.bmp', r'\.svg')
    ext_pattern = rf"({'|'.join(img_exts)})($|[?&#/])"
    return bool(re.search(ext_pattern, clean, re.IGNORECASE))

def is_spayee_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return "spayee.in" in host or "spayee" in host or "spayee" in path

def is_goclasses_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    host = (parsed.netloc or "").lower()
    return "goclasses.in" in host or "gateoverflow.in" in host

def is_kgs_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return "khanglobalstudies.com" in host or "kgs" in host or "akamaized.net" in host and "khanglobalstudies" in path

def is_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    host = (parsed.netloc or "").lower()
    return "youtube.com" in host or "youtu.be" in host or "youtube-nocookie.com" in host

def is_encrypted_stream_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return "dragoapi" in host or "encrypted.m" in path or ("drm" in path and "m3u8" in path)

def is_direct_pdf_url(url: str, category_hint: Optional[str] = None) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    if category_hint and str(category_hint).strip().lower() in ("pdf", "document", "notes", "material"):
        return True
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    path = (parsed.path or "").lower()
    return ".pdf" in path or "file_manager/pdf" in path or "application/pdf" in (parsed.query or "").lower()

def is_appx_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return (
        "appx" in host
        or "classplus" in host
        or "classx" in host
        or "/lecture/" in path
        or "fetch_video" in path
        or "v2/video" in path
    )

def is_hls_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    path = (parsed.path or "").lower()
    return ".m3u8" in path or "playlist.m3u8" in path or "master.m3u8" in path

def is_direct_m3u8_url(url: str) -> bool:
    return is_hls_url(url)

def is_direct_video_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    clean = url.strip()
    if not clean:
        return False
    base_url = clean.split("*")[0].strip()
    parsed = urlparse(base_url)
    path = (parsed.path or "").lower()
    video_exts = (r'\.mp4', r'\.mkv', r'\.webm', r'\.avi', r'\.mov', r'\.ts', r'\.flv')
    return bool(re.search(rf"({'|'.join(video_exts)})($|[?&#])", path))

class MediaRouter:
    """
    Independent media URL classifier and router.
    Routes URLs to their proper specialized pipeline without cross-contamination.
    """
    is_direct_image_url = staticmethod(is_direct_image_url)
    is_direct_pdf_url = staticmethod(is_direct_pdf_url)
    is_kgs_url = staticmethod(is_kgs_url)
    is_spayee_url = staticmethod(is_spayee_url)
    is_goclasses_url = staticmethod(is_goclasses_url)
    is_youtube_url = staticmethod(is_youtube_url)
    is_encrypted_stream_url = staticmethod(is_encrypted_stream_url)
    is_hls_url = staticmethod(is_hls_url)
    is_direct_m3u8_url = staticmethod(is_direct_m3u8_url)
    is_appx_url = staticmethod(is_appx_url)
    is_direct_video_url = staticmethod(is_direct_video_url)

    @staticmethod
    def classify_url(url: str, category_hint: Optional[str] = None) -> MediaType:
        if not url or not isinstance(url, str):
            return MediaType.UNKNOWN
        clean = url.strip()
        if not clean:
            return MediaType.UNKNOWN

        if is_direct_image_url(clean, category_hint=category_hint):
            return MediaType.DIRECT_IMAGE
        if is_direct_pdf_url(clean, category_hint=category_hint):
            return MediaType.DIRECT_PDF
        if is_appx_url(clean):
            return MediaType.APPX_LECTURE
        if is_kgs_url(clean):
            return MediaType.KGS_HLS
        if is_spayee_url(clean):
            return MediaType.SPAYEE_HLS
        if is_goclasses_url(clean):
            return MediaType.GO_CLASSES
        if is_encrypted_stream_url(clean):
            return MediaType.ENCRYPTED_STREAM
        if is_hls_url(clean):
            return MediaType.DIRECT_M3U8
        if is_direct_video_url(clean):
            return MediaType.DIRECT_VIDEO
        if is_youtube_url(clean):
            return MediaType.YOUTUBE
        if ".zip" in clean.lower():
            return MediaType.ZIP

        return MediaType.UNKNOWN

    @staticmethod
    def extract_clean_title(url: str, default_title: Optional[str] = None) -> str:
        if default_title and default_title.strip() and default_title.strip().lower() not in (
            "video", "output", "download", "stream", "default title", "master", "playlist", "index", "file", "document", "notes"
        ):
            return default_title.strip()

        parsed = urlparse(url)
        path_parts = [p for p in (parsed.path or "").split("/") if p]
        for candidate in reversed(path_parts):
            cand_unquoted = unquote(candidate)
            stem = Path(cand_unquoted).stem
            if stem and stem.lower() not in ("master", "index", "playlist", "video", "output", "download", "stream", "file", "doc", "document"):
                return stem
        return "Lecture Content"
