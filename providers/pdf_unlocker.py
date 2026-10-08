import os
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import requests
try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz  # PyMuPDF fallback
    except ImportError:
        fitz = None

from config.settings import TEMP_DIR, DOWNLOADS_DIR, WATERMARK_TEXT

logger = logging.getLogger(__name__)

def get_headers_for_pdf_url(url: str) -> Dict[str, str]:
    """
    Builds appropriate HTTP headers and Referer for downloading PDFs across different CDN providers:
    - AppX / ClassX / Akamai: https://player.akamai.net.in/ & https://akstechnicalclasses.classx.co.in
    - Spayee / Graphy: https://www.goclasses.in/
    - KGS / Khan Global: https://khanglobalstudies.com/
    - Generic / Direct S3 / CloudFront
    """
    clean_url = (url or "").lower()
    if any(k in clean_url for k in ("akamai.net.in", "classx.co.in", "appx.co.in", "classplusapp.com", "static-db")):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://player.akamai.net.in/",
            "Origin": "https://akstechnicalclasses.classx.co.in",
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Connection": "keep-alive"
        }
    elif any(k in clean_url for k in ("spayee.com", "goclasses.in", "spayee", "graphy.com")):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://www.goclasses.in/",
            "Origin": "https://www.goclasses.in",
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Connection": "keep-alive"
        }
    elif any(k in clean_url for k in ("khanglobalstudies", "kgs")):
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Referer": "https://khanglobalstudies.com/",
            "Origin": "https://khanglobalstudies.com",
            "Accept": "application/pdf,application/octet-stream,*/*"
        }
    else:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/pdf,application/octet-stream,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive"
        }

