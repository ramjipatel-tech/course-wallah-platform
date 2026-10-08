import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from providers.adapters import NativeMediaHelper, AppxLectureResult

class TestUserAppxPayload(unittest.TestCase):
    def setUp(self):
        self.sample_payload = {
            "status": "success",
            "video_id": "207716",
            "course_id": "241",
            "youtube_url": None,
            "data": {
                "id": "207716",
                "parent_id": -1,
                "Title": "1. Number System: Decimal & Binary",
                "description": "",
                "hls_stream_type": "6",
                "enc_type": "1",
                "lecture_summary_url": "",
                "material_type": "VIDEO",
                "file_link": "https://liveclasses-so.classx.co.in/live/T_178006366843131504.m3u8?starttime_epoch=1780063668&endtime_epoch=1780150068&mode=4&timeshift=1&txCodecTempName=480so",
                "livestream_links": [],
                "low_latency_enabled": False,
                "video_player_token": "",
                "video_player_url": "",
                "video_player_lower_url": "",
                "download_url_higher_version": "",
                "download_url_lower_version": "",
                "study_material_link": "",
                "uhs_version": "0.00",
                "cookie_key": "",
                "cookie_value": "",
                "rec_domain": "",
                "zoom_token": "",
                "encrypted_links": [
                    {
                        "quality": "720p",
                        "path": "https://transcoded-videos.classx.co.in/videos/akstechnicalclasses-data/3797810-1780067763/hls-1ae40c/480p/master-4806727.586635016.m3u8?edge-cache-token=URLPrefix=aHR0cHM6Ly90cmFuc2NvZGVkLXZpZGVvcy5jbGFzc3guY28uaW4vdmlkZW9zL2Frc3RlY2huaWNhbGNsYXNzZXMtZGF0YS8zNzk3ODEwLTE3ODAwNjc3NjM~Expires=1791484777~Signature=j9hE8efNLSeRT1OQ2Bkn_DeY43dWTfrkoLtRuP5uJWWMjS3AjvBUrYW5x8yXdeO_7nnvStgzpQiCmurWR1rFCQ&bitrate=720",
                        "backup_url": "https://transcoded-videos.classx.co.in/videos/akstechnicalclasses-data/3797810-1780067763/hls-1ae40c/480p/master-4806727.586635016.m3u8?edge-cache-token=URLPrefix=aHR0cHM6Ly90cmFuc2NvZGVkLXZpZGVvcy5jbGFzc3guY28uaW4vdmlkZW9zL2Frc3RlY2huaWNhbGNsYXNzZXMtZGF0YS8zNzk3ODEwLTE3ODAwNjc3NjM~Expires=1791484777~Signature=j9hE8efNLSeRT1OQ2Bkn_DeY43dWTfrkoLtRuP5uJWWMjS3AjvBUrYW5x8yXdeO_7nnvStgzpQiCmurWR1rFCQ&bitrate=720",
                        "backup_url2": "https://transcoded-videos.classx.co.in/videos/akstechnicalclasses-data/3797810-1780067763/hls-1ae40c/480p/master-4806727.586635016.m3u8?edge-cache-token=URLPrefix=aHR0cHM6Ly90cmFuc2NvZGVkLXZpZGVvcy5jbGFzc3guY28uaW4vdmlkZW9zL2Frc3RlY2huaWNhbGNsYXNzZXMtZGF0YS8zNzk3ODEwLTE3ODAwNjc3NjM~Expires=1791484777~Signature=j9hE8efNLSeRT1OQ2Bkn_DeY43dWTfrkoLtRuP5uJWWMjS3AjvBUrYW5x8yXdeO_7nnvStgzpQiCmurWR1rFCQ&bitrate=720",
                        "key": ""
                    },
                    {
                        "quality": "480p",
                        "path": "https://transcoded-videos.classx.co.in/videos/akstechnicalclasses-data/3797810-1780067763/hls-1ae40c/480p/master-4806727.586635016.m3u8?edge-cache-token=URLPrefix=aHR0cHM6Ly90cmFuc2NvZGVkLXZpZGVvcy5jbGFzc3guY28uaW4vdmlkZW9zL2Frc3RlY2huaWNhbGNsYXNzZXMtZGF0YS8zNzk3ODEwLTE3ODAwNjc3NjM~Expires=1791484777~Signature=j9hE8efNLSeRT1OQ2Bkn_DeY43dWTfrkoLtRuP5uJWWMjS3AjvBUrYW5x8yXdeO_7nnvStgzpQiCmurWR1rFCQ",
                        "key": ""
                    }
                ],
                "thumbnail": "https://appx-content-v2.classx.co.in/paid_course4/2026-06-01-0_8773661221882507.png",
                "course_id": "241",
                "pdf_link": "https://static-db-v2.appx.co.in/paid_course4/2026-06-01-0_877431883497071.pdf?URLPrefix=aHR0cHM6Ly9zdGF0aWMtZGItdjIuYXBweC5jby5pbi9wYWlkX2NvdXJzZTQvMjAyNi0wNi0wMS0wXzg3NzQzMTg4MzQ5NzA3MS5wZGY&Expires=1791490368&KeyName=appx-pdf-keyset&Signature=Ytnpj6nUmhEW4OdFhebS72z0PDzMDmtdMGRcm29OgGu6pie51SGcZsCafzgXXvUXNv19oAECWGMat6v_eGDOCA",
                "duration_in_secs": "3088"
            },
            "fetch_method": "mobile+fw1",
            "_cached": True
        }

    @patch("requests.get")
    def test_resolve_user_payload_exact(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = self.sample_payload
        mock_get.return_value = mock_resp

        test_url = "https://appx-sign-urls-tes-9bef20f0ce55.herokuapp.com/fetch_video?api_base=akstechnicalclassesapi.akamai.net.in&course_id=241&video_id=207716&token=test"
        res = NativeMediaHelper.resolve_lecture_source(test_url, target_quality="720p")

        self.assertIsNotNone(res.video_url, "video_url must not be None")
        self.assertTrue("transcoded-videos.classx.co.in" in res.video_url)
        self.assertTrue(res.has_video)
        self.assertTrue(res.has_pdf)
        self.assertIsNotNone(res.pdf_url)
        self.assertTrue("static-db-v2.appx.co.in" in res.pdf_url)
        self.assertEqual(res.title, "1. Number System: Decimal & Binary")
        self.assertEqual(res.thumbnail, "https://appx-content-v2.classx.co.in/paid_course4/2026-06-01-0_8773661221882507.png")
        self.assertEqual(res.video_id, "207716")
        self.assertEqual(res.course_id, "241")
        self.assertFalse(res.is_drm)
        print("\n[TEST_SUCCESS] Extracted video:", res.video_url[:60], "...")
        print("[TEST_SUCCESS] Extracted PDF:", res.pdf_url[:60], "...")
        print("[TEST_SUCCESS] Extracted Title:", res.title)
        print("[TEST_SUCCESS] Extracted Thumbnail:", res.thumbnail)

if __name__ == "__main__":
    unittest.main()
