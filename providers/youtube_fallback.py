import os
import re
import json
import logging
import asyncio
import subprocess
from typing import Optional, Dict, Any, List, Tuple, Union
from urllib.parse import urlparse, quote, parse_qs
from pathlib import Path

import requests

from config.settings import TEMP_DIR, DOWNLOADS_DIR

logger = logging.getLogger(__name__)

def parse_quality_number(q_str: str) -> int:
    if not q_str:
        return 720
    q_lower = str(q_str).lower()
    if "4k" in q_lower or "2160" in q_lower:
        return 2160
    if "2k" in q_lower or "1440" in q_lower:
        return 1440
    m = re.search(r"(\d{3,4})", str(q_str))
    return int(m.group(1)) if m else 720

def parse_bytes_from_label(label: str) -> int:
    if not label:
        return 0
    matches = re.findall(r"([\d.]+)\s*(GB|GiB|MB|MiB|KB|KiB|B)\b(?![kKmMgG]?bps|/s)", str(label), re.IGNORECASE)
    if not matches:
        return 0
    val_str, unit_raw = matches[-1]
    val = float(val_str)
    unit = unit_raw.upper()
    if unit in ("GB", "GIB"):
        return int(val * 1024 * 1024 * 1024)
    elif unit in ("MB", "MIB"):
        return int(val * 1024 * 1024)
    elif unit in ("KB", "KIB"):
        return int(val * 1024)
    return int(val)

DEFAULT_YOUTUBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive"
}

YTULTRA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://www.ytultra.com",
    "Referer": "https://www.ytultra.com/",
    "Connection": "keep-alive"
}

def parse_vynex_formats(data: Dict[str, Any], target_height: Any = 720) -> Optional[Dict[str, Any]]:
    if not data or not isinstance(data, dict):
        return None

    if isinstance(target_height, str):
        target_height = parse_quality_number(target_height)
    elif not isinstance(target_height, (int, float)) or target_height <= 0:
        target_height = 720
    else:
        target_height = int(target_height)

    formats = data.get("formats")
    if not isinstance(formats, list) and isinstance(data.get("data"), dict):
        formats = data["data"].get("formats")

    if not isinstance(formats, list) or not formats:
        return None

    progressive_candidates = []
    for f in formats:
        if not isinstance(f, dict):
            continue
        v_url = f.get("url")
        if not v_url:
            continue
        has_v = f.get("has_video", True)
        has_a = f.get("has_audio", True)
        h = f.get("height") or parse_quality_number(f.get("quality_label") or f.get("format_note") or "")
        if has_v and has_a:
            progressive_candidates.append({
                "url": v_url,
                "height": h,
                "format_id": f.get("format_id"),
                "filesize": f.get("filesize") or 0
            })

    if not progressive_candidates:
        return None

    at_or_below = [c for c in progressive_candidates if c["height"] <= target_height]
    if at_or_below:
        at_or_below.sort(key=lambda x: x["height"], reverse=True)
        return at_or_below[0]

    progressive_candidates.sort(key=lambda x: x["height"], reverse=True)
    return progressive_candidates[0]

def resolve_youtube_vynex(url: str, quality: str = "720p", timeout: int = 15) -> Optional[str]:
    api_url = f"https://api.vynex.download/api/v1/info?url={quote(url, safe='')}"
    try:
        resp = requests.get(api_url, headers=DEFAULT_YOUTUBE_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            chosen = parse_vynex_formats(data, target_height=quality)
            if chosen and chosen.get("url"):
                return chosen["url"]
    except Exception as e:
        logger.debug(f"[VYNEX] Error resolving {url}: {e}")
    return None

def fetch_ytultra_media_data(url: str, timeout: int = 15) -> Optional[Dict[str, Any]]:
    endpoint = "https://backend.ytultra.com/api/v1/media-info"
    payload = {"url": url}
    try:
        resp = requests.post(endpoint, json=payload, headers=YTULTRA_HEADERS, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug(f"[YTULTRA] Error fetching info for {url}: {e}")
    return None

def parse_ytultra_response(data: Dict[str, Any], target_height: Any = 720) -> Optional[Dict[str, Any]]:
    if not data or not isinstance(data, dict):
        return None

    media_list = data.get("media") or data.get("formats") or []
    if not isinstance(media_list, list) or not media_list:
        return None

    target_h = parse_quality_number(str(target_height))
    candidates = []

    for item in media_list:
        if not isinstance(item, dict):
            continue
        d_url = item.get("downloadUrl") or item.get("url")
        if not d_url:
            continue
        quality_label = item.get("quality") or item.get("resolution") or ""
        h = parse_quality_number(quality_label)
        candidates.append({
            "url": d_url,
            "height": h,
            "quality": quality_label
        })

    if not candidates:
        return None

    at_or_below = [c for c in candidates if c["height"] <= target_h]
    if at_or_below:
        at_or_below.sort(key=lambda x: x["height"], reverse=True)
        return at_or_below[0]

    candidates.sort(key=lambda x: x["height"], reverse=True)
    return candidates[0]

def resolve_youtube_ytultra(url: str, quality: str = "720p", timeout: int = 15) -> Optional[str]:
    data = fetch_ytultra_media_data(url, timeout=timeout)
    if data:
        chosen = parse_ytultra_response(data, target_height=quality)
        if chosen and chosen.get("url"):
            return chosen["url"]
    return None

def download_media_stream_url(
    url: str,
    output_path: str,
    target_quality: str = "720p",
    timeout: int = 30
) -> Optional[str]:
    """Downloads a direct or resolved media stream to output_path."""
    try:
        with requests.get(url, stream=True, headers=DEFAULT_YOUTUBE_HEADERS, timeout=timeout) as resp:
            if resp.status_code == 200:
                with open(output_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                    return output_path
    except Exception as e:
        logger.error(f"Failed stream download: {e}")
    return None
