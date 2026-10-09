import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from db.connection import get_db_session, init_db
from db.models import App, Batch, Subject, Lecture, Video, VideoStorage, VideoStorageStatus, PublicationStatus
from providers.adapters import NativeMediaHelper
from engines.watermark import WatermarkEngine
from storage.providers.vcdn import VcdnStorageProvider

sample_payload = {
  "status": "success",
  "video_id": "207716",
  "course_id": "241",
  "data": {
    "id": "207716",
    "parent_id": -1,
    "Title": "1. Number System: Decimal & Binary",
    "description": "",
    "hls_stream_type": "6",
    "enc_type": "1",
    "material_type": "VIDEO",
    "file_link": "https://liveclasses-so.classx.co.in/live/T_178006366843131504.m3u8?starttime_epoch=1780063668&endtime_epoch=1780150068&mode=4&timeshift=1&txCodecTempName=480so",
    "encrypted_links": [
      {
        "quality": "720p",
        "path": "https://transcoded-videos.classx.co.in/videos/akstechnicalclasses-data/3797810-1780067763/hls-1ae40c/480p/master-4806727.586635016.m3u8?edge-cache-token=URLPrefix=aHR0cHM6Ly90cmFuc2NvZGVkLXZpZGVvcy5jbGFzc3guY28uaW4vdmlkZW9zL2Frc3RlY2huaWNhbGNsYXNzZXMtZGF0YS8zNzk3ODEwLTE3ODAwNjc3NjM~Expires=1791541677~Signature=N5o8Y5ZCBH-jZFlGp7LEjLXxzKHvn3NU2DPHqbsGgb2HsRfw8pnVD3RYTKHo5arBKAHHWdat_uZYRiYmVcgBDw&bitrate=720"
      },
      {
        "quality": "480p",
        "path": "https://transcoded-videos.classx.co.in/videos/akstechnicalclasses-data/3797810-1780067763/hls-1ae40c/480p/master-4806727.586635016.m3u8?edge-cache-token=URLPrefix=aHR0cHM6Ly90cmFuc2NvZGVkLXZpZGVvcy5jbGFzc3guY28uaW4vdmlkZW9zL2Frc3RlY2huaWNhbGNsYXNzZXMtZGF0YS8zNzk3ODEwLTE3ODAwNjc3NjM~Expires=1791541677~Signature=N5o8Y5ZCBH-jZFlGp7LEjLXxzKHvn3NU2DPHqbsGgb2HsRfw8pnVD3RYTKHo5arBKAHHWdat_uZYRiYmVcgBDw"
      }
    ],
    "thumbnail": "https://appx-content-v2.classx.co.in/paid_course4/2026-06-01-0_8773661221882507.png",
    "pdf_link": "https://static-db-v2.appx.co.in/paid_course4/2026-06-01-0_877431883497071.pdf"
  }
}

