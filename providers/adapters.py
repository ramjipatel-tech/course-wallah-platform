import os
import re
import sys
import json
import time
import shutil
import logging
import asyncio
import subprocess
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlunparse
from typing import Optional, Dict, Any, Tuple, Union, List

from dataclasses import dataclass
import requests

# Platform root directory
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# ==============================================================================
# DATA STRUCTURES
# ==============================================================================

@dataclass
class AppxLectureResult:
    video_url: Optional[str] = None
    pdf_url: Optional[str] = None
    title: Optional[str] = None
    thumbnail: Optional[str] = None
    video_id: Optional[str] = None
    course_id: Optional[str] = None
    video_quality: Optional[str] = None
    is_drm: bool = False
    drm_message: Optional[str] = None
    has_video: bool = False
    has_pdf: bool = False
    error: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


# ==============================================================================
# NATIVE STANDALONE MEDIA ENGINE (ZERO EXTERNAL LEGACY DEPENDENCIES)
# ==============================================================================

class NativeMediaHelper:
    """
    Self-contained media resolution and download engine for Course Wallah Platform.
    Eliminates external legacy dependencies and provides 100% autonomous operation
    across Railway, Docker, Linux, and Windows environments.
    """

    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

    @classmethod
    def resolve_lecture_source(cls, url: str, target_quality: Optional[str] = None) -> AppxLectureResult:
        """
        Resolves AppX, ClassX, Akamai, or Heroku signed lecture endpoints (such as fetch_video)
        into structured media stream URLs, companion PDFs, and DRM metadata.
        """
        if not url or not isinstance(url, str):
            return AppxLectureResult(error="Empty or invalid URL provided")

        clean_url = url.strip()
        parsed = urlparse(clean_url)
        path_lower = parsed.path.lower()
        url_lower = clean_url.lower()

        # Direct media streams or external links that do not require API resolution
        if (
            path_lower.endswith((".m3u8", ".mp4", ".mkv", ".ts", ".webm"))
            or "youtu.be" in url_lower
            or "youtube.com" in url_lower
        ):
            return AppxLectureResult(
                video_url=clean_url,
                has_video=True,
                is_drm=False,
                video_quality=target_quality or "720p"
            )

        if path_lower.endswith(".pdf"):
            return AppxLectureResult(
                pdf_url=clean_url,
                has_pdf=True,
                is_drm=False
            )

        # Make HTTP request to resolve the lecture endpoint
        try:
            resp = requests.get(clean_url, headers=cls.DEFAULT_HEADERS, timeout=25)
            resp.raise_for_status()
            try:
                data = resp.json()
            except Exception:
                # If not JSON, check if text is an M3U8 or redirect
                text = resp.text.strip()
                if text.startswith("#EXTM3U") or ".m3u8" in text:
                    return AppxLectureResult(
                        video_url=resp.url or clean_url,
                        has_video=True,
                        is_drm=False,
                        video_quality=target_quality or "720p"
                    )
                return AppxLectureResult(error="Unrecognized non-JSON API response from provider")
        except Exception as e:
            logger.error(f"[NATIVE_HELPER] Failed to query lecture endpoint: {e}")
            return AppxLectureResult(error=f"Network error resolving lecture source: {e}")

        # Extract data dictionary (handles both { "data": { ... } } and top-level response)
        d = data.get("data") if isinstance(data, dict) and isinstance(data.get("data"), dict) else (data if isinstance(data, dict) else {})

        # 1. DRM Check
        is_drm = False
        drm_msg = None
        if (
            d.get("is_drm") in (True, 1, "1", "true", "True")
            or d.get("drm") in (True, 1, "1", "true", "True")
            or bool(d.get("drm_type"))
            or bool(d.get("drm_scheme"))
            or "widevine" in str(d).lower()
        ):
            is_drm = True
            drm_msg = str(d.get("drm_message") or d.get("drm_type") or "Widevine DRM Encrypted")

        # 2. Extract Video Stream URL
        video_url = None
        qualities = d.get("encrypted_links") or d.get("download_links") or d.get("qualities") or d.get("streams") or d.get("video_urls")
        if isinstance(qualities, list) and qualities:
            target_num = re.search(r"\d+", str(target_quality)) if target_quality else None
            matched_q = None
            if target_num:
                target_val = target_num.group(0)
                for q_item in qualities:
                    if isinstance(q_item, dict):
                        q_label = str(q_item.get("quality") or q_item.get("bitrate") or q_item.get("label") or q_item.get("resolution") or "")
                        if target_val in q_label:
                            matched_q = (
                                q_item.get("path")
                                or q_item.get("backup_url")
                                or q_item.get("backup_url2")
                                or q_item.get("link")
                                or q_item.get("url")
                                or q_item.get("video_url")
                            )
                            if matched_q:
                                break
            if not matched_q:
                # Pick highest quality / first available
                for q_item in qualities:
                    if isinstance(q_item, dict):
                        cand = (
                            q_item.get("path")
                            or q_item.get("backup_url")
                            or q_item.get("backup_url2")
                            or q_item.get("link")
                            or q_item.get("url")
                            or q_item.get("video_url")
                        )
                        if cand and isinstance(cand, str) and cand.strip():
                            matched_q = cand.strip()
                            break
            if matched_q:
                video_url = str(matched_q).strip()

        # Fallback to direct field links
        if not video_url:
            for key in (
                "download_link",
                "file_link",
                "download_url_higher_version",
                "download_url_lower_version",
                "video_player_url",
                "link",
                "video_url",
                "stream_url",
                "m3u8_url",
                "m3u8",
                "video",
                "encrypted_link",
                "encrypted_url",
                "url",
                "youtube_url"
            ):
                val = d.get(key)
                if val and isinstance(val, str) and val.strip():
                    val_str = val.strip()
                    if not val_str.lower().endswith(".pdf"):
                        video_url = val_str
                        break

        if not video_url:
            file_val = d.get("file_url") or d.get("download_url")
            if file_val and isinstance(file_val, str) and not file_val.lower().endswith(".pdf"):
                video_url = file_val.strip()

        # 3. Extract PDF URL
        pdf_url = None
        for key in (
            "pdf_link",
            "pdf_link2",
            "study_material_link",
            "pdf_summary_link",
            "pdf2_summary_link",
            "document_url",
            "pdf_url",
            "pdf",
            "notes",
            "notes_url",
            "doc_url",
            "material_url",
            "attachment_url",
            "notes_pdf"
        ):
            val = d.get(key)
            if val and isinstance(val, str) and val.strip():
                pdf_url = val.strip()
                break

        if not pdf_url:
            file_val = d.get("file_url")
            if file_val and isinstance(file_val, str) and file_val.lower().endswith(".pdf"):
                pdf_url = file_val.strip()

        # 4. Metadata
        title = (
            d.get("Title")
            or d.get("title")
            or d.get("video_name")
            or d.get("name")
            or d.get("lecture_title")
            or ""
        )
        thumbnail = (
            d.get("thumbnail")
            or d.get("thumb")
            or d.get("image")
            or d.get("poster")
            or d.get("cover_image")
            or ""
        )
        
        qs = parse_qs(parsed.query)
        video_id = str(d.get("video_id") or d.get("id") or qs.get("video_id", [""])[0] or "")
        course_id = str(d.get("course_id") or d.get("batch_id") or qs.get("course_id", [""])[0] or "")

        return AppxLectureResult(
            video_url=video_url,
            pdf_url=pdf_url,
            title=title or None,
            thumbnail=thumbnail or None,
            video_id=video_id or None,
            course_id=course_id or None,
            video_quality=target_quality or "720p",
            is_drm=is_drm,
            drm_message=drm_msg,
            has_video=bool(video_url),
            has_pdf=bool(pdf_url),
            raw_data=data
        )

    @classmethod
    def download_appx_m3u8(
        cls,
        url: str,
        clean_title: str,
        headers: Optional[Dict[str, str]] = None,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads HLS (.m3u8) streams via yt-dlp or ffmpeg into clean, validated MP4 containers
        using appropriate Referer and Origin headers.
        """
        dest_dir = Path(custom_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_file = dest_dir / f"{clean_title}.mp4"

        # Determine smart referer from URL domain
        parsed_stream = urlparse(url)
        origin_domain = f"{parsed_stream.scheme}://{parsed_stream.netloc}" if parsed_stream.netloc else "https://classx.co.in"
        req_headers = cls.DEFAULT_HEADERS.copy()
        req_headers["Referer"] = f"{origin_domain}/"
        req_headers["Origin"] = origin_domain
        if headers:
            req_headers.update(headers)

        # If key is provided in stream URL (e.g. url*key), delegate to Spayee decryptor
        if "*" in url:
            stream_part, key_part = url.split("*", 1)
            return original_spayee.download_spayee_hls(
                url=stream_part.strip(),
                output_path=None,
                clean_title=clean_title,
                key=key_part.strip(),
                quality="720p",
                custom_dir=custom_dir
            )

        # 1. Attempt download using yt-dlp
        try:
            logger.info(f"[NATIVE_HELPER] Downloading HLS stream via yt-dlp: {clean_title}")
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-check-certificates",
                "--concurrent-fragments", "8",
                "-N", "8",
                "--retries", "10",
                "--fragment-retries", "10",
                "--add-header", f"Referer:{req_headers['Referer']}",
                "--add-header", f"Origin:{req_headers['Origin']}",
                "-o", str(out_file),
                url
            ]
            if headers:
                for k, v in headers.items():
                    if k not in ("Referer", "Origin"):
                        cmd.extend(["--add-header", f"{k}:{v}"])

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 1024:
                return str(out_file)
            else:
                logger.warning(f"[NATIVE_HELPER] yt-dlp exited with {res.returncode}: {res.stderr[:200]}")
        except Exception as yt_err:
            logger.warning(f"[NATIVE_HELPER] yt-dlp failed: {yt_err}, falling back to ffmpeg...")

        # 2. Fallback to ffmpeg
        try:
            logger.info(f"[NATIVE_HELPER] Downloading HLS stream via ffmpeg: {clean_title}")
            ffmpeg_cmd = ["ffmpeg", "-y"]
            hdr_str = ""
            for k, v in req_headers.items():
                hdr_str += f"{k}: {v}\r\n"
            if hdr_str:
                ffmpeg_cmd.extend(["-headers", hdr_str])

            ffmpeg_cmd.extend([
                "-i", url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "+faststart",
                str(out_file)
            ])
            res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 1024:
                return str(out_file)
            else:
                raise RuntimeError(f"ffmpeg failed with exit {res.returncode}: {res.stderr[:200]}")
        except Exception as ff_err:
            raise RuntimeError(f"HLS download failed across all engines: {ff_err}")

        # If key is provided in stream URL (e.g. url*key), delegate to Spayee decryptor
        if "*" in url:
            stream_part, key_part = url.split("*", 1)
            return original_spayee.download_spayee_hls(
                url=stream_part.strip(),
                output_path=None,
                clean_title=clean_title,
                key=key_part.strip(),
                quality="720p",
                custom_dir=custom_dir
            )

        # 1. Attempt download using yt-dlp
        try:
            logger.info(f"[NATIVE_HELPER] Downloading HLS stream via yt-dlp: {clean_title}")
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-check-certificates",
                "--concurrent-fragments", "8",
                "-N", "8",
                "--retries", "10",
                "--fragment-retries", "10",
                "-o", str(out_file),
                url
            ]
            if headers:
                for k, v in headers.items():
                    cmd.extend(["--add-header", f"{k}:{v}"])

            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 1024:
                return str(out_file)
            else:
                logger.warning(f"[NATIVE_HELPER] yt-dlp exited with {res.returncode}: {res.stderr[:200]}")
        except Exception as yt_err:
            logger.warning(f"[NATIVE_HELPER] yt-dlp failed: {yt_err}, falling back to ffmpeg...")

        # 2. Fallback to ffmpeg
        try:
            logger.info(f"[NATIVE_HELPER] Downloading HLS stream via ffmpeg: {clean_title}")
            ffmpeg_cmd = ["ffmpeg", "-y"]
            hdr_str = ""
            req_headers = cls.DEFAULT_HEADERS.copy()
            if headers:
                req_headers.update(headers)
            for k, v in req_headers.items():
                hdr_str += f"{k}: {v}\r\n"
            if hdr_str:
                ffmpeg_cmd.extend(["-headers", hdr_str])

            ffmpeg_cmd.extend([
                "-i", url,
                "-c", "copy",
                "-bsf:a", "aac_adtstoasc",
                "-movflags", "+faststart",
                str(out_file)
            ])
            res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 1024:
                return str(out_file)
            else:
                raise RuntimeError(f"ffmpeg failed with exit {res.returncode}: {res.stderr[:200]}")
        except Exception as ff_err:
            raise RuntimeError(f"HLS download failed across all engines: {ff_err}")

    @classmethod
    def download_direct_video(
        cls,
        url: str,
        clean_title: str,
        headers: Optional[Dict[str, str]] = None,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads direct media streams (.mp4, .mkv, .ts) in streamed chunks.
        """
        dest_dir = Path(custom_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        ext = ".mp4"
        path_p = Path(urlparse(url).path)
        if path_p.suffix.lower() in [".mp4", ".mkv", ".webm", ".ts", ".mov"]:
            ext = path_p.suffix.lower()
            
        out_file = dest_dir / f"{clean_title}{ext}"
        req_headers = cls.DEFAULT_HEADERS.copy()
        if headers:
            req_headers.update(headers)

        try:
            with requests.get(url, headers=req_headers, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(out_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
            if out_file.exists() and out_file.stat().st_size > 0:
                return str(out_file)
        except Exception as e:
            logger.warning(f"[NATIVE_HELPER] Direct chunk download failed: {e}, attempting yt-dlp...")

        return cls.download_appx_m3u8(url, clean_title, headers=headers, custom_dir=custom_dir)

    @classmethod
    async def download_pdf(
        cls,
        url: str,
        name: str,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads PDF documents asynchronously.
        """
        dest_dir = Path(custom_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        clean_name = re.sub(r'[\\/*?:"<>|]', "", name).strip() or "document"
        if not clean_name.lower().endswith(".pdf"):
            clean_name += ".pdf"
        out_file = dest_dir / clean_name

        def _do_download():
            with requests.get(url, headers=cls.DEFAULT_HEADERS, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(out_file, "wb") as f:
                    for chunk in r.iter_content(chunk_size=512 * 1024):
                        if chunk:
                            f.write(chunk)
            return str(out_file)

        return await asyncio.to_thread(_do_download)

    @classmethod
    def download_image(
        cls,
        url: str,
        clean_title: str,
        headers: Optional[Dict[str, str]] = None,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads image assets.
        """
        dest_dir = Path(custom_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_file = dest_dir / f"{clean_title}.jpg"
        req_headers = cls.DEFAULT_HEADERS.copy()
        if headers:
            req_headers.update(headers)

        resp = requests.get(url, headers=req_headers, timeout=30)
        resp.raise_for_status()
        out_file.write_bytes(resp.content)
        return str(out_file)

    @classmethod
    async def download_video(
        cls,
        url: str,
        clean_title: str,
        quality: str = "720p",
        user_id: Optional[int] = None,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads YouTube or generic video sources via yt-dlp.
        """
        dest_dir = Path(custom_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_file = dest_dir / f"{clean_title}.mp4"

        def _ytdlp_sync():
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--no-check-certificates",
                "-f", f"bestvideo[height<={quality.rstrip('p')}]+bestaudio/best[height<={quality.rstrip('p')}]/best",
                "--merge-output-format", "mp4",
                "-o", str(out_file),
                url
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
            if res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 1024:
                return str(out_file)
            raise RuntimeError(f"yt-dlp failed with code {res.returncode}: {res.stderr[:200]}")

        return await asyncio.to_thread(_ytdlp_sync)

    @classmethod
    def download_and_decrypt_video(
        cls,
        clean_stream: str,
        clean_title: str,
        key: Optional[str] = None,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads and decrypts AES-128 streams.
        """
        return original_spayee.download_spayee_hls(
            url=clean_stream,
            output_path=None,
            clean_title=clean_title,
            key=key,
            quality="720p",
            custom_dir=custom_dir
        )

    @classmethod
    def download_kgs(
        cls,
        url: str,
        clean_title: str,
        quality: str = "720p",
        headers: Optional[Dict[str, str]] = None,
        custom_dir: str = "downloads"
    ) -> str:
        """
        Downloads Khan Global Studies (KGS) Akamai streams.
        """
        kgs_headers = {
            "User-Agent": cls.DEFAULT_HEADERS["User-Agent"],
            "Referer": "https://khanglobalstudies.com/",
            "Origin": "https://khanglobalstudies.com"
        }
        if headers:
            kgs_headers.update(headers)
        return cls.download_appx_m3u8(url, clean_title, headers=kgs_headers, custom_dir=custom_dir)


# ==============================================================================
# IMPORT ORIGINAL ROOT MODULES OR FALLBACK TO NATIVE HELPER
# ==============================================================================

try:
    import spayee_downloader as original_spayee
except ImportError:
    from providers import spayee as original_spayee

try:
    import itsgolu as original_helper
except ImportError:
    original_helper = NativeMediaHelper

try:
    import kgs_downloader as original_kgs
except ImportError:
    original_kgs = NativeMediaHelper

try:
    import youtube_fallback as original_yt_fallback
except ImportError:
    from providers import youtube_fallback as original_yt_fallback

try:
    import pdf_unlocker as original_pdf_unlocker
except ImportError:
    from providers import pdf_unlocker as original_pdf_unlocker

try:
    from utils import parse_pdf_input
except ImportError:
    def parse_pdf_input(url: str, title: str = ""):
        return {"url": url, "title": title, "password": None}

from providers.router import MediaRouter, MediaType

logger = logging.getLogger(__name__)


# ==============================================================================
# EXCEPTIONS
# ==============================================================================

class ProviderError(Exception):
    """Base exception for provider operations."""
    pass

class DRMProtectedError(ProviderError):
    """Content is DRM encrypted."""
    pass

class MediaValidationError(ProviderError):
    """Media failed validation checks (empty, corrupt, no video stream)."""
    pass

class ProviderResolutionError(ProviderError):
    """Provider API resolution failed."""
    pass

class ProviderDownloadError(ProviderError):
    """Provider download failed."""
    pass

class VideoUnavailableError(ProviderError):
    """
    Legitimate provider response where no video stream URL is available,
    but notes / PDF or course material may be available.
    """
    def __init__(self, message: str, pdf_url: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.pdf_url = pdf_url
        self.metadata = metadata or {}


# ==============================================================================
# LOG SANITIZATION
# ==============================================================================

def sanitize_url_for_logging(url: Optional[str]) -> str:
    """
    Strips tokens, JWTs, signatures, passwords, and sensitive query parameters from URLs
    for safe operational logging.
    """
    if not url or not isinstance(url, str):
        return ""
    clean = url.strip()
    if not clean:
        return ""

    key_part = None
    if "*" in clean:
        parts = clean.split("*", 1)
        clean = parts[0].strip()
        key_part = "[KEY_PROTECTED]"

    try:
        parsed = urlparse(clean)
        qs = parse_qs(parsed.query)
        safe_params = []
        for k, v in qs.items():
            k_lower = k.lower()
            if any(s in k_lower for s in ("token", "jwt", "session", "key", "sig", "auth", "secret", "cookie")):
                safe_params.append(f"{k}=[REDACTED]")
            else:
                val = v[0] if v else ""
                safe_params.append(f"{k}={val[:30]}")
        
        safe_query = "&".join(safe_params)
        sanitized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            safe_query,
            parsed.fragment
        ))
        return f"{sanitized} * {key_part}" if key_part else sanitized
    except Exception:
        return "[SANITIZED_URL]"


# ==============================================================================
# MEDIA VALIDATION ENGINE
# ==============================================================================

class MediaValidator:
    """
    Validates downloaded media files before downstream processing (watermark/upload).
    Guarantees container opens, duration > 0, video stream exists, and resolution is valid.
    """

    @classmethod
    async def validate_video_file(cls, file_path: Union[str, Path]) -> Dict[str, Any]:
        p = Path(file_path)
        if not p.exists():
            raise MediaValidationError(f"Video file not found on disk: {p}")

        size = p.stat().st_size
        if size <= 1024:
            raise MediaValidationError(f"Video file is empty or corrupted ({size} bytes): {p}")

        # Run ffprobe
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height",
            "-of", "json",
            str(p)
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err_text = stderr.decode("utf-8", errors="replace").strip()
                raise MediaValidationError(f"ffprobe failed to inspect media: {err_text}")

            probe_data = json.loads(stdout.decode("utf-8", errors="replace"))
            streams = probe_data.get("streams", [])
            fmt = probe_data.get("format", {})

            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            if not video_streams:
                raise MediaValidationError(f"No video stream found in container: {p}")

            v_stream = video_streams[0]
            width = int(v_stream.get("width") or 0)
            height = int(v_stream.get("height") or 0)
            codec = v_stream.get("codec_name", "unknown")
            duration = float(fmt.get("duration") or 0.0)

            res_label = f"{height}p" if height else "720p"

            logger.info(
                f"[MEDIA_VALIDATED] path={p.name} size={size} codec={codec} "
                f"resolution={width}x{height} duration={duration:.1f}s"
            )

            return {
                "valid": True,
                "file_path": str(p),
                "file_size": size,
                "duration": duration,
                "resolution": res_label,
                "width": width,
                "height": height,
                "codec": codec
            }

        except Exception as exc:
            if isinstance(exc, MediaValidationError):
                raise
            raise MediaValidationError(f"Failed to probe video file: {exc}")


# ==============================================================================
# PROVIDER ADAPTERS (REUSING ORIGINAL PROVEN IMPLEMENTATIONS)
# ==============================================================================

class AppxProviderAdapter:
    """
    Adapter for APPX / ClassX / Classplus / Akamai lecture endpoints.
    Reuses original `resolve_lecture_source` and `download_appx_m3u8` from root `itsgolu.py`.
    """

    @classmethod
    async def resolve_and_download(
        cls,
        url: str,
        clean_title: str,
        quality: str = "720p",
        custom_dir: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:APPX] Resolving lecture source: {safe_url}")

        target_q = quality if quality in ["144p", "240p", "360p", "480p", "720p", "1080p"] else None
        
        # 1. Resolve source using original helper
        try:
            lec_res = await asyncio.to_thread(original_helper.resolve_lecture_source, url, target_q)
        except Exception as e:
            raise ProviderResolutionError(f"APPX lecture source resolution failed: {e}")

        if lec_res.is_drm:
            raise DRMProtectedError(f"Content is DRM encrypted: {lec_res.drm_message or 'Widevine DRM'}")

        if not lec_res.has_video and not lec_res.has_pdf:
            raise ProviderResolutionError(f"No playable video or PDF found: {lec_res.error or 'Empty response'}")

        meta = {
            "title": lec_res.title,
            "thumbnail": lec_res.thumbnail,
            "pdf_url": lec_res.pdf_url,
            "video_id": lec_res.video_id,
            "course_id": lec_res.course_id,
            "has_video": lec_res.has_video,
            "has_pdf": lec_res.has_pdf,
            "video_quality": lec_res.video_quality
        }

        # 2. Download M3U8 stream using original download_appx_m3u8
        if not lec_res.video_url:
            if lec_res.has_pdf and lec_res.pdf_url:
                safe_pdf = sanitize_url_for_logging(lec_res.pdf_url)
                logger.info(f"[PROVIDER:APPX] Deterministic response: Video=NO | PDF=YES ({safe_pdf})")
                raise VideoUnavailableError(
                    f"No video stream URL returned by provider API (PDF available: {safe_pdf})",
                    pdf_url=lec_res.pdf_url,
                    metadata=meta
                )
            raise ProviderResolutionError("No video stream URL returned by provider API")

        safe_stream = sanitize_url_for_logging(lec_res.video_url)
        logger.info(f"[PROVIDER:APPX] Downloading stream: {safe_stream}")

        try:
            v_file = await asyncio.to_thread(
                original_helper.download_appx_m3u8,
                lec_res.video_url,
                clean_title,
                None,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"APPX stream download failed: {e}")

        if not v_file or not os.path.exists(v_file) or os.path.getsize(v_file) == 0:
            raise ProviderDownloadError("APPX video download produced empty or missing file.")

        # 3. Validate media
        val_info = await MediaValidator.validate_video_file(v_file)
        meta.update(val_info)

        return v_file, meta


class SpayeeProviderAdapter:
    """
    Adapter for Spayee / Spees / GoClasses HLS Streams.
    Reuses original `spayee_downloader.download_spayee_hls` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        quality: str = "720p",
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:SPAYEE] Downloading Spayee HLS: {safe_url}")

        key = None
        clean_stream = url
        if "*" in url:
            parts = url.split("*", 1)
            clean_stream = parts[0].strip()
            key = parts[1].strip()

        try:
            v_file = await asyncio.to_thread(
                original_spayee.download_spayee_hls,
                url,
                None, # output_path
                clean_title,
                key,
                quality,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"Spayee HLS download failed: {e}")

        if not v_file or not os.path.exists(v_file) or os.path.getsize(v_file) == 0:
            raise ProviderDownloadError("Spayee HLS download produced empty or missing file.")

        await MediaValidator.validate_video_file(v_file)
        return v_file


class KgsProviderAdapter:
    """
    Adapter for Khan Global Studies (KGS) Akamai HLS streams.
    Reuses original `kgs_downloader.download_kgs_hls` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        quality: str = "720p",
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:KGS] Downloading KGS HLS: {safe_url}")

        try:
            v_file = await asyncio.to_thread(
                original_kgs.download_kgs,
                url,
                clean_title,
                quality,
                None,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"KGS HLS download failed: {e}")

        if not v_file or not os.path.exists(v_file) or os.path.getsize(v_file) == 0:
            raise ProviderDownloadError("KGS HLS download produced empty or missing file.")

        await MediaValidator.validate_video_file(v_file)
        return v_file


class YouTubeProviderAdapter:
    """
    Adapter for YouTube source video extraction.
    Reuses original `download_video` and `youtube_fallback.py` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        quality: str = "720p",
        user_id: Optional[int] = None,
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:YOUTUBE] Downloading YouTube source: {safe_url}")

        try:
            # 1. Try original helper download_video
            yt_file = await original_helper.download_video(
                url,
                clean_title,
                quality,
                user_id=user_id,
                custom_dir=custom_dir or "downloads"
            )
            if yt_file and os.path.exists(yt_file) and os.path.getsize(yt_file) > 1024:
                await MediaValidator.validate_video_file(yt_file)
                return yt_file
        except Exception as e:
            logger.warning(f"[PROVIDER:YOUTUBE] Primary yt-dlp download failed: {e}, attempting fallback...")

        # 2. Try Vynex / YtUltra Fallback Resolvers
        try:
            resolved = (
                original_yt_fallback.resolve_youtube_vynex(url, quality=quality)
                or original_yt_fallback.resolve_youtube_ytultra(url, quality=quality)
            )
            if resolved:
                out_path = Path(custom_dir or "downloads") / f"{clean_title}.mp4"
                v_file = original_yt_fallback.download_media_stream_url(resolved, str(out_path), target_quality=quality)
                if v_file and os.path.exists(v_file) and os.path.getsize(v_file) > 1024:
                    await MediaValidator.validate_video_file(v_file)
                    return v_file
        except Exception as fb_e:
            logger.error(f"[PROVIDER:YOUTUBE] Fallback resolver failed: {fb_e}")

        raise ProviderDownloadError("YouTube source download failed via all resolvers.")


class EncryptedStreamAdapter:
    """
    Adapter for AES-128 / DragoAPI encrypted streams.
    Reuses original `download_and_decrypt_video` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:ENCRYPTED] Downloading and decrypting stream: {safe_url}")

        key = None
        clean_stream = url
        if "*" in url:
            parts = url.split("*", 1)
            clean_stream = parts[0].strip()
            key = parts[1].strip()

        try:
            enc_file = await asyncio.to_thread(
                original_helper.download_and_decrypt_video,
                clean_stream,
                clean_title,
                key,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"Encrypted stream download/decryption failed: {e}")

        if not enc_file or not os.path.exists(enc_file) or os.path.getsize(enc_file) == 0:
            raise ProviderDownloadError("Encrypted stream download produced empty or missing file.")

        await MediaValidator.validate_video_file(enc_file)
        return enc_file


class DirectM3u8Adapter:
    """
    Adapter for generic direct M3U8 HLS playlists.
    Reuses original `download_appx_m3u8` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:DIRECT_M3U8] Downloading M3U8 stream: {safe_url}")

        clean_stream = url.split("*")[0].strip()
        try:
            v_file = await asyncio.to_thread(
                original_helper.download_appx_m3u8,
                clean_stream,
                clean_title,
                None,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"Direct M3U8 stream download failed: {e}")

        if not v_file or not os.path.exists(v_file) or os.path.getsize(v_file) == 0:
            raise ProviderDownloadError("Direct M3U8 download produced empty or missing file.")

        await MediaValidator.validate_video_file(v_file)
        return v_file


class DirectVideoAdapter:
    """
    Adapter for direct video files (.mp4, .mkv, .webm, .ts, etc.).
    Reuses original `download_direct_video` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:DIRECT_VIDEO] Downloading direct video: {safe_url}")

        clean_stream = url.split("*")[0].strip()
        try:
            v_file = await asyncio.to_thread(
                original_helper.download_direct_video,
                clean_stream,
                clean_title,
                None,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"Direct video download failed: {e}")

        if not v_file or not os.path.exists(v_file) or os.path.getsize(v_file) == 0:
            raise ProviderDownloadError("Direct video download produced empty or missing file.")

        await MediaValidator.validate_video_file(v_file)
        return v_file


class PdfProviderAdapter:
    """
    Adapter for PDF documents (with or without password).
    Reuses original `download_pdf` and `pdf_unlocker.py` from root.
    """

    @classmethod
    async def download_and_process(
        cls,
        url: str,
        clean_title: str,
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:PDF] Downloading PDF document: {safe_url}")

        pdf_info = parse_pdf_input(url)
        raw_url = pdf_info["url"]
        pwd = pdf_info["password"]

        try:
            pdf_file = await original_helper.download_pdf(
                url=raw_url,
                name=clean_title,
                custom_dir=custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"PDF download failed: {e}")

        if not pdf_file or not os.path.exists(pdf_file) or os.path.getsize(pdf_file) == 0:
            raise ProviderDownloadError("PDF download produced empty or missing file.")

        # If password protected, unlock
        if pwd:
            logger.info(f"[PROVIDER:PDF] Unlocking password-protected PDF: {Path(pdf_file).name}")
            try:
                unlocked_path = Path(pdf_file).with_name(f"unlocked_{Path(pdf_file).name}")
                res = original_pdf_unlocker.unlock_pdf_file(
                    input_pdf=Path(pdf_file),
                    output_pdf=unlocked_path,
                    password=pwd
                )
                if res.is_success and unlocked_path.exists() and unlocked_path.stat().st_size > 0:
                    try:
                        os.remove(pdf_file)
                    except OSError:
                        pass
                    return str(unlocked_path)
            except Exception as un_e:
                logger.warning(f"[PROVIDER:PDF] Password unlock attempt failed: {un_e}")

        return pdf_file


class ImageProviderAdapter:
    """
    Adapter for direct images (.jpg, .png, .webp).
    Reuses original `download_image` from root.
    """

    @classmethod
    async def download(
        cls,
        url: str,
        clean_title: str,
        custom_dir: Optional[str] = None
    ) -> str:
        safe_url = sanitize_url_for_logging(url)
        logger.info(f"[PROVIDER:IMAGE] Downloading image: {safe_url}")

        clean_stream = url.split("*")[0].strip()
        try:
            img_file = await asyncio.to_thread(
                original_helper.download_image,
                clean_stream,
                clean_title,
                None,
                custom_dir or "downloads"
            )
        except Exception as e:
            raise ProviderDownloadError(f"Image download failed: {e}")

        if not img_file or not os.path.exists(img_file) or os.path.getsize(img_file) == 0:
            raise ProviderDownloadError("Image download produced empty or missing file.")

        return img_file


# ==============================================================================
# CENTRAL MEDIA DOWNLOADER ROUTER
# ==============================================================================

class UnifiedMediaDownloader:
    """
    Unified router that dispatches to the exact specialized original provider adapter
    based on the classified MediaType.
    """

    @classmethod
    async def download_video(
        cls,
        url: str,
        title: str,
        quality: str = "720p",
        user_id: Optional[int] = None,
        custom_dir: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        clean_title = re.sub(r'[\\/*?:"<>|]', "", title).strip() or f"lecture_{int(time.time())}"
        m_type = MediaRouter.classify_url(url)
        safe_log_url = sanitize_url_for_logging(url)

        logger.info(f"[ROUTER] Dispatching media type {m_type.value} for title='{clean_title}' url={safe_log_url}")

        meta: Dict[str, Any] = {"media_type": m_type.value}

        # 1. APPX LECTURE
        if m_type == MediaType.APPX_LECTURE:
            v_file, appx_meta = await AppxProviderAdapter.resolve_and_download(
                url=url,
                clean_title=clean_title,
                quality=quality,
                custom_dir=custom_dir
            )
            meta.update(appx_meta)
            return v_file, meta

        # 2. SPAYEE / GO CLASSES
        if m_type in (MediaType.SPAYEE_HLS, MediaType.GO_CLASSES):
            v_file = await SpayeeProviderAdapter.download(
                url=url,
                clean_title=clean_title,
                quality=quality,
                custom_dir=custom_dir
            )
            val = await MediaValidator.validate_video_file(v_file)
            meta.update(val)
            return v_file, meta

        # 3. KGS (Khan Global Studies)
        if m_type == MediaType.KGS_HLS:
            v_file = await KgsProviderAdapter.download(
                url=url,
                clean_title=clean_title,
                quality=quality,
                custom_dir=custom_dir
            )
            val = await MediaValidator.validate_video_file(v_file)
            meta.update(val)
            return v_file, meta

        # 4. YOUTUBE
        if m_type == MediaType.YOUTUBE:
            v_file = await YouTubeProviderAdapter.download(
                url=url,
                clean_title=clean_title,
                quality=quality,
                user_id=user_id,
                custom_dir=custom_dir
            )
            val = await MediaValidator.validate_video_file(v_file)
            meta.update(val)
            return v_file, meta

        # 5. ENCRYPTED STREAM
        if m_type == MediaType.ENCRYPTED_STREAM:
            v_file = await EncryptedStreamAdapter.download(
                url=url,
                clean_title=clean_title,
                custom_dir=custom_dir
            )
            val = await MediaValidator.validate_video_file(v_file)
            meta.update(val)
            return v_file, meta

        # 6. DIRECT M3U8
        if m_type == MediaType.DIRECT_M3U8:
            v_file = await DirectM3u8Adapter.download(
                url=url,
                clean_title=clean_title,
                custom_dir=custom_dir
            )
            val = await MediaValidator.validate_video_file(v_file)
            meta.update(val)
            return v_file, meta

        # 7. DIRECT VIDEO
        if m_type == MediaType.DIRECT_VIDEO:
            v_file = await DirectVideoAdapter.download(
                url=url,
                clean_title=clean_title,
                custom_dir=custom_dir
            )
            val = await MediaValidator.validate_video_file(v_file)
            meta.update(val)
            return v_file, meta

        # 8. DIRECT IMAGE
        if m_type == MediaType.DIRECT_IMAGE:
            img_file = await ImageProviderAdapter.download(
                url=url,
                clean_title=clean_title,
                custom_dir=custom_dir
            )
            meta["file_size"] = os.path.getsize(img_file)
            return img_file, meta

        raise ProviderError(f"Unsupported or unknown media provider for URL: {safe_log_url}")
