import os
import re
import sys
import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, Union

from config.settings import TEMP_DIR, DOWNLOADS_DIR
from providers.router import MediaRouter, MediaType, parse_pdf_input
from providers.adapters import (
    UnifiedMediaDownloader,
    AppxProviderAdapter,
    SpayeeProviderAdapter,
    KgsProviderAdapter,
    YouTubeProviderAdapter,
    EncryptedStreamAdapter,
    DirectM3u8Adapter,
    DirectVideoAdapter,
    PdfProviderAdapter,
    ImageProviderAdapter,
    MediaValidator,
    sanitize_url_for_logging,
    ProviderError,
    DRMProtectedError,
    MediaValidationError,
    VideoUnavailableError
)

logger = logging.getLogger(__name__)

class MediaDownloader:
    """
    Unified Media Downloader for Course Wallah Platform.
    Reuses protected downloader logic for APPX, Spayee, Direct Streams, YouTube, and PDFs
    with media stream validation and token/JWT log sanitization.
    """

    @classmethod
    async def download_video_stream_with_meta(
        cls,
        url: str,
        title: str,
        quality: str = "720p",
        user_id: Optional[int] = None,
        custom_dir: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Main entry point for downloading authorized video sources and returning companion metadata (such as pdf_url).
        """
        dest_dir = custom_dir or DOWNLOADS_DIR
        Path(dest_dir).mkdir(parents=True, exist_ok=True)

        v_file, meta = await UnifiedMediaDownloader.download_video(
            url=url,
            title=title,
            quality=quality,
            user_id=user_id,
            custom_dir=dest_dir
        )
        return str(v_file), meta

    @classmethod
    async def download_video_stream(
        cls,
        url: str,
        title: str,
        quality: str = "720p",
        user_id: Optional[int] = None,
        custom_dir: Optional[str] = None
    ) -> str:
        """
        Main entry point for downloading any authorized video source.
        Routes directly through UnifiedMediaDownloader to the specialized provider adapter.
        """
        v_file, _ = await cls.download_video_stream_with_meta(
            url=url,
            title=title,
            quality=quality,
            user_id=user_id,
            custom_dir=custom_dir
        )
        return v_file

    @classmethod
    async def download_pdf_notes(
        cls,
        url: str,
        title: str,
        custom_dir: Optional[str] = None
    ) -> str:
        """
        Downloads and unlocks PDF notes (with password support).
        """
        dest_dir = custom_dir or DOWNLOADS_DIR
        Path(dest_dir).mkdir(parents=True, exist_ok=True)

        pdf_file = await PdfProviderAdapter.download_and_process(
            url=url,
            clean_title=title,
            custom_dir=dest_dir
        )
        return str(pdf_file)
