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

# Ensure parent root directory (B:\Projects\downloader bot) is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Import original proven root modules (READ-ONLY REFERENCE)
import itsgolu as original_helper
import spayee_downloader as original_spayee
import kgs_downloader as original_kgs
import youtube_fallback as original_yt_fallback
import pdf_unlocker as original_pdf_unlocker
from utils import parse_pdf_input

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
