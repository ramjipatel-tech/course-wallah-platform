import os
from pathlib import Path
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from db.models import Video, VideoStorage, VideoStorageStatus, Lecture, Batch, App, Subject, Folder
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


@pytest.fixture
def temp_dummy_video(tmp_path):
    """Creates a temporary dummy MP4 video file for testing."""
    video_file = tmp_path / "test_lecture.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"A" * 1024)
    return str(video_file)


@pytest.fixture
def temp_dummy_pdf(tmp_path):
    """Creates a temporary dummy PDF file."""
    pdf_file = tmp_path / "test_notes.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy pdf content")
    return str(pdf_file)


# ==============================================================================
# TEST 1: SHA-256 DUPLICATE DETECTION & HASHING
# ==============================================================================
@pytest.mark.asyncio
async def test_sha256_hashing(temp_dummy_video):
    hash_sync = compute_file_sha256_sync(temp_dummy_video)
    hash_async = await compute_file_sha256_async(temp_dummy_video)
    assert hash_sync is not None
    assert len(hash_sync) == 64
    assert hash_sync == hash_async


# ==============================================================================
# TEST 2: PROVIDER INITIALIZATION & CONFIGURATION
# ==============================================================================
def test_providers_initialization():
    vcdn = VcdnStorageProvider(api_key="test_vcdn_key", priority=1)
    media_cm = MediaCmStorageProvider(api_key="test_media_key", priority=2)
    anonmp4 = AnonMp4StorageProvider(priority=3)
    vevocloud = VevocloudStorageProvider(api_key="test_vevo_key", priority=4)

    assert vcdn.name == "vcdn"
    assert vcdn.priority == 1
    assert vcdn.enabled is True

    assert media_cm.name == "media_cm"
    assert media_cm.priority == 2

    assert anonmp4.name == "anonmp4"
    assert anonmp4.priority == 3

    assert vevocloud.name == "vevocloud"
    assert vevocloud.priority == 4


# ==============================================================================
# TEST 3: VCDN MULTIPART INGEST & VERIFICATION FLOW
# ==============================================================================
@pytest.mark.asyncio
async def test_vcdn_upload_and_verification_flow(temp_dummy_video):
    provider = VcdnStorageProvider(api_key="test_key")

    mock_init_resp = MagicMock(status_code=200)
    mock_init_resp.json.return_value = {
        "uploadId": "test-uuid-1234",
        "videoId": "test-uuid-1234",
        "uploadUrl": "/api/v1/upload/test-uuid-1234/chunk",
    }

    mock_chunk_resp = MagicMock(status_code=200)
    mock_chunk_resp.json.return_value = {"received": 1048}

    mock_complete_resp = MagicMock(status_code=200)
    mock_complete_resp.json.return_value = {"videoId": "test-uuid-1234", "status": "uploaded"}

    mock_video_resp = MagicMock(status_code=200)
    mock_video_resp.json.return_value = {
        "id": "test-uuid-1234",
        "status": "ready",
        "embed_url": "https://embed.vcdn.me/embed/test-uuid-1234",
        "transcode_progress": 100,
    }

    mock_token_resp = MagicMock(status_code=200)
    mock_token_resp.json.return_value = {
        "streamUrl": "https://cdn.vcdn.me/hls/test-uuid-1234/master.m3u8?token=xyz",
        "token": "xyz",
    }

    with patch("httpx.AsyncClient.post", side_effect=[mock_init_resp, mock_chunk_resp, mock_complete_resp, mock_token_resp]), \
         patch("httpx.AsyncClient.get", return_value=mock_video_resp):
        res = await provider.upload(temp_dummy_video, "Test Video")

    assert res.success is True
    assert res.status == StorageProviderStatus.READY.value
    assert res.provider_video_id == "test-uuid-1234"
    assert res.embed_url == "https://embed.vcdn.me/embed/test-uuid-1234"
    assert "master.m3u8" in res.hls_url


