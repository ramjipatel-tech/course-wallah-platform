import os
import sys
import unittest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root and parent to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
ROOT_DIR = BASE_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from providers.router import MediaRouter, MediaType
from providers.adapters import (
    sanitize_url_for_logging,
    MediaValidator,
    AppxProviderAdapter,
    SpayeeProviderAdapter,
    KgsProviderAdapter,
    YouTubeProviderAdapter,
    EncryptedStreamAdapter,
    DirectM3u8Adapter,
    DirectVideoAdapter,
    PdfProviderAdapter,
    ImageProviderAdapter,
    UnifiedMediaDownloader
)

class TestProviderCompatibility(unittest.IsolatedAsyncioTestCase):

    def test_01_url_classification_matrix(self):
        """Verify MediaRouter classifies all provider sources in exact priority order."""
        # 1. APPX
        appx_url = "https://appx-sign-urls-tes-9bef20f0ce55.herokuapp.com/fetch_video?api_base=akstechnicalclassesapi.akamai.net.in&course_id=241&video_id=219194&token=eyJ0eXAi..."
        self.assertEqual(MediaRouter.classify_url(appx_url), MediaType.APPX_LECTURE)

        # 2. SPAYEE
        spayee_url = "https://qcdn.spayee.in/transcoded/12345/master.m3u8*0123456789abcdef0123456789abcdef"
        self.assertEqual(MediaRouter.classify_url(spayee_url), MediaType.SPAYEE_HLS)

        # 3. KGS (Khan Global Studies)
        kgs_url = "https://kgs-video.khanglobalstudies.com/vod/12345/master.m3u8"
        self.assertEqual(MediaRouter.classify_url(kgs_url), MediaType.KGS_HLS)

        # 4. GO CLASSES
        goclasses_url = "https://goclasses.in/vod/stream/master.m3u8*my_aes_key"
        self.assertEqual(MediaRouter.classify_url(goclasses_url), MediaType.GO_CLASSES)

        # 5. YOUTUBE
        yt_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(MediaRouter.classify_url(yt_url), MediaType.YOUTUBE)
        yt_short = "https://youtu.be/dQw4w9WgXcQ"
        self.assertEqual(MediaRouter.classify_url(yt_short), MediaType.YOUTUBE)

        # 6. ENCRYPTED STREAM
        enc_url = "https://dragoapi.vercel.app/stream/test.m3u8*abc123key"
        self.assertEqual(MediaRouter.classify_url(enc_url), MediaType.ENCRYPTED_STREAM)

        # 7. DIRECT M3U8
        m3u8_url = "https://d111111abcdef8.cloudfront.net/out/v1/master.m3u8"
        self.assertEqual(MediaRouter.classify_url(m3u8_url), MediaType.DIRECT_M3U8)

        # 8. DIRECT VIDEO
        mp4_url = "https://cdn.example.com/videos/lecture_01.mp4"
        self.assertEqual(MediaRouter.classify_url(mp4_url), MediaType.DIRECT_VIDEO)

        # 9. DIRECT PDF
        pdf_url = "https://cdn.example.com/notes/chapter1.pdf*secretpwd"
        self.assertEqual(MediaRouter.classify_url(pdf_url), MediaType.DIRECT_PDF)

        # 10. DIRECT IMAGE
        img_url = "https://cdn.example.com/thumbnails/intro.jpg"
        self.assertEqual(MediaRouter.classify_url(img_url), MediaType.DIRECT_IMAGE)

    def test_02_log_sanitization(self):
        """Verify tokens, JWTs, keys, and session strings are completely redacted from logs."""
        raw_url = "https://api.example.com/fetch_video?course_id=241&video_id=219194&token=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.secret&session=secret_session"
        sanitized = sanitize_url_for_logging(raw_url)
        self.assertNotIn("eyJ0eXAi", sanitized)
        self.assertNotIn("secret_session", sanitized)
        self.assertIn("token=[REDACTED]", sanitized)
        self.assertIn("session=[REDACTED]", sanitized)
        self.assertIn("course_id=241", sanitized)

        raw_keyed = "https://qcdn.spayee.in/master.m3u8*0123456789abcdef0123456789abcdef"
        sanitized_keyed = sanitize_url_for_logging(raw_keyed)
        self.assertNotIn("0123456789abcdef", sanitized_keyed)
        self.assertIn("[KEY_PROTECTED]", sanitized_keyed)

    @patch("providers.adapters.original_helper.resolve_lecture_source")
    @patch("providers.adapters.original_helper.download_appx_m3u8")
    @patch("providers.adapters.MediaValidator.validate_video_file")
    async def test_03_appx_provider_adapter(self, mock_val, mock_dl, mock_res):
        """Verify AppxProviderAdapter calls original resolve_lecture_source and download_appx_m3u8."""
        mock_result = MagicMock()
        mock_result.is_drm = False
        mock_result.has_video = True
        mock_result.has_pdf = False
        mock_result.video_url = "https://transcoded.classx.co.in/master.m3u8"
        mock_result.title = "AppX Lecture Test"
        mock_result.thumbnail = "https://thumb.classx.co.in/img.png"
        mock_result.video_id = "101"
        mock_result.course_id = "202"
        mock_result.video_quality = "720p"
        mock_res.return_value = mock_result

        test_out_file = str(BASE_DIR / "downloads" / "test_appx_clip.mp4")
        mock_dl.return_value = test_out_file

        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=5000000):
            mock_val.return_value = {
                "valid": True,
                "file_path": test_out_file,
                "file_size": 5000000,
                "duration": 120.0,
                "resolution": "720p"
            }

            v_file, meta = await AppxProviderAdapter.resolve_and_download(
                url="https://test.appx.co.in/fetch_video?id=101",
                clean_title="test_appx_clip",
                quality="720p"
            )

            mock_res.assert_called_once()
            mock_dl.assert_called_once()
            self.assertEqual(v_file, test_out_file)
            self.assertEqual(meta["video_id"], "101")
            self.assertEqual(meta["duration"], 120.0)

    @patch("providers.adapters.original_spayee.download_spayee_hls")
    @patch("providers.adapters.MediaValidator.validate_video_file")
    async def test_04_spayee_provider_adapter(self, mock_val, mock_dl):
        """Verify SpayeeProviderAdapter invokes original spayee_downloader with AES key."""
        test_out = str(BASE_DIR / "downloads" / "test_spayee.mp4")
        mock_dl.return_value = test_out

        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=8000000):
            mock_val.return_value = {"valid": True, "duration": 300.0}

            v_file = await SpayeeProviderAdapter.download(
                url="https://qcdn.spayee.in/master.m3u8*0123456789abcdef0123456789abcdef",
                clean_title="test_spayee",
                quality="720p"
            )
            mock_dl.assert_called_once()
            self.assertEqual(v_file, test_out)

    @patch("providers.adapters.original_kgs.download_kgs")
    @patch("providers.adapters.MediaValidator.validate_video_file")
    async def test_05_kgs_provider_adapter(self, mock_val, mock_dl):
        """Verify KgsProviderAdapter invokes original kgs_downloader."""
        test_out = str(BASE_DIR / "downloads" / "test_kgs.mp4")
        mock_dl.return_value = test_out

        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=9000000):
            mock_val.return_value = {"valid": True, "duration": 450.0}

            v_file = await KgsProviderAdapter.download(
                url="https://kgs-video.khanglobalstudies.com/vod/123/master.m3u8",
                clean_title="test_kgs",
                quality="720p"
            )
            mock_dl.assert_called_once()
            self.assertEqual(v_file, test_out)

    @patch("providers.adapters.original_helper.download_video")
    @patch("providers.adapters.MediaValidator.validate_video_file")
    async def test_06_youtube_provider_adapter(self, mock_val, mock_dl):
        """Verify YouTubeProviderAdapter invokes original helper download_video."""
        test_out = str(BASE_DIR / "downloads" / "test_yt.mp4")
        mock_dl.return_value = test_out

        with patch("os.path.exists", return_value=True), patch("os.path.getsize", return_value=12000000):
            mock_val.return_value = {"valid": True, "duration": 600.0}

            v_file = await YouTubeProviderAdapter.download(
                url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                clean_title="test_yt",
                quality="720p"
            )
            mock_dl.assert_called_once()
            self.assertEqual(v_file, test_out)

if __name__ == "__main__":
    unittest.main()
