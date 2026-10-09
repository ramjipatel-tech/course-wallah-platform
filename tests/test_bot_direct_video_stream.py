import pytest
from unittest.mock import AsyncMock, MagicMock
from pyrogram.types import Message, Chat, Video as TgVideo

from db.connection import init_db, get_db_session
from db.repository import ContentRepository
from db.models import PublicationStatus, VideoStorageStatus
from storage.telegram_stream.client_pool import TelegramClientPool
from bot.handlers import publish_video_to_telegram_stream_and_db


@pytest.mark.asyncio
async def test_publish_video_to_telegram_stream_and_db():
    await init_db()

    pool = TelegramClientPool.get_instance()
    pool.storage_chat_id = -1009999999999

    # Mock Message
    mock_msg = MagicMock(spec=Message)
    mock_msg.id = 1234
    mock_msg.caption = "Test Physics Chapter 1"
    mock_msg.chat = MagicMock(spec=Chat)
    mock_msg.chat.id = 987654

    mock_video = MagicMock(spec=TgVideo)
    mock_video.file_name = "physics_ch1.mp4"
    mock_video.duration = 1800
    mock_video.file_size = 50 * 1024 * 1024
    mock_video.width = 1920
    mock_video.height = 1080

    mock_msg.video = mock_video
    mock_msg.document = None

    # Mock copy
    mock_storage_msg = MagicMock(spec=Message)
    mock_storage_msg.id = 55555
    mock_msg.copy = AsyncMock(return_value=mock_storage_msg)

    mock_client = MagicMock()

    ok, text, meta = await publish_video_to_telegram_stream_and_db(
        client=mock_client,
        message=mock_msg,
        user_id=987654,
        custom_title="Custom Physics Lecture"
    )

    assert ok is True
    assert meta["storage_msg_id"] == 55555
    assert meta["title"] == "Custom Physics Lecture"
    assert "/api/v1/stream/tg/55555" in meta["stream_url"]
    assert "isPlaying=true" in meta["web_player_url"]

    # Verify DB persistence
    async with get_db_session() as session:
        repo = ContentRepository(session)
        lecture = await repo.get_lecture_by_id(meta["lecture_id"])
        assert lecture is not None
        assert lecture.title == "Custom Physics Lecture"
        assert lecture.publication_status == PublicationStatus.PUBLISHED
        assert lecture.has_video is True

        assert lecture.video is not None
        assert len(lecture.video.storages) >= 1
        tg_st = next((s for s in lecture.video.storages if s.provider == "telegram_stream"), None)
        assert tg_st is not None
        assert tg_st.provider_video_id == "55555"
        assert tg_st.playback_url == "/api/v1/stream/tg/55555"
        assert tg_st.status == VideoStorageStatus.READY.value