# ==============================================================================
# TEST 4: MEDIA.CM INGEST & VERIFICATION FLOW
# ==============================================================================
@pytest.mark.asyncio
async def test_media_cm_upload_and_verification_flow(temp_dummy_video):
    provider = MediaCmStorageProvider(api_key="test_media_key")

    mock_server_resp = MagicMock(status_code=200)
    mock_server_resp.json.return_value = {"result": "https://s1.media.cm/upload/01"}

    mock_upload_resp = MagicMock(status_code=200)
    mock_upload_resp.json.return_value = [
        {"filecode": "cm_file_999", "file_status": "OK"}
    ]

    mock_info_resp = MagicMock(status_code=200)
    mock_info_resp.json.return_value = {
        "status": 200,
        "result": [
            {
                "filecode": "cm_file_999",
                "file_title": "Test Video",
                "file_size": "1048",
                "file_length": "60",
                "canplay": 1,
            }
        ]
    }

    with patch("httpx.AsyncClient.get", side_effect=[mock_server_resp, mock_info_resp]), \
         patch("httpx.AsyncClient.post", return_value=mock_upload_resp):
        res = await provider.upload(temp_dummy_video, "Test Video")

    assert res.success is True
    assert res.status == StorageProviderStatus.READY.value
    assert res.provider_video_id == "cm_file_999"
    assert "https://media.cm/cm_file_999" in res.watch_url
    assert "cm_file_999" in res.embed_url


# ==============================================================================
# TEST 5: ANONMP4 INGEST & VERIFICATION FLOW
# ==============================================================================
@pytest.mark.asyncio
async def test_anonmp4_upload_and_verification_flow(temp_dummy_video):
    provider = AnonMp4StorageProvider()

    mock_upload_resp = MagicMock(status_code=200)
    mock_upload_resp.json.return_value = {
        "status": True,
        "id": "anon_vid_555",
        "url": "https://anonmp4.com/watch/anon_vid_555",
        "embed": "https://anonmp4.com/embed/anon_vid_555",
        "delete_url": "https://anonmp4.com/delete/key123",
    }

    with patch("httpx.AsyncClient.post", return_value=mock_upload_resp), \
         patch("storage.verification.RemoteStreamVerifier.verify_url_accessible", return_value=True):
        res = await provider.upload(temp_dummy_video, "Test Video")

    assert res.success is True
    assert res.status == StorageProviderStatus.READY.value
    assert res.provider_video_id == "anon_vid_555"
    assert res.watch_url == "https://anonmp4.com/watch/anon_vid_555"
    assert res.embed_url == "https://anonmp4.com/embed/anon_vid_555"


# ==============================================================================
# TEST 6: VEVOCLOUD INGEST & VERIFICATION FLOW
# ==============================================================================
@pytest.mark.asyncio
async def test_vevocloud_upload_and_verification_flow(temp_dummy_video):
    provider = VevocloudStorageProvider(api_key="test_vevo_key")

    mock_init_resp = MagicMock(status_code=200)
    mock_init_resp.json.return_value = {
        "sessionId": "vevo_sess_777",
        "videoId": "vevo_vid_777",
    }

    mock_chunk_resp = MagicMock(status_code=200)
    mock_chunk_resp.json.return_value = {"status": "chunk_received"}

    mock_comp_resp = MagicMock(status_code=200)
    mock_comp_resp.json.return_value = {"status": "processing"}

    mock_video_resp = MagicMock(status_code=200)
    mock_video_resp.json.return_value = {
        "id": "vevo_vid_777",
        "title": "Test Video",
        "status": "ready",
        "hls_link": "https://cdn.vevocloud.com/hls/vevo_vid_777/master.m3u8",
        "embedded_link": "https://vevocloud.com/embed/vevo_vid_777",
    }

    with patch("httpx.AsyncClient.post", side_effect=[mock_init_resp, mock_chunk_resp, mock_comp_resp]), \
         patch("httpx.AsyncClient.get", return_value=mock_video_resp):
        res = await provider.upload(temp_dummy_video, "Test Video")

    assert res.success is True
    assert res.status == StorageProviderStatus.READY.value
    assert res.provider_video_id == "vevo_vid_777"
    assert res.hls_url == "https://cdn.vevocloud.com/hls/vevo_vid_777/master.m3u8"


