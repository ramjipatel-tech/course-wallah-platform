import os
import sys
import re
import time
import base64
import uuid
import shutil
import logging
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Dict, Any, Union, Tuple, List
from urllib.parse import urlparse, urljoin

import requests
import m3u8

from config.settings import TEMP_DIR, DOWNLOADS_DIR
from providers.router import is_spayee_url

logger = logging.getLogger(__name__)

DEFAULT_SPAYEE_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.goclasses.in/",
}

def clean_spayee_key(key: Union[str, bytes]) -> bytes:
    if not key:
        raise ValueError("Invalid authorized AES-128 key")

    if isinstance(key, bytes):
        if len(key) == 16:
            return key
        raise ValueError("Invalid authorized AES-128 key")

    if not isinstance(key, str):
        raise ValueError("Invalid authorized AES-128 key")

    key_str = key.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", key_str):
        return bytes.fromhex(key_str)

    try:
        raw = base64.b64decode(key_str, validate=True)
        if len(raw) == 16:
            return raw
    except Exception:
        pass

    raise ValueError("Invalid authorized AES-128 key")

def parse_spayee_input(combined_url: str, explicit_key: Optional[str] = None) -> Tuple[str, Optional[str]]:
    if not combined_url or not isinstance(combined_url, str):
        raise ValueError("Empty or invalid Spayee URL.")

    clean_input = combined_url.strip()
    if "*" in clean_input:
        m3u8_url, key_str = clean_input.split("*", 1)
        return m3u8_url.strip(), key_str.strip()

    return clean_input, explicit_key.strip() if explicit_key else None

def create_spayee_session(headers: Optional[Dict[str, str]] = None, workers: int = 16) -> requests.Session:
    session = requests.Session()
    pool_size = max(64, (workers or 16) * 4)
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=pool_size,
        pool_maxsize=pool_size,
        max_retries=3
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(DEFAULT_SPAYEE_HEADERS)
    if headers and isinstance(headers, dict):
        session.headers.update(headers)
    return session

def _parse_height_from_uri(uri: str) -> int:
    m = re.search(r"(\d{3,4})p?", uri)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return 0

def select_spayee_variant(
    parsed_master: m3u8.M3U8,
    master_url: str,
    preferred_quality: Optional[str] = None
) -> Tuple[str, int]:
    variants = parsed_master.playlists
    if not variants:
        return master_url, 0

    scored = []
    for var in variants:
        uri = var.uri
        height = 0
        bandwidth = 0
        if var.stream_info:
            if var.stream_info.resolution and len(var.stream_info.resolution) >= 2:
                height = var.stream_info.resolution[1]
            if var.stream_info.bandwidth:
                bandwidth = var.stream_info.bandwidth
        if height == 0:
            height = _parse_height_from_uri(uri)

        resolved_uri = urljoin(master_url, uri)
        scored.append({"uri": resolved_uri, "height": height, "bandwidth": bandwidth})

    scored.sort(key=lambda x: (x["height"], x["bandwidth"]), reverse=True)

    if preferred_quality:
        target_m = re.search(r"(\d{3,4})", str(preferred_quality))
        if target_m:
            target_h = int(target_m.group(1))
            matches = [s for s in scored if s["height"] == target_h]
            if matches:
                return matches[0]["uri"], matches[0]["height"]

    chosen = scored[0]
    chosen_h = chosen["height"] if chosen["height"] > 0 else 720
    return chosen["uri"], chosen_h

def detect_separate_audio(parsed_master: m3u8.M3U8, master_url: str) -> Optional[str]:
    if not parsed_master or not parsed_master.media:
        return None
    for media in parsed_master.media:
        if getattr(media, "type", "").upper() == "AUDIO" and getattr(media, "uri", None):
            return urljoin(master_url, media.uri)
    return None