def download_pdf_file(url: str, output_path: Path, timeout: int = 60) -> Tuple[bool, str]:
    """Downloads PDF from URL with domain-aware headers and fallback validation."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        primary_headers = get_headers_for_pdf_url(url)
        header_variants = [
            primary_headers,
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Referer": "https://player.akamai.net.in/",
                "Origin": "https://akstechnicalclasses.classx.co.in",
                "Accept": "application/pdf,application/octet-stream,*/*"
            },
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/pdf,application/octet-stream,*/*"
            }
        ]

        last_err = ""
        for h in header_variants:
            try:
                with requests.get(url, headers=h, stream=True, timeout=timeout) as resp:
                    if resp.status_code == 200:
                        with open(output_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                                if chunk:
                                    f.write(chunk)
                        if output_path.exists() and output_path.stat().st_size > 0:
                            return True, "Success"
                    else:
                        last_err = f"HTTP Error {resp.status_code}"
            except Exception as e:
                last_err = str(e)

        return False, last_err or "Downloaded PDF is empty"
    except Exception as e:
        return False, str(e)


def apply_red_watermark_to_doc(doc: Any, watermark_text: str = "COURSE WALLAH"):
    """
    Applies a premium, stylish red watermark across every page of the PDF document:
    - Prominent diagonal central watermark in semi-transparent crimson red (won't obscure reading).
    - Subtitle badge ('★ EXCLUSIVE STUDY MATERIAL ★').
    - Header red accent line with branded title.
    - Footer red accent line with copyright and page numbering.
    """
    if not fitz or not doc:
        return

    total_pages = len(doc)
    text_to_apply = (watermark_text or WATERMARK_TEXT or "COURSE WALLAH").strip()
    sub_badge = "★ EXCLUSIVE STUDY MATERIAL ★"
    red_color = (0.88, 0.12, 0.16)
    dark_red = (0.75, 0.15, 0.18)

    for idx, page in enumerate(doc):
        try:
            rect = page.rect
            w = rect.width
            h = rect.height

            if w < 50 or h < 50:
                continue

            # 1. Main Diagonal Watermark in Center (-35 degrees)
            rot_angle = -35
            mat = fitz.Matrix(rot_angle)
            font_size = max(28, min(56, int(w / 11)))

            text_len_est = len(text_to_apply) * font_size * 0.55
            p_main = fitz.Point(w * 0.5 - (text_len_est * 0.38), h * 0.55)
            page.insert_text(
                p_main,
                text_to_apply,
                fontsize=font_size,
                fontname="helv",
                color=red_color,
                fill_opacity=0.18,
                morph=(p_main, mat),
                overlay=True
            )

            # Secondary Sub-Badge
            p_sub = fitz.Point(w * 0.5 - (len(sub_badge) * 5.5 * 0.38), h * 0.60)
            page.insert_text(
                p_sub,
                sub_badge,
                fontsize=10,
                fontname="helv",
                color=red_color,
                fill_opacity=0.14,
                morph=(p_sub, mat),
                overlay=True
            )

            # 2. Header Accent (for standard pages with enough margin)
            if h > 200 and w > 200:
                header_y = 28
                page.draw_line(
                    fitz.Point(36, header_y),
                    fitz.Point(w - 36, header_y),
                    color=red_color,
                    width=0.75,
                    stroke_opacity=0.6,
                    overlay=True
                )
                page.insert_text(
                    fitz.Point(36, header_y - 6),
                    f"📖 {text_to_apply}",
                    fontsize=8,
                    fontname="helv",
                    color=red_color,
                    fill_opacity=0.85,
                    overlay=True
                )

                # 3. Footer Accent
                footer_y = h - 28
                page.draw_line(
                    fitz.Point(36, footer_y),
                    fitz.Point(w - 36, footer_y),
                    color=red_color,
                    width=0.75,
                    stroke_opacity=0.6,
                    overlay=True
                )
                page.insert_text(
                    fitz.Point(36, footer_y + 12),
                    "Course Wallah Educational Platform • Verified Study Resource",
                    fontsize=7.5,
                    fontname="helv",
                    color=dark_red,
                    fill_opacity=0.75,
                    overlay=True
                )
                page_str = f"Page {idx + 1} of {total_pages}"
                page.insert_text(
                    fitz.Point(w - 36 - len(page_str) * 5.2, footer_y + 12),
                    page_str,
                    fontsize=7.5,
                    fontname="helv",
                    color=dark_red,
                    fill_opacity=0.75,
                    overlay=True
                )
        except Exception as pe:
            logger.warning(f"Could not apply watermark to PDF page #{idx + 1}: {pe}")


def validate_and_process_pdf(
    input_pdf: Path,
    output_pdf: Path,
    password: Optional[str] = None,
    watermark_text: Optional[str] = None
) -> Tuple[bool, int, str]:
    """
    Validates PDF, authenticates password if protected, applies stylish red watermark, and saves clean PDF.
    Returns (success, page_count, error_msg).
    """
    if not fitz:
        # Fallback if PyMuPDF not available
        if input_pdf.exists() and input_pdf.stat().st_size > 0:
            import shutil
            shutil.copy2(input_pdf, output_pdf)
            return True, 1, "PyMuPDF not installed, copied raw"
        return False, 0, "PyMuPDF not installed"

    try:
        doc = fitz.open(str(input_pdf))
    except Exception as e:
        return False, 0, f"Corrupted PDF file: {e}"

    try:
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                doc.close()
                return False, 0, "PDF is password-protected and invalid/no password was supplied"

        page_count = len(doc)
        text_to_apply = watermark_text or WATERMARK_TEXT or "COURSE WALLAH"

        if text_to_apply:
            apply_red_watermark_to_doc(doc, text_to_apply)

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        doc.save(
            str(output_pdf),
            garbage=4,
            deflate=True,
            clean=True
        )
        doc.close()
        return True, page_count, "Success"

    except Exception as e:
        if 'doc' in locals():
            try:
                doc.close()
            except Exception:
                pass
        return False, 0, f"Error processing PDF: {e}"