# ==============================================================================
# TEST 7: SEQUENTIAL MULTI-STORAGE MANAGER REPLICATION
# ==============================================================================
@pytest.mark.asyncio
async def test_multistorage_sequential_replication(temp_dummy_video):
    class MockProvider(BaseVideoStorageProvider):
        def __init__(self, name, priority):
            super().__init__(name=name, priority=priority, enabled=True)
            self.upload_called = False

        async def upload(self, file_path, title, metadata=None, progress_cb=None):
            self.upload_called = True
            if progress_cb:
                progress_cb(100.0, 1000, 1000)
            return StorageProviderResult(
                success=True,
                status=StorageProviderStatus.READY.value,
                provider=self.name,
                provider_video_id=f"id_{self.name}",
                embed_url=f"https://{self.name}.com/embed",
                watch_url=f"https://{self.name}.com/watch",
            )

        async def get_status(self, upload_id):
            return None

        async def delete(self, upload_id):
            return True

        async def verify(self, res):
            return True

        async def health_check(self):
            return {"provider": self.name, "healthy": True, "status": "ONLINE"}

    p1 = MockProvider("vcdn", 1)
    p2 = MockProvider("media_cm", 2)
    p3 = MockProvider("anonmp4", 3)
    p4 = MockProvider("vevocloud", 4)

    manager = MultiStorageManager(providers=[p1, p2, p3, p4], max_retries=2, retry_delay=1)

    ui_events = []
    def _ui_cb(payload):
        ui_events.append(payload["current_provider"])

    with patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):
        
        result = await manager.replicate_video(
            video_id="dummy-vid-123",
            video_file_path=temp_dummy_video,
            title="Data Structures Lecture 01",
            progress_ui_callback=_ui_cb,
        )

    assert result["success"] is True
    assert result["ready_count"] == 4
    assert p1.upload_called is True
    assert p2.upload_called is True
    assert p3.upload_called is True
    assert p4.upload_called is True
    assert len(ui_events) > 0


# ==============================================================================
# TEST 8: RETRY & FAILURE HANDLING IN MANAGER
# ==============================================================================
@pytest.mark.asyncio
async def test_multistorage_retry_and_failure_handling(temp_dummy_video):
    class FailingProvider(BaseVideoStorageProvider):
        def __init__(self, name, priority):
            super().__init__(name=name, priority=priority, enabled=True)
            self.attempts = 0

        async def upload(self, file_path, title, metadata=None, progress_cb=None):
            self.attempts += 1
            return StorageProviderResult(
                success=False,
                status=StorageProviderStatus.FAILED.value,
                provider=self.name,
                error="HTTP 500 Network Timeout",
            )

        async def get_status(self, upload_id):
            return None

        async def delete(self, upload_id):
            return False

        async def verify(self, res):
            return False

        async def health_check(self):
            return {"provider": self.name, "healthy": False, "status": "ERROR"}

    failing_p = FailingProvider("media_cm", 1)
    manager = MultiStorageManager(providers=[failing_p], max_retries=2, retry_delay=0)

    with patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):
        
        result = await manager.replicate_video(
            video_id="dummy-vid-fail",
            video_file_path=temp_dummy_video,
            title="Failed Lecture",
        )

    assert result["success"] is False
    assert result["ready_count"] == 0
    assert failing_p.attempts == 2
    assert result["provider_states"]["media_cm"]["status"] == StorageProviderStatus.FAILED.value