def _determine_segment_ext(uri: str, default_ext: str = ".ts") -> str:
    parsed = urlparse(uri)
    path = parsed.path.lower()
    for ext in (".ts", ".aac", ".m4s", ".mp4", ".m4a", ".fmp4"):
        if path.endswith(ext):
            return ext
    return default_ext

def download_segment_with_retry(
    session: requests.Session,
    segment_url: str,
    target_path: Path,
    segment_idx: int,
    max_retries: int = 3,
    chunk_size: int = 1024 * 1024
) -> int:
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path.stat().st_size

    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")

    for attempt in range(1, max_retries + 1):
        try:
            with session.get(segment_url, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)

            if tmp_path.exists() and tmp_path.stat().st_size > 0:
                if target_path.exists():
                    try:
                        target_path.unlink()
                    except OSError:
                        pass
                tmp_path.rename(target_path)
                return target_path.stat().st_size
            else:
                raise RuntimeError("Downloaded segment is 0 bytes")
        except Exception as exc:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
            if attempt < max_retries:
                time.sleep(1)
            else:
                raise RuntimeError(f"Spayee segment {segment_idx} failed: {exc}")
    return 0

def download_segments_parallel(
    session: requests.Session,
    segments: List[Tuple[int, str, str]],
    work_dir: Path,
    workers: int = 16,
    chunk_size: int = 1024 * 1024,
    stream_type: str = "Video",
    job_context: Optional[Any] = None
) -> None:
    total_segs = len(segments)
    if total_segs == 0:
        return

    workers_count = max(1, min(int(workers or 16), 32))
    lock = threading.Lock()
    completed_count = 0
    downloaded_bytes = 0
    t0 = time.time()
    last_log_time = t0
    errors = []

    def _worker(seg_info: Tuple[int, str, str]) -> None:
        nonlocal completed_count, downloaded_bytes, last_log_time
        seg_idx, seg_url, local_rel = seg_info
        seg_target = work_dir / local_rel

        if job_context and getattr(job_context, "is_cancelled", False):
            raise RuntimeError("Job cancelled by user")

        seg_size = download_segment_with_retry(
            session=session,
            segment_url=seg_url,
            target_path=seg_target,
            segment_idx=seg_idx,
            max_retries=3,
            chunk_size=chunk_size
        )

        with lock:
            completed_count += 1
            downloaded_bytes += seg_size
            now = time.time()
            if (now - last_log_time >= 3.0) or (completed_count == total_segs):
                last_log_time = now
                elapsed = max(0.1, now - t0)
                speed_mb = (downloaded_bytes / (1024 * 1024)) / elapsed
                pct = (completed_count / total_segs) * 100.0
                dl_mb = downloaded_bytes / (1024 * 1024)
                if job_context and hasattr(job_context, "update_progress"):
                    job_context.update_progress(pct, dl_mb)

    with ThreadPoolExecutor(max_workers=workers_count) as executor:
        futures = {executor.submit(_worker, seg): seg for seg in segments}
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                errors.append(str(exc))
                for f in futures:
                    f.cancel()
                break

    if errors:
        raise RuntimeError(f"SPAYEE_SEGMENT_FAILED: {errors[0]}")

def rewrite_local_playlist(
    source_m3u8_text: str,
    base_playlist_url: str,
    segments_dir_name: str,
    key_filename: str,
    is_encrypted: bool
) -> Tuple[str, List[Tuple[int, str, str]]]:
    lines = source_m3u8_text.splitlines()
    rewritten_lines = []
    segments = []
    seg_idx = 1

    for line in lines:
        stripped = line.strip()
        if not stripped:
            rewritten_lines.append(line)
            continue

        if stripped.startswith("#"):
            if stripped.startswith("#EXT-X-KEY:"):
                new_key_tag = re.sub(
                    r'URI=(?:"[^"]*"|\'[^\']*\'|[^\s,]*)',
                    f'URI="{key_filename}"',
                    stripped
                )
                rewritten_lines.append(new_key_tag)
            else:
                rewritten_lines.append(line)
        else:
            seg_url = urljoin(base_playlist_url, stripped)
            seg_ext = _determine_segment_ext(stripped, default_ext=".ts" if "video" in segments_dir_name else ".aac")
            local_rel = f"{segments_dir_name}/segment_{seg_idx:06d}{seg_ext}"
            segments.append((seg_idx, seg_url, local_rel))
            rewritten_lines.append(local_rel)
            seg_idx += 1

    return "\n".join(rewritten_lines) + "\n", segments

