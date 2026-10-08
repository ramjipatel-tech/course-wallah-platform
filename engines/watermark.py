import os
import re
import math
import time
import shutil
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

from config.settings import WATERMARK_TEXT, WATERMARK_OPACITY, WATERMARK_CRF, TEMP_DIR, DATA_DIR

logger = logging.getLogger(__name__)

class WatermarkEngine:
    """
    Professional Animated Watermark Engine for Course Wallah Platform.
    Applies continuous smooth moving watermarks across the video frame
    to protect content while maintaining viewer experience.
    """

    @classmethod
    def find_font_file(cls) -> Optional[str]:
        """Detects available system or local font file for FFmpeg drawtext."""
        candidates = [
            Path(DATA_DIR).parent / "assets" / "font.otf",
            Path(DATA_DIR).parent / "assets" / "font.ttf",
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("C:/Windows/Fonts/calibri.ttf"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
        ]
        for c in candidates:
            if c.exists():
                return str(c).replace("\\", "/").replace(":", "\\:")
        return None

    @classmethod
    def build_watermark_filter(
        cls,
        text: str = WATERMARK_TEXT,
        logo_path: Optional[str] = None,
        opacity: float = 0.45,
        animation_mode: str = "continuous_drift",
        interval: int = 8
    ) -> str:
        """
        Generates FFmpeg filter complex expression with smooth dynamic coordinates.
        """
        safe_text = text.replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")
        alpha_val = max(0.1, min(opacity, 0.9))

        # Smooth continuous floating 2D Lissajous curve / bouncing drift
        if animation_mode == "continuous_drift":
            # Continuous smooth movement across the screen using sin/cos of time
            x_expr = "(w-tw)/2 + ((w-tw)/2 - 30)*sin(2*PI*t/18)"
            y_expr = "(h-th)/2 + ((h-th)/2 - 30)*cos(2*PI*t/24)"
        elif animation_mode == "smooth_bounce":
            # Smooth triangular bounce
            x_expr = "mod(t*40\\, w-tw-40)+20"
            y_expr = "mod(t*25\\, h-th-40)+20"
        elif animation_mode == "corner_rotation":
            # Shift corners every `interval` seconds smoothly
            x_expr = f"if(lt(mod(t,{interval*4}),{interval}), 30, if(lt(mod(t,{interval*4}),{interval*2}), w-tw-30, if(lt(mod(t,{interval*4}),{interval*3}), w-tw-30, 30)))"
            y_expr = f"if(lt(mod(t,{interval*4}),{interval}), 30, if(lt(mod(t,{interval*4}),{interval*2}), 30, if(lt(mod(t,{interval*4}),{interval*3}), h-th-30, h-th-30)))"
        else:
            # Default smooth drift
            x_expr = "(w-tw)/2 + ((w-tw)/2 - 30)*sin(2*PI*t/18)"
            y_expr = "(h-th)/2 + ((h-th)/2 - 30)*cos(2*PI*t/24)"

        font_file = cls.find_font_file()
        font_arg = f"fontfile='{font_file}':" if font_file else ""

        # High aesthetic drawtext styling: Inter/Roboto/Arial with subtle shadow and border
        font_style = (
            f"drawtext={font_arg}"
            f"text='{safe_text}':"
            f"fontsize=h/26:"
            f"fontcolor=white@{alpha_val}:"
            f"borderw=1.5:"
            f"bordercolor=black@{alpha_val*0.8}:"
            f"shadowcolor=black@{alpha_val*0.6}:"
            f"shadowx=1:shadowy=1:"
            f"x='{x_expr}':"
            f"y='{y_expr}'"
        )
        return font_style

    @classmethod
    async def apply_watermark(
        cls,
        input_video: str,
        output_video: str,
        watermark_text: str = WATERMARK_TEXT,
        logo_path: Optional[str] = None,
        crf: int = WATERMARK_CRF,
        animation_mode: str = "continuous_drift",
        job_context: Optional[Any] = None
    ) -> str:
        """
        Applies animated dynamic watermark to video using optimized FFmpeg encoding.
        """
        in_path = Path(input_video)
        out_path = Path(output_video)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        vf = cls.build_watermark_filter(
            text=watermark_text,
            logo_path=logo_path,
            opacity=WATERMARK_OPACITY,
            animation_mode=animation_mode
        )

        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-i", str(in_path),
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", str(crf),
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(out_path)
        ]

        logger.info(f"[WATERMARK] Applying dynamic moving watermark to {in_path.name}...")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Watermark encoding failed: {err[:300]}")

        logger.info(f"[WATERMARK] Successfully watermarked: {out_path.name} ({out_path.stat().st_size / (1024*1024):.2f} MB)")
        return str(out_path)