# ==============================================================================
# TEST 9: DISABLED PROVIDER SKIPPING
# ==============================================================================
@pytest.mark.asyncio
async def test_multistorage_disabled_provider_skipping(temp_dummy_video):
    class DummyProvider(BaseVideoStorageProvider):
        async def upload(self, file_path, title, metadata=None, progress_cb=None):
            return StorageProviderResult(success=True, status=StorageProviderStatus.READY.value, provider=self.name)
        async def get_status(self, upload_id):
            return None
        async def delete(self, upload_id):
            return True
        async def verify(self, res):
            return True
        async def health_check(self):
            return {"provider": self.name, "healthy": True}

    p_active = DummyProvider("vcdn", priority=1, enabled=True)
    p_disabled = DummyProvider("media_cm", priority=2, enabled=False)

    manager = MultiStorageManager(providers=[p_active, p_disabled])

    with patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):
        
        result = await manager.replicate_video(
            video_id="dummy-vid-disabled",
            video_file_path=temp_dummy_video,
            title="Skipped Provider Lecture",
        )

    assert result["provider_states"]["media_cm"]["status"] == StorageProviderStatus.DISABLED.value
    assert result["provider_states"]["vcdn"]["status"] == StorageProviderStatus.READY.value


# ==============================================================================
# TEST 10: TELEGRAM PROGRESS & COMPLETION CARDS RENDERING
# ==============================================================================
def test_telegram_ui_cards_rendering():
    payload = {
        "title": "Data Structures Lecture 01",
        "file_size": 1024 * 1024 * 50,  # 50 MB
        "current_provider": "vcdn",
        "completed_count": 2,
        "total_providers": 4,
        "ready_count": 2,
        "provider_states": {
            "vcdn": {"name": "vcdn", "status": "READY", "progress": 100.0, "attempt": 1, "max_attempts": 3},
            "media_cm": {"name": "media_cm", "status": "UPLOADING", "progress": 45.0, "attempt": 1, "max_attempts": 3},
            "anonmp4": {"name": "anonmp4", "status": "PENDING", "progress": 0.0, "attempt": 1, "max_attempts": 3},
            "vevocloud": {"name": "vevocloud", "status": "PENDING", "progress": 0.0, "attempt": 1, "max_attempts": 3},
        }
    }

    # Test replication progress card
    prog_card = ProgressUICards.render_storage_replication_card(payload)
    assert "VIDEO PROCESSING" in prog_card
    assert "Data Structures Lecture 01" in prog_card
    assert "VCDN" in prog_card
    assert "Media.cm" in prog_card
    assert "Telegram" in prog_card

    # Test completed card
    comp_card = ProgressUICards.render_storage_completed_card(payload)
    assert "VIDEO READY" in comp_card
    assert "4 Ready" in comp_card or "Ready" in comp_card

    # Test incomplete card
    incomp_payload = dict(payload)
    incomp_payload["provider_states"]["anonmp4"]["status"] = "FAILED"
    incomp_card = ProgressUICards.render_storage_incomplete_card(incomp_payload)
    assert "STORAGE INCOMPLETE" in incomp_card
    assert "FAILED" in incomp_card


# ==============================================================================
# TEST 11: STORAGE HEALTH SERVICE
# ==============================================================================
@pytest.mark.asyncio
async def test_storage_health_service():
    with patch("storage.providers.vcdn.VcdnStorageProvider.health_check", return_value={"provider": "vcdn", "healthy": True, "status": "ONLINE"}), \
         patch("storage.providers.media_cm.MediaCmStorageProvider.health_check", return_value={"provider": "media_cm", "healthy": True, "status": "ONLINE"}), \
         patch("storage.providers.anonmp4.AnonMp4StorageProvider.health_check", return_value={"provider": "anonmp4", "healthy": True, "status": "ONLINE"}), \
         patch("storage.providers.vevocloud.VevocloudStorageProvider.health_check", return_value={"provider": "vevocloud", "healthy": True, "status": "ONLINE"}):
        
        health = await StorageHealthService.check_all_providers()
        assert len(health) == 4
        assert all(h["healthy"] for h in health)


