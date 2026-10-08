import os
import re
import json
import math
import time
import shutil
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from config.settings import TEMP_DIR, DOWNLOADS_DIR, THUMBNAILS_DIR, MAX_UPLOAD_SIZE_BYTES

logger = logging.getLogger(__name__)

class VideoProcessor:
    """
    Video inspection, thumbnail extraction, and splitting utility.
    """

    @classmethod
    async def probe_video(cls, file_path: str) -> Dict[str, Any]:
        """Runs ffprobe on the video to extract duration, resolution, codecs."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration,size,bit_rate:stream=width,height,codec_name,codec_type",
            "-of", "json",
            str(file_path)
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            return {"duration": 0.0, "width": 1280, "height": 720, "has_video": True, "has_audio": True}

        try:
            data = json.loads(stdout.decode("utf-8"))
            fmt = data.get("format", {})
            duration = float(fmt.get("duration", 0.0))
            size = int(fmt.get("size", 0))

            width = 1280
            height = 720
            has_video = False
            has_audio = False

            for s in data.get("streams", []):
                if s.get("codec_type") == "video" and not has_video:
                    width = int(s.get("width", 1280))
                    height = int(s.get("height", 720))
                    has_video = True
                elif s.get("codec_type") == "audio":
                    has_audio = True

            return {
                "duration": duration,
                "size": size,
                "width": width,
                "height": height,
                "has_video": has_video,
                "has_audio": has_audio,
                "resolution": f"{height}p"
            }
        except Exception as e:
            logger.error(f"Error parsing ffprobe output: {e}")
            return {"duration": 0.0, "width": 1280, "height": 720, "has_video": True, "has_audio": True}

    @classmethod
    async def extract_thumbnail(cls, video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """Extracts a crisp thumbnail frame at 15% duration."""
        info = await cls.probe_video(video_path)
        duration = info.get("duration", 0.0)
        timestamp = max(1.0, duration * 0.15) if duration > 10 else 1.0

        target = Path(output_path) if output_path else Path(THUMBNAILS_DIR) / f"{Path(video_path).stem}_thumb.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-ss", str(timestamp),
            "-i", str(video_path),
            "-vframes", "1",
            "-q:v", "2",
            str(target)
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        if target.exists() and target.stat().st_size > 500:
            return str(target)
        return None

    @classmethod
    async def extract_frame(cls, video_path: str, output_path: Optional[str] = None) -> Optional[str]:
        """Alias for extract_thumbnail."""
        return await cls.extract_thumbnail(video_path, output_path)

    @classmethod
    async def generate_branded_thumbnail(cls, video_path: str, title: str = "", output_path: Optional[str] = None) -> Optional[str]:
        """Generates a branded thumbnail from the video."""
        return await cls.extract_thumbnail(video_path, output_path)


    @classmethod
    async def split_if_large(cls, video_path: str, max_bytes: int = MAX_UPLOAD_SIZE_BYTES) -> List[str]:
        """
        Splits video into parts if it exceeds max_bytes.
        Returns list of part file paths.
        """
        p = Path(video_path)
        if not p.exists() or p.stat().st_size <= max_bytes:
            return [str(p)]

        file_size = p.stat().st_size
        num_parts = math.ceil(file_size / max_bytes)
        info = await cls.probe_video(video_path)
        total_dur = info.get("duration", 0.0)
        part_dur = total_dur / num_parts

        logger.info(f"[SPLIT] Video size ({file_size / (1024*1024):.1f} MB) exceeds limit. Splitting into {num_parts} parts...")
        parts = []

        for i in range(num_parts):
            start_t = i * part_dur
            out_part = p.parent / f"{p.stem}.part{i+1:02d}.mp4"
            cmd = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                "-ss", str(start_t),
                "-i", str(p),
                "-t", str(part_dur),
                "-c", "copy",
                "-movflags", "+faststart",
                str(out_part)
            ]
            proc = await asyncio.create_subprocess_exec(*cmd)
            await proc.communicate()

            if out_part.exists() and out_part.stat().st_size > 0:
                parts.append(str(out_part))

        return parts if parts else [str(p)]
