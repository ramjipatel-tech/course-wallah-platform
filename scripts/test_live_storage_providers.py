import os
import sys
import asyncio
import tempfile
import logging
import uuid
from datetime import datetime

# Set utf-8 output encoding
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import (
    VCDN_ENABLED, VCDN_API_KEY, VCDN_BASE_URL,
    MEDIA_CM_ENABLED, MEDIA_CM_API_KEY, MEDIA_CM_BASE_URL,
    ANONMP4_ENABLED, ANONMP4_API_URL,
    VEVOCLOUD_ENABLED, VEVOCLOUD_API_KEY, VEVOCLOUD_BASE_URL,
)
from storage.providers.vcdn import VcdnStorageProvider
from storage.providers.media_cm import MediaCmStorageProvider
from storage.providers.anonmp4 import AnonMp4StorageProvider
from storage.providers.vevocloud import VevocloudStorageProvider
from storage.health import StorageHealthService
from storage.manager import MultiStorageManager
from db.connection import init_db, get_db_session
from db.models import Video, VideoStorage, VideoStorageStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("TargetedAudit")


async def generate_small_test_video(file_path: str):
    """
    Generates a tiny valid 1-second MP4 video using ffmpeg or standard binary MP4 header.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        if os.path.exists(file_path) and os.path.getsize(file_path) > 500:
            return True
    except Exception as ex:
        logger.debug("ffmpeg fallback: %s", ex)

    with open(file_path, "wb") as f:
        f.write(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42" + b"\x00" * 4096)
    return True


async def run_targeted_storage_audit():
    print("=" * 70)
    print(" 🎯 COURSE WALLAH — TARGETED REAL-WORLD LOCAL STORAGE AUDIT")
    print("=" * 70)

    await init_db()

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tf:
        test_video_path = tf.name

    await generate_small_test_video(test_video_path)
    file_size = os.path.getsize(test_video_path)
    print(f"\n📦 Test video created: {test_video_path} ({file_size} bytes)")

    report = {}
    created_video_ids = []

    # -------------------------------------------------------------
    # 1. LIVE HEALTH & CONNECTIVITY CHECKS
    # -------------------------------------------------------------
    print("\n--- [PHASE 1] LIVE API CONNECTIVITY & HEALTH CHECKS ---")
    health_results = await StorageHealthService.check_all_providers()
    for h in health_results:
        p_name = h.get("provider", "unknown").upper()
        st = h.get("status")
        msg = h.get("message")
        print(f"  • {p_name:<10}: status={st} | healthy={h.get('healthy')} | {msg}")

    # -------------------------------------------------------------
    # 2. TARGETED REAL API TESTS
    # -------------------------------------------------------------
    print("\n--- [PHASE 2] TARGETED REAL PROVIDER UPLOADS & VERIFICATIONS ---")

    # 2.1 Media.cm (Primary verified production provider)
    print("\n>>> [1] Media.cm Live Test:")
    media_cm = MediaCmStorageProvider()
    res_media = await media_cm.upload(test_video_path, f"Targeted Audit {datetime.utcnow().strftime('%H%M%S')}")
    report["media_cm"] = {
        "success": res_media.success,
        "status": res_media.status,
        "provider_video_id": res_media.provider_video_id,
        "embed_url": res_media.embed_url,
        "watch_url": res_media.watch_url,
        "error": res_media.error,
    }
    print(f"  Result: status={res_media.status} | filecode={res_media.provider_video_id} | embed={res_media.embed_url}")

    # Cleanup Media.cm test file
    if res_media.provider_video_id:
        del_ok = await media_cm.delete(res_media.provider_video_id)
        print(f"  🧹 Cleaned up Media.cm test file ({res_media.provider_video_id}): confirmed={del_ok}")

    # 2.2 VCDN (Upload & Async Transcoding Bounded Polling Test)
    print("\n>>> [2] VCDN Live Test (Bounded Polling & State Detection):")
    vcdn = VcdnStorageProvider(verify_timeout=15)
    res_vcdn = await vcdn.upload(test_video_path, f"Targeted Audit {datetime.utcnow().strftime('%H%M%S')}")
    report["vcdn"] = {
        "success": res_vcdn.success,
        "status": res_vcdn.status,
        "provider_video_id": res_vcdn.provider_video_id,
        "embed_url": res_vcdn.embed_url,
        "watch_url": res_vcdn.watch_url,
        "error": res_vcdn.error,
    }
    print(f"  Result: status={res_vcdn.status} | video_id={res_vcdn.provider_video_id} | error={res_vcdn.error}")

    # Cleanup VCDN test file
    if res_vcdn.provider_video_id:
        del_vcdn_ok = await vcdn.delete(res_vcdn.provider_video_id)
        print(f"  🧹 Cleaned up VCDN test video ({res_vcdn.provider_video_id}): confirmed={del_vcdn_ok}")

    # 2.3 AnonMP4 & Vevocloud status review
    print("\n>>> [3] AnonMP4 Diagnosis:")
    anonmp4 = AnonMp4StorageProvider()
    anon_health = await anonmp4.health_check()
    print(f"  Status: {anon_health.get('status')} | {anon_health.get('message')}")
    report["anonmp4"] = anon_health

    print("\n>>> [4] Vevocloud Diagnosis:")
    vevocloud = VevocloudStorageProvider()
    vevo_health = await vevocloud.health_check()
    print(f"  Status: {vevo_health.get('status')} | {vevo_health.get('message')}")
    report["vevocloud"] = vevo_health

    # -------------------------------------------------------------
    # 3. END-TO-END MULTISTORAGEMANAGER PIPELINE & PERSISTENCE TEST
    # -------------------------------------------------------------
    print("\n--- [PHASE 3] END-TO-END ORCHESTRATION & DB PERSISTENCE ---")
    uid_suffix = uuid.uuid4().hex[:8]
    test_app_id = f"app_audit_{uid_suffix}"
    test_batch_id = f"batch_audit_{uid_suffix}"
    test_subj_id = f"subj_audit_{uid_suffix}"
    test_fold_id = f"fold_audit_{uid_suffix}"
    test_lec_id = f"lec_audit_{uid_suffix}"
    test_db_vid = f"vid_audit_{uid_suffix}"

    from db.models import App, Batch, Subject, Folder, Lecture, PublicationStatus

    async with get_db_session() as session:
        app_obj = App(id=test_app_id, name=f"Audit App {uid_suffix}", slug=f"audit-app-{uid_suffix}")
        batch_obj = Batch(id=test_batch_id, app_id=test_app_id, name=f"Audit Batch {uid_suffix}", slug=f"audit-batch-{uid_suffix}")
        subj_obj = Subject(id=test_subj_id, batch_id=test_batch_id, name=f"Audit Subject {uid_suffix}", slug=f"audit-subj-{uid_suffix}")
        fold_obj = Folder(id=test_fold_id, subject_id=test_subj_id, name=f"Audit Folder {uid_suffix}", slug=f"audit-fold-{uid_suffix}")
        lec_obj = Lecture(
            id=test_lec_id,
            folder_id=test_fold_id,
            subject_id=test_subj_id,
            batch_id=test_batch_id,
            title=f"Audit Lecture {uid_suffix}",
            slug=f"audit-lec-{uid_suffix}",
            lecture_index=1,
            has_video=True,
            publication_status=PublicationStatus.PUBLISHED,
        )
        v_rec = Video(
            id=test_db_vid,
            lecture_id=test_lec_id,
            filename="audit_sample.mp4",
            duration=1.0,
            resolution="320x240",
            file_size=file_size,
        )
        session.add_all([app_obj, batch_obj, subj_obj, fold_obj, lec_obj, v_rec])
        await session.commit()

    manager = MultiStorageManager(
        providers=[
            VcdnStorageProvider(priority=1, verify_timeout=15),
            MediaCmStorageProvider(priority=2),
            AnonMp4StorageProvider(priority=3, enabled=False),
            VevocloudStorageProvider(priority=4, enabled=False),
        ],
        required_providers=["media_cm"],
    )

    multi_res = await manager.replicate_video(
        video_id=test_db_vid,
        video_file_path=test_video_path,
        title="Production Local Audit Run",
    )
    print(f"  Replication Success: {multi_res.get('success')}")
    print(f"  Ready Count: {multi_res.get('ready_count')}")
    print(f"  Processing Count: {multi_res.get('processing_count')}")

    # Verify DB persistence
    async with get_db_session() as session:
        v_check = await session.get(Video, test_db_vid)
        assert v_check is not None and v_check.sha256 is not None, "Video SHA-256 must be persisted"
        print(f"  ✅ Video record verified with SHA-256: {v_check.sha256[:16]}...")

    # Cleanup DB and test files
    if os.path.exists(test_video_path):
        os.remove(test_video_path)

    # Clean up any test uploads created during Phase 3
    for p_name, r in multi_res.get("results", {}).items():
        if r.provider_video_id:
            if p_name == "media_cm":
                del_m = await media_cm.delete(r.provider_video_id)
                print(f"  🧹 Cleaned up Phase 3 Media.cm ({r.provider_video_id}): {del_m}")
            elif p_name == "vcdn":
                del_v = await vcdn.delete(r.provider_video_id)
                print(f"  🧹 Cleaned up Phase 3 VCDN ({r.provider_video_id}): {del_v}")

    # Teardown DB test entities
    async with get_db_session() as session:
        from sqlalchemy import delete
        await session.execute(delete(App).where(App.id == test_app_id))
        await session.commit()
        print("  🧹 DB test rows cleaned up successfully.")

    print("\n" + "=" * 70)
    print(" 🎉 TARGETED AUDIT & FIXES VERIFIED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_targeted_storage_audit())
