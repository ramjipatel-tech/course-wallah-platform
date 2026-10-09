import os
import sys
import asyncio
import tempfile
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from storage.base import (
    BaseVideoStorageProvider,
    StorageProviderResult,
    StorageProviderStatus,
)
from storage.hashing import compute_file_sha256_sync, compute_file_sha256_async
from storage.providers.vcdn import VcdnStorageProvider
from storage.providers.media_cm import MediaCmStorageProvider
from storage.providers.anonmp4 import AnonMp4StorageProvider
from storage.providers.vevocloud import VevocloudStorageProvider
from storage.manager import MultiStorageManager
from storage.health import StorageHealthService
from bot.progress_ui import ProgressUICards
from providers.router import MediaRouter, MediaType
from db.connection import init_db


async def run_all_checks():
    print("=" * 60)
    print(" 🚀 STARTING LOCAL MULTI-STORAGE REPLICATION VERIFICATION")
    print("=" * 60)

    # Initialize DB & migrations
    await init_db()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        f.write(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"A" * 2048)
        dummy_video_path = f.name

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 dummy pdf notes content")
        dummy_pdf_path = f.name

    try:
        # Check 1: SHA-256 Hashing
        print("\n[CHECK 1] Testing SHA-256 duplicate calculation...")
        hash_sync = compute_file_sha256_sync(dummy_video_path)
        hash_async = await compute_file_sha256_async(dummy_video_path)
        assert len(hash_sync) == 64, "SHA-256 hash length must be 64 characters"
        assert hash_sync == hash_async, "Sync and Async hash calculations must match"
        print(f"  ✅ SHA-256: {hash_sync[:16]}... (PASS)")

        # Check 2: VCDN Provider Flow
        print("\n[CHECK 2] Testing VCDN Provider Upload & Verification...")
        vcdn = VcdnStorageProvider(api_key="mock_vcdn_key")
        mock_init = MagicMock(status_code=200)
        mock_init.json.return_value = {"uploadId": "vcdn-uuid-1", "videoId": "vcdn-uuid-1", "uploadUrl": "/api/v1/upload/vcdn-uuid-1/chunk"}
        mock_chunk = MagicMock(status_code=200)
        mock_chunk.json.return_value = {"received": 2048}
        mock_complete = MagicMock(status_code=200)
        mock_complete.json.return_value = {"videoId": "vcdn-uuid-1", "status": "uploaded"}
        mock_video = MagicMock(status_code=200)
        mock_video.json.return_value = {"id": "vcdn-uuid-1", "status": "ready", "embed_url": "https://embed.vcdn.me/embed/vcdn-uuid-1"}
        mock_token = MagicMock(status_code=200)
        mock_token.json.return_value = {"streamUrl": "https://cdn.vcdn.me/hls/vcdn-uuid-1/master.m3u8?token=xyz"}

        with patch("httpx.AsyncClient.post", side_effect=[mock_init, mock_chunk, mock_complete, mock_token]), \
             patch("httpx.AsyncClient.get", return_value=mock_video):
            res_vcdn = await vcdn.upload(dummy_video_path, "Test Lecture VCDN")
        assert res_vcdn.success and res_vcdn.status == "READY"
        print(f"  ✅ VCDN: Uploaded + Verified READY (Embed: {res_vcdn.embed_url})")

        # Check 3: Media.cm Provider Flow
        print("\n[CHECK 3] Testing Media.cm Provider Upload & Verification...")
        media_cm = MediaCmStorageProvider(api_key="mock_media_key")
        mock_srv = MagicMock(status_code=200)
        mock_srv.json.return_value = {"result": "https://s1.media.cm/upload/01"}
        mock_up = MagicMock(status_code=200)
        mock_up.json.return_value = [{"filecode": "cm_code_888", "file_status": "OK"}]
        mock_info = MagicMock(status_code=200)
        mock_info.json.return_value = {"status": 200, "result": [{"filecode": "cm_code_888", "canplay": 1}]}

        with patch("httpx.AsyncClient.get", side_effect=[mock_srv, mock_info]), \
             patch("httpx.AsyncClient.post", return_value=mock_up):
            res_media = await media_cm.upload(dummy_video_path, "Test Lecture Media.cm")
        assert res_media.success and res_media.status == "READY"
        print(f"  ✅ Media.cm: Uploaded + Verified READY (Watch: {res_media.watch_url})")

        # Check 4: AnonMP4 Provider Flow
        print("\n[CHECK 4] Testing AnonMP4 Provider Upload & Verification...")
        anonmp4 = AnonMp4StorageProvider()
        mock_anon_up = MagicMock(status_code=200)
        mock_anon_up.json.return_value = {
            "status": True,
            "id": "anon_code_999",
            "url": "https://anonmp4.com/watch/anon_code_999",
            "embed": "https://anonmp4.com/embed/anon_code_999",
        }
        with patch("httpx.AsyncClient.post", return_value=mock_anon_up), \
             patch("storage.verification.RemoteStreamVerifier.verify_url_accessible", return_value=True):
            res_anon = await anonmp4.upload(dummy_video_path, "Test Lecture AnonMP4")
        assert res_anon.success and res_anon.status == "READY"
        print(f"  ✅ AnonMP4: Uploaded + Verified READY (Watch: {res_anon.watch_url})")

        # Check 5: Vevocloud Provider Flow
        print("\n[CHECK 5] Testing Vevocloud Provider Upload & Verification...")
        vevocloud = VevocloudStorageProvider(api_key="mock_vevo_key")
        mock_vevo_init = MagicMock(status_code=200)
        mock_vevo_init.json.return_value = {"sessionId": "vevo_sess_1", "videoId": "vevo_vid_1"}
        mock_vevo_chunk = MagicMock(status_code=200)
        mock_vevo_chunk.json.return_value = {"status": "chunk_received"}
        mock_vevo_comp = MagicMock(status_code=200)
        mock_vevo_comp.json.return_value = {"status": "processing"}
        mock_vevo_vid = MagicMock(status_code=200)
        mock_vevo_vid.json.return_value = {
            "id": "vevo_vid_1",
            "status": "ready",
            "hls_link": "https://cdn.vevocloud.com/hls/vevo_vid_1/master.m3u8",
        }
        with patch("httpx.AsyncClient.post", side_effect=[mock_vevo_init, mock_vevo_chunk, mock_vevo_comp]), \
             patch("httpx.AsyncClient.get", return_value=mock_vevo_vid):
            res_vevo = await vevocloud.upload(dummy_video_path, "Test Lecture Vevocloud")
        assert res_vevo.success and res_vevo.status == "READY"
        print(f"  ✅ Vevocloud: Uploaded + Verified READY (HLS: {res_vevo.hls_url})")

        # Check 6: Sequential MultiStorageManager Orchestration
        print("\n[CHECK 6] Testing MultiStorageManager Sequential Orchestration across 4 providers...")
        manager = MultiStorageManager(
            providers=[
                VcdnStorageProvider(api_key="k1", priority=1),
                MediaCmStorageProvider(api_key="k2", priority=2),
                AnonMp4StorageProvider(priority=3),
                VevocloudStorageProvider(api_key="k4", priority=4),
            ],
            max_retries=2,
            retry_delay=0,
        )

        with patch.object(VcdnStorageProvider, "upload", return_value=res_vcdn), \
             patch.object(MediaCmStorageProvider, "upload", return_value=res_media), \
             patch.object(AnonMp4StorageProvider, "upload", return_value=res_anon), \
             patch.object(VevocloudStorageProvider, "upload", return_value=res_vevo), \
             patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
             patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
             patch("db.connection.get_db_session"):
            
            multi_res = await manager.replicate_video(
                video_id="dummy-vid-uuid",
                video_file_path=dummy_video_path,
                title="Advanced Data Structures",
            )
        assert multi_res["success"] is True
        assert multi_res["ready_count"] == 4
        print(f"  ✅ Sequential MultiStorageManager: 4/4 providers verified READY (PASS)")

        # Check 7: Telegram Progress UI Card Formats
        print("\n[CHECK 7] Testing Telegram UI Cards formatting...")
        rep_card = ProgressUICards.render_storage_replication_card(multi_res)
        assert "VIDEO PROCESSING" in rep_card
        assert "VCDN" in rep_card and "Media.cm" in rep_card

        comp_card = ProgressUICards.render_storage_completed_card(multi_res)
        assert "VIDEO READY" in comp_card

        incomp_card = ProgressUICards.render_storage_incomplete_card(multi_res)
        assert "STORAGE INCOMPLETE" in incomp_card
        print("  ✅ Telegram UI Cards: Replication, Completed, and Incomplete rendered cleanly (PASS)")

        # Check 8: Frozen Router Tests
        print("\n[CHECK 8] Testing Frozen Provider Routing Integrity...")
        yt_type = MediaRouter.classify_url("https://www.youtube.com/watch?v=sample123")
        assert yt_type == MediaType.YOUTUBE, "YouTube must be strictly detected as YOUTUBE"

        appx_type = MediaRouter.classify_url("https://media-cdn.classplus.co/video.m3u8")
        assert appx_type == MediaType.APPX_LECTURE, "APPX must be strictly detected as APPX_LECTURE"

        spayee_type = MediaRouter.classify_url("https://media.spayee.in/master.m3u8")
        assert spayee_type == MediaType.SPAYEE_HLS, "Spayee must NOT fall into YouTube"

        goclass_type = MediaRouter.classify_url("https://goclasses.in/video/123")
        assert goclass_type == MediaType.GO_CLASSES, "GoClasses must NOT fall into YouTube"

        pdf_type = MediaRouter.classify_url("https://example.com/notes.pdf")
        assert pdf_type == MediaType.DIRECT_PDF, "PDF must route strictly to PDF and never video replication"
        print("  ✅ Frozen Provider Protection: APPX, YouTube, Spayee, GoClasses, and PDF routing 100% verified (PASS)")

        print("\n" + "=" * 60)
        print(" 🎉 ALL LOCAL INTEGRATION AND REPLICATION CHECKS PASSED!")
        print("=" * 60)

    finally:
        if os.path.exists(dummy_video_path):
            os.remove(dummy_video_path)
        if os.path.exists(dummy_pdf_path):
            os.remove(dummy_pdf_path)


if __name__ == "__main__":
    asyncio.run(run_all_checks())