async def process_test_lecture():
    await init_db()
    print("=" * 60)
    print("1. PARSING LECTURE PAYLOAD")
    print("=" * 60)
    
    d = sample_payload["data"]
    title = d["Title"]
    video_url = d["encrypted_links"][0]["path"]
    pdf_url = d.get("pdf_link")
    thumbnail_url = d.get("thumbnail")
    quality = "480p"
    
    print(f"Title: {title}")
    print(f"Quality: {quality}")
    print(f"Video URL: {video_url[:80]}...")
    print(f"PDF URL: {pdf_url}")
    
    print("=" * 60)
    print("2. DOWNLOADING VIDEO STREAM (FFMPEG + SMART REFERER)")
    print("=" * 60)
    
    download_dir = "downloads"
    os.makedirs(download_dir, exist_ok=True)
    clean_title = "lecture_number_systems_01"
    raw_video_path = os.path.join(download_dir, f"{clean_title}.mp4")
    watermarked_path = os.path.join(download_dir, f"wm_{clean_title}.mp4")

    if not os.path.exists(raw_video_path):
        raw_video_path = NativeMediaHelper.download_appx_m3u8(
            url=video_url,
            clean_title=clean_title,
            custom_dir=download_dir
        )
    print(f"Raw Video on Disk: {raw_video_path} ({os.path.getsize(raw_video_path)} bytes)")
    
    print("=" * 60)
    print("3. APPLYING MOVING WATERMARK ('COURSE WALLAH')")
    print("=" * 60)
    
    if not os.path.exists(watermarked_path):
        await WatermarkEngine.apply_watermark(
            input_video=raw_video_path,
            output_video=watermarked_path,
            watermark_text="COURSE WALLAH"
        )
    print(f"Watermarked Video Ready: {watermarked_path} ({os.path.getsize(watermarked_path)} bytes)")
    
    print("=" * 60)
    print("4. UPLOADING WATERMARKED VIDEO TO VCDN")
    print("=" * 60)
    
    vcdn = VcdnStorageProvider()
    vcdn_result = await vcdn.upload(watermarked_path, title)
    print(f"VCDN Upload Result: success={vcdn_result.success}, status={vcdn_result.status}")
    print(f"VCDN Video ID: {vcdn_result.provider_video_id}")
    print(f"VCDN Embed URL: {vcdn_result.embed_url}")
    print(f"VCDN HLS URL: {vcdn_result.hls_url}")
    
    print("=" * 60)
    print("5. SAVING LECTURE IN DATABASE")
    print("=" * 60)
    
    async with get_db_session() as session:
        # Get or create dummy app, batch, subject, folder for local test
        from db.models import Folder
        app = await session.get(App, "app_technical_classes")
        if not app:
            app = App(id="app_technical_classes", name="Technical Classes", slug="technical-classes")
            session.add(app)
            
        batch = await session.get(Batch, "batch_digital_electronics")
        if not batch:
            batch = Batch(id="batch_digital_electronics", app_id="app_technical_classes", name="Digital Electronics", slug="digital-electronics")
            session.add(batch)
            
        subject = await session.get(Subject, "sub_unit_1")
        if not subject:
            subject = Subject(id="sub_unit_1", batch_id="batch_digital_electronics", name="Unit 1.0 Number Systems", slug="unit-1-number-systems")
            session.add(subject)

        folder = await session.get(Folder, "fld_unit_1")
        if not folder:
            folder = Folder(id="fld_unit_1", subject_id="sub_unit_1", name="Unit 1.0 Number Systems", slug="unit-1-number-systems")
            session.add(folder)
            
        lec_id = f"lec_test_{sample_payload['video_id']}"
        lec = await session.get(Lecture, lec_id)
        if not lec:
            lec = Lecture(
                id=lec_id,
                folder_id="fld_unit_1",
                subject_id="sub_unit_1",
                batch_id="batch_digital_electronics",
                title=title,
                slug="1-number-system-decimal-binary",
                lecture_index=1,
                has_video=True,
                has_pdf=bool(pdf_url),
                publication_status=PublicationStatus.PUBLISHED,
                source_url=video_url,
                source_pdf_url=pdf_url,
                thumbnail_url=thumbnail_url
            )
            session.add(lec)
            
        vid_id = f"vid_{sample_payload['video_id']}"
        vid = await session.get(Video, vid_id)
        if not vid:
            vid = Video(
                id=vid_id,
                lecture_id=lec_id,
                title=title,
                resolution=quality,
                duration=3088
            )
            session.add(vid)
            
        st_id = f"st_vcdn_{sample_payload['video_id']}"
        st = await session.get(VideoStorage, st_id)
        if not st:
            st = VideoStorage(
                id=st_id,
                video_id=vid_id,
                provider="vcdn",
                status=VideoStorageStatus.READY.value if vcdn_result.status == "READY" else VideoStorageStatus.PROCESSING.value,
                provider_video_id=vcdn_result.provider_video_id,
                embed_url=vcdn_result.embed_url,
                hls_url=vcdn_result.hls_url,
                playback_url=vcdn_result.playback_url or vcdn_result.embed_url
            )
            session.add(st)
        else:
            st.provider_video_id = vcdn_result.provider_video_id
            st.embed_url = vcdn_result.embed_url
            st.hls_url = vcdn_result.hls_url
            st.playback_url = vcdn_result.playback_url or vcdn_result.embed_url
            st.status = VideoStorageStatus.READY.value
            
        await session.commit()
        print(f"Lecture saved successfully: ID={lec_id}, Video={vid_id}, Storage={st_id}")

    print("=" * 60)
    print("ALL STEPS COMPLETED 100% SUCCESSFULLY!")
    print("=" * 60)

asyncio.run(process_test_lecture())