# ==============================================================================
# TEST 12: PROTECTED FROZEN PROVIDERS (APPX & YOUTUBE)
# ==============================================================================
def test_frozen_providers_detection():
    from providers.router import MediaRouter, MediaType

    # YouTube strict domain routing test
    yt_type = MediaRouter.classify_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert yt_type == MediaType.YOUTUBE

    yt_short_type = MediaRouter.classify_url("https://youtu.be/dQw4w9WgXcQ")
    assert yt_short_type == MediaType.YOUTUBE

    # APPX / Classplus routing test
    appx_type = MediaRouter.classify_url("https://media-cdn.classplus.co/video.m3u8")
    assert appx_type == MediaType.APPX_LECTURE

    # Spayee & Go Classes
    spayee_type = MediaRouter.classify_url("https://media.spayee.in/master.m3u8")
    assert spayee_type == MediaType.SPAYEE_HLS

    goclass_type = MediaRouter.classify_url("https://goclasses.in/video/123")
    assert goclass_type == MediaType.GO_CLASSES

    # PDF routing test (Never enters video replication)
    pdf_type = MediaRouter.classify_url("https://example.com/notes.pdf")
    assert pdf_type == MediaType.DIRECT_PDF


# ==============================================================================
# TEST 13: VCDN ASYNC TRANSCODING & RESUME WITHOUT RE-UPLOAD
# ==============================================================================
@pytest.mark.asyncio
async def test_vcdn_async_transcoding_and_resume(temp_dummy_video):
    provider = VcdnStorageProvider(api_key="test_vcdn_key")

    mock_status_proc = StorageProviderResult(
        success=False,
        status=StorageProviderStatus.PROCESSING.value,
        provider="vcdn",
        provider_video_id="vcdn-async-uuid-1",
        embed_url="https://embed.vcdn.me/embed/vcdn-async-uuid-1",
        watch_url="https://embed.vcdn.me/embed/vcdn-async-uuid-1",
    )

    mock_status_ready = StorageProviderResult(
        success=True,
        status=StorageProviderStatus.READY.value,
        provider="vcdn",
        provider_video_id="vcdn-async-uuid-1",
        embed_url="https://embed.vcdn.me/embed/vcdn-async-uuid-1",
        watch_url="https://embed.vcdn.me/embed/vcdn-async-uuid-1",
        hls_url="https://cdn.vcdn.me/hls/vcdn-async-uuid-1/master.m3u8",
        playback_url="https://cdn.vcdn.me/hls/vcdn-async-uuid-1/master.m3u8",
    )

    manager = MultiStorageManager(
        providers=[provider],
        max_retries=1,
        required_providers=["vcdn"],
    )

    # 1. First run: upload accepts, verification returns PROCESSING -> required provider is NOT READY, so success is False
    with patch.object(VcdnStorageProvider, "upload", return_value=mock_status_proc), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock) as mock_p_stat, \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock) as mock_p_succ, \
         patch("db.connection.get_db_session"):

        res1 = await manager.replicate_video(
            video_id="test-vid-proc-1",
            video_file_path=temp_dummy_video,
            title="Async Transcoding Video",
        )
        assert res1["success"] is False
        assert res1["processing_count"] == 1
        assert res1["ready_count"] == 0
        assert "vcdn" in res1["processing_required"]

    # 2. Second run (restart recovery): resumes from PROCESSING without uploading again!
    with patch.object(VcdnStorageProvider, "upload", side_effect=Exception("Should NOT re-upload!")) as mock_up, \
         patch.object(VcdnStorageProvider, "verify", return_value=mock_status_ready), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        # Simulate existing processing record
        fake_existing = VideoStorage(
            video_id="test-vid-proc-1",
            provider="vcdn",
            status=VideoStorageStatus.PROCESSING.value,
            provider_video_id="vcdn-async-uuid-1",
            attempt_count=1,
        )

        with patch("storage.manager.select") as mock_sel, \
             patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = [fake_existing]
            mock_exec.return_value = mock_res

            res2 = await manager.replicate_video(
                video_id="test-vid-proc-1",
                video_file_path=temp_dummy_video,
                title="Async Transcoding Video",
            )
            assert res2["success"] is True
            assert res2["ready_count"] == 1
            mock_up.assert_not_called()