def process_spayee_ffmpeg(work_dir: Path, has_audio: bool, ffmpeg_bin: str = "ffmpeg") -> Path:
    video_m3u8 = work_dir / "video.m3u8"
    video_only_mp4 = work_dir / "video_only.mp4"
    final_mp4 = work_dir / "final.mp4"

    cmd_video = [
        ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
        "-allowed_extensions", "ALL", "-f", "hls", "-i", "video.m3u8",
        "-c", "copy", "-movflags", "+faststart", "video_only.mp4"
    ]
    res_video = subprocess.run(cmd_video, cwd=str(work_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res_video.returncode != 0 or not video_only_mp4.exists() or video_only_mp4.stat().st_size == 0:
        raise RuntimeError(f"FFmpeg video processing failed: {res_video.stderr.strip()[:300]}")

    if has_audio:
        audio_only_m4a = work_dir / "audio_only.m4a"
        cmd_audio = [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-allowed_extensions", "ALL", "-f", "hls", "-i", "audio.m3u8",
            "-c", "copy", "audio_only.m4a"
        ]
        res_audio = subprocess.run(cmd_audio, cwd=str(work_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_audio.returncode != 0 or not audio_only_m4a.exists() or audio_only_m4a.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg audio processing failed: {res_audio.stderr.strip()[:300]}")

        cmd_merge = [
            ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "warning",
            "-i", "video_only.mp4", "-i", "audio_only.m4a",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "copy",
            "-movflags", "+faststart", "final.mp4"
        ]
        res_merge = subprocess.run(cmd_merge, cwd=str(work_dir), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res_merge.returncode != 0 or not final_mp4.exists() or final_mp4.stat().st_size == 0:
            raise RuntimeError(f"FFmpeg merge failed: {res_merge.stderr.strip()[:300]}")
    else:
        shutil.copy2(video_only_mp4, final_mp4)

    return final_mp4

def validate_spayee_output(file_path: Path, ffprobe_bin: str = "ffprobe") -> bool:
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False
    try:
        cmd = [ffprobe_bin, "-v", "error", "-show_streams", str(file_path)]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            return "codec_type=video" in res.stdout
    except Exception:
        pass
    return file_path.exists() and file_path.stat().st_size > 1024

def download_spayee_hls(
    combined_url: str,
    output_path: Optional[Union[str, Path]] = None,
    name: Optional[str] = None,
    key: Optional[str] = None,
    quality: Optional[str] = None,
    job_context: Optional[Any] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> str:
    if not combined_url or not isinstance(combined_url, str) or not combined_url.strip():
        raise ValueError("Invalid or empty Spayee URL.")

    out_base = Path(DOWNLOADS_DIR)
    safe_title = re.sub(r'[\\/*?:"<>|]', "", name or "Spayee_Lecture").strip() or f"Spayee_Lecture_{int(time.time())}"
    if safe_title.endswith(".mp4"):
        safe_title = safe_title[:-4]

    target_output_file = Path(output_path) if output_path else out_base / f"{safe_title}.mp4"

    m3u8_url, auth_key_str = parse_spayee_input(combined_url, explicit_key=key)
    session = create_spayee_session(headers=headers)

    work_dir = Path(TEMP_DIR) / f"spayee_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    video_segments_dir = work_dir / "video_segments"
    audio_segments_dir = work_dir / "audio_segments"
    video_segments_dir.mkdir(exist_ok=True)

    try:
        resp_master = session.get(m3u8_url, timeout=30)
        if resp_master.status_code != 200:
            raise RuntimeError(f"Spayee playlist could not be fetched: HTTP {resp_master.status_code}")

        master_text = resp_master.text
        (work_dir / "master.m3u8").write_text(master_text, encoding="utf-8")

        parsed_master = m3u8.loads(master_text, uri=m3u8_url)
        has_variants = bool(parsed_master.is_variant and parsed_master.playlists)

        if has_variants:
            video_playlist_url, selected_height = select_spayee_variant(parsed_master, m3u8_url, preferred_quality=quality)
            resp_video = session.get(video_playlist_url, timeout=30)
            if resp_video.status_code != 200:
                raise RuntimeError(f"Spayee video playlist could not be fetched: HTTP {resp_video.status_code}")
            video_playlist_text = resp_video.text
            video_base_url = video_playlist_url
        else:
            video_playlist_text = master_text
            video_base_url = m3u8_url

        (work_dir / "video_source.m3u8").write_text(video_playlist_text, encoding="utf-8")

        audio_playlist_url = detect_separate_audio(parsed_master, m3u8_url) if has_variants else None
        has_separate_audio = False
        audio_playlist_text = ""
        audio_base_url = ""

        if audio_playlist_url:
            resp_audio = session.get(audio_playlist_url, timeout=30)
            if resp_audio.status_code == 200:
                audio_playlist_text = resp_audio.text
                (work_dir / "audio_source.m3u8").write_text(audio_playlist_text, encoding="utf-8")
                audio_base_url = audio_playlist_url
                audio_segments_dir.mkdir(exist_ok=True)
                has_separate_audio = True

        video_is_encrypted = "#EXT-X-KEY" in video_playlist_text and "AES-128" in video_playlist_text
        audio_is_encrypted = has_separate_audio and ("#EXT-X-KEY" in audio_playlist_text and "AES-128" in audio_playlist_text)

        if video_is_encrypted or audio_is_encrypted or auth_key_str:
            if not auth_key_str:
                raise ValueError("Spayee stream is encrypted with AES-128 but no key was provided.")
            aes_key_bytes = clean_spayee_key(auth_key_str)
            (work_dir / "video_key.bin").write_bytes(aes_key_bytes)
            if has_separate_audio:
                (work_dir / "audio_key.bin").write_bytes(aes_key_bytes)

        rewritten_video_m3u8, video_segments = rewrite_local_playlist(
            source_m3u8_text=video_playlist_text,
            base_playlist_url=video_base_url,
            segments_dir_name="video_segments",
            key_filename="video_key.bin",
            is_encrypted=video_is_encrypted
        )
        (work_dir / "video.m3u8").write_text(rewritten_video_m3u8, encoding="utf-8")

        audio_segments = []
        if has_separate_audio:
            rewritten_audio_m3u8, audio_segments = rewrite_local_playlist(
                source_m3u8_text=audio_playlist_text,
                base_playlist_url=audio_base_url,
                segments_dir_name="audio_segments",
                key_filename="audio_key.bin",
                is_encrypted=audio_is_encrypted
            )
            (work_dir / "audio.m3u8").write_text(rewritten_audio_m3u8, encoding="utf-8")

        download_segments_parallel(session, video_segments, work_dir, stream_type="Video", job_context=job_context)
        if has_separate_audio and audio_segments:
            download_segments_parallel(session, audio_segments, work_dir, stream_type="Audio", job_context=job_context)

        final_mp4 = process_spayee_ffmpeg(work_dir, has_audio=has_separate_audio)

        if not validate_spayee_output(final_mp4):
            raise RuntimeError("Spayee final video validation failed.")

        target_output_file.parent.mkdir(parents=True, exist_ok=True)
        if target_output_file.exists():
            try:
                target_output_file.unlink()
            except OSError:
                pass

        shutil.copy2(final_mp4, target_output_file)
        return str(target_output_file)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