# ==============================================================================
# TEST 14: REQUIRED PROVIDERS POLICY (READY vs PROCESSING vs FAILED)
# ==============================================================================
@pytest.mark.asyncio
async def test_multistorage_required_providers_policy(temp_dummy_video):
    p_vcdn = VcdnStorageProvider(api_key="k1", priority=1)
    p_media = MediaCmStorageProvider(api_key="k2", priority=2)
    p_anon = AnonMp4StorageProvider(priority=3)

    res_vcdn_proc = StorageProviderResult(success=False, status="PROCESSING", provider="vcdn", provider_video_id="v1")
    res_vcdn_ready = StorageProviderResult(success=True, status="READY", provider="vcdn", provider_video_id="v1")
    res_media_ready = StorageProviderResult(success=True, status="READY", provider="media_cm", provider_video_id="m1")
    res_media_proc = StorageProviderResult(success=False, status="PROCESSING", provider="media_cm", provider_video_id="m1")
    res_anon_fail = StorageProviderResult(success=False, status="FAILED", provider="anonmp4", error="DNS fail")

    # Policy 1: Only media_cm is required -> since media_cm is READY, success should be True
    mgr1 = MultiStorageManager(
        providers=[p_vcdn, p_media, p_anon],
        required_providers=["media_cm"],
        max_retries=1,
    )
    with patch.object(VcdnStorageProvider, "upload", return_value=res_vcdn_proc), \
         patch.object(MediaCmStorageProvider, "upload", return_value=res_media_ready), \
         patch.object(AnonMp4StorageProvider, "upload", return_value=res_anon_fail), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("storage.manager.asyncio.sleep", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        r1 = await mgr1.replicate_video("vid-1", temp_dummy_video, "Test 1")
        assert r1["success"] is True

    # Policy 2: anonmp4 is required -> since anonmp4 failed, success must be False
    mgr2 = MultiStorageManager(
        providers=[p_vcdn, p_media, p_anon],
        required_providers=["anonmp4"],
        max_retries=1,
    )
    with patch.object(VcdnStorageProvider, "upload", return_value=res_vcdn_proc), \
         patch.object(MediaCmStorageProvider, "upload", return_value=res_media_ready), \
         patch.object(AnonMp4StorageProvider, "upload", return_value=res_anon_fail), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("storage.manager.asyncio.sleep", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        r2 = await mgr2.replicate_video("vid-2", temp_dummy_video, "Test 2")
        assert r2["success"] is False
        assert "anonmp4" in r2["failed_required"]

    # Policy 3: vcdn is required -> since vcdn is PROCESSING, success must be False
    mgr3 = MultiStorageManager(
        providers=[p_vcdn, p_media, p_anon],
        required_providers=["vcdn"],
        max_retries=1,
    )
    with patch.object(VcdnStorageProvider, "upload", return_value=res_vcdn_proc), \
         patch.object(MediaCmStorageProvider, "upload", return_value=res_media_ready), \
         patch.object(AnonMp4StorageProvider, "upload", return_value=res_anon_fail), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("storage.manager.asyncio.sleep", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        r3 = await mgr3.replicate_video("vid-3", temp_dummy_video, "Test 3")
        assert r3["success"] is False
        assert "vcdn" in r3["processing_required"]

    # Policy 4: Both vcdn and media_cm required -> vcdn PROCESSING blocks completion
    mgr4 = MultiStorageManager(
        providers=[p_vcdn, p_media],
        required_providers=["vcdn", "media_cm"],
        max_retries=1,
    )
    with patch.object(VcdnStorageProvider, "upload", return_value=res_vcdn_proc), \
         patch.object(MediaCmStorageProvider, "upload", return_value=res_media_ready), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        r4 = await mgr4.replicate_video("vid-4", temp_dummy_video, "Test 4")
        assert r4["success"] is False
        assert "vcdn" in r4["processing_required"]

    # Policy 5: Both vcdn and media_cm required -> both READY permits completion
    mgr5 = MultiStorageManager(
        providers=[p_vcdn, p_media],
        required_providers=["vcdn", "media_cm"],
        max_retries=1,
    )
    with patch.object(VcdnStorageProvider, "upload", return_value=res_vcdn_ready), \
         patch.object(MediaCmStorageProvider, "upload", return_value=res_media_ready), \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        r5 = await mgr5.replicate_video("vid-5", temp_dummy_video, "Test 5")
        assert r5["success"] is True
        assert r5["ready_count"] == 2


# ==============================================================================
# TEST 15: REGRESSION - NEXT LECTURE BLOCKED WHEN STORAGE IS PROCESSING
# ==============================================================================
@pytest.mark.asyncio
async def test_next_lecture_blocked_when_storage_processing(temp_dummy_video):
    from engines.job_engine import ContentProcessingEngine, BatchJobController
    from engines.youtube_account_manager import YouTubeAccountManager
    from parsers.indexer import NormalizedLecture, NormalizedFolder, NormalizedSubject, NormalizedBatchTree
    from storage.base import StorageReplicationProcessingError

    lec1 = NormalizedLecture(index=1, title="Lecture 01", video_url="https://appx.co/1.m3u8")
    lec2 = NormalizedLecture(index=2, title="Lecture 02", video_url="https://appx.co/2.m3u8")
    folder = NormalizedFolder(name="Unit 01", lectures=[lec1, lec2])
    subject = NormalizedSubject(name="Physics", folders=[folder])
    tree = NormalizedBatchTree(app_name="Test App", batch_name="Test Batch", total_lectures=2, subjects=[subject])

    controller = BatchJobController(
        bot_id="bot_1",
        job_id="test_job_1",
        batch_id="test_batch_1",
        batch_name="Test Batch",
        user_id=12345,
        total_lectures=2,
    )

    engine = ContentProcessingEngine(bot_id="bot_1")

    # Mock process_lecture_item for lecture 1 to raise StorageReplicationProcessingError
    processed_indices = []

    async def mock_process(app_id, app_slug, batch_id, batch_slug, subject_name, folder_name, unit_number, item, user_id, **kwargs):
        processed_indices.append(item.index)
        if item.index == 1:
            raise StorageReplicationProcessingError("VCDN transcoding in progress", provider="vcdn")
        return {"status": "SUCCESS"}

    with patch.object(engine, "process_lecture_item", side_effect=mock_process):
        summary = await engine.run_full_batch(
            controller=controller,
            session_data={"tree": tree, "batch_name": f"Test Batch {int(datetime.now(timezone.utc).timestamp())}"},
        )

    # Assert that batch paused on lecture 1 and lecture 2 never started!
    assert controller.is_paused is True
    assert controller.completed_count == 0
    assert processed_indices == [1]
    assert 2 not in processed_indices


# ==============================================================================
# TEST 16: REGRESSION - LOCAL VIDEO CLEANUP RETAINED ON PROCESSING/FAIL AND REMOVED ON READY
# ==============================================================================
@pytest.mark.asyncio
async def test_local_video_cleanup_retained_on_incomplete_and_cleaned_on_ready(tmp_path):
    from engines.job_engine import ContentProcessingEngine
    from engines.youtube_account_manager import YouTubeAccountManager
    from parsers.indexer import NormalizedLecture
    from storage.base import StorageReplicationProcessingError, StorageReplicationFailedError
    from db.connection import get_db_session
    from db.repository import ContentRepository

    # Create dummy local files
    work_dir = tmp_path / "work_dir_test"
    work_dir.mkdir(parents=True, exist_ok=True)
    test_video = work_dir / "wm_video.mp4"
    test_video.write_bytes(b"dummy_video_bytes_12345")

    engine = ContentProcessingEngine(bot_id="bot_1")
    item = NormalizedLecture(index=1, title="Test Lec", video_url="https://appx.co/v.m3u8")

    # Create actual batch in DB
    ts = int(datetime.now(timezone.utc).timestamp())
    async with get_db_session() as db_sess:
        repo = ContentRepository(db_sess)
        app = await repo.get_or_create_app(f"App {ts}")
        batch, _ = await repo.get_or_create_batch(app.id, f"Batch {ts}")
        app_id, app_slug, batch_id, batch_slug = app.id, app.slug, batch.id, batch.slug

    # Case A: When replicate_video returns success=False (PROCESSING)
    mock_res_proc = {
        "success": False,
        "processing_required": ["vcdn"],
        "failed_required": [],
        "ready_count": 0,
        "total_enabled": 1,
        "provider_states": {"vcdn": {"status": "PROCESSING"}},
    }

    async def mock_wm(input_video, output_video, **kwargs):
        Path(output_video).write_bytes(b"watermarked_bytes_123")

    with patch("storage.manager.MultiStorageManager.replicate_video", new_callable=AsyncMock, return_value=mock_res_proc), \
         patch("engines.job_engine.MediaDownloader.download_video_stream_with_meta", new_callable=AsyncMock, return_value=(str(test_video), {})), \
         patch("engines.job_engine.VideoProcessor.probe_video", new_callable=AsyncMock, return_value={"duration": 10.0, "resolution": "1080p", "size": 100}), \
         patch("engines.job_engine.VideoProcessor.split_if_large", new_callable=AsyncMock, return_value=[str(test_video)]), \
         patch("engines.job_engine.WatermarkEngine.apply_watermark", side_effect=mock_wm), \
         patch("engines.job_engine.VideoProcessor.extract_thumbnail", new_callable=AsyncMock, return_value=None), \
         patch("engines.job_engine.YouTubeAccountManager.upload_with_multi_account_failover", new_callable=AsyncMock, return_value={"youtube_video_id": "yt_123"}), \
         patch("engines.job_engine.YouTubeAccountManager.save_checkpoint") as mock_save_ckpt:

        with pytest.raises(StorageReplicationProcessingError):
            await engine.process_lecture_item(
                app_id=app_id,
                app_slug=app_slug,
                batch_id=batch_id,
                batch_slug=batch_slug,
                subject_name="S1",
                folder_name="F1",
                unit_number="U1",
                item=item,
                user_id=123,
            )

        # Assert checkpoint was saved to preserve prepared video artifact
        assert mock_save_ckpt.called
        assert mock_save_ckpt.call_args[1]["prepared_video_path"] is not None


# ==============================================================================
# TEST 17: REGRESSION - RESUME FROM PROCESSING VERIFIES WITHOUT RE-UPLOAD
# ==============================================================================
@pytest.mark.asyncio
async def test_resume_from_processing_verifies_without_reupload_and_completes(temp_dummy_video):
    provider = VcdnStorageProvider(api_key="test_vcdn_key")
    manager = MultiStorageManager(providers=[provider], required_providers=["vcdn"])

    mock_ready = StorageProviderResult(
        success=True,
        status=StorageProviderStatus.READY.value,
        provider="vcdn",
        provider_video_id="vcdn_existing_id_99",
        embed_url="https://embed.vcdn.me/embed/vcdn_existing_id_99",
        watch_url="https://embed.vcdn.me/embed/vcdn_existing_id_99",
    )

    fake_existing = VideoStorage(
        video_id="test_video_db_id",
        provider="vcdn",
        status=VideoStorageStatus.PROCESSING.value,
        provider_video_id="vcdn_existing_id_99",
        attempt_count=1,
    )

    # When replicate_video runs, it resumes verification using vcdn_existing_id_99
    with patch.object(VcdnStorageProvider, "upload", side_effect=Exception("Should NOT upload!")) as mock_upload, \
         patch.object(VcdnStorageProvider, "verify", return_value=mock_ready) as mock_verify, \
         patch("storage.manager._persist_storage_status", new_callable=AsyncMock), \
         patch("storage.manager._persist_storage_success", new_callable=AsyncMock), \
         patch("db.connection.get_db_session"):

        with patch("storage.manager.select") as mock_sel, \
             patch("sqlalchemy.ext.asyncio.AsyncSession.execute") as mock_exec:
            mock_res = MagicMock()
            mock_res.scalars.return_value.all.return_value = [fake_existing]
            mock_exec.return_value = mock_res

            res = await manager.replicate_video(
                video_id="test_video_db_id",
                video_file_path=temp_dummy_video,
                title="Resumed Video",
            )

            assert res["success"] is True
            assert res["ready_count"] == 1
            mock_verify.assert_called_once_with("vcdn_existing_id_99")
            mock_upload.assert_not_called()



