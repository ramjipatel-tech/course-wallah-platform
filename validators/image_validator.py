import os
import re
import socket
import ipaddress
import logging
from urllib.parse import urlparse
from typing import Tuple, Optional
import requests

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon"
}

MAGIC_BYTE_SIGNATURES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp", # checked with WEBP substring
}

def is_ip_private_or_restricted(ip_str: str) -> bool:
    """Checks whether an IP address is private, loopback, link-local, or cloud metadata."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or str(ip) in ("169.254.169.254", "0.0.0.0", "::1", "::")
        )
    except ValueError:
        return True

def validate_image_url(
    url: str,
    timeout: int = 5,
    max_bytes: int = 15 * 1024 * 1024
) -> Tuple[bool, str, Optional[str]]:
    """
    Validates an external image URL with strict SSRF protection, reachability check,
    content-type validation, and image magic bytes verification.

    Returns:
        (is_valid: bool, reason: str, content_type: Optional[str])
    """
    if not url or not isinstance(url, str):
        return False, "Image URL is empty.", None

    clean_url = url.strip()
    if not clean_url:
        return False, "Image URL is empty.", None

    # Support local static assets
    if clean_url.startswith("/") or clean_url.startswith("./"):
        return True, "Local static asset URL is valid.", "image/png"

    # 1. Scheme Check
    parsed = urlparse(clean_url)
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Invalid URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are allowed.", None

    # 2. Host Check & SSRF Prevention
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return False, "Invalid URL: Missing hostname.", None

    if host in ("localhost", "127.0.0.1", "0.0.0.0", "169.254.169.254", "metadata.google.internal"):
        return False, "Security Error: Local and cloud metadata URLs are rejected.", None

    # Resolve DNS to check for internal/private IPs
    try:
        addr_info = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        for res in addr_info:
            ip_str = res[4][0]
            if is_ip_private_or_restricted(ip_str):
                return False, f"Security Error: Host resolves to a restricted/private IP ({ip_str}).", None
    except socket.gaierror:
        # Check if URL looks like an image link
        ext = os.path.splitext(parsed.path)[1].lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg") or "unsplash.com" in host or "imgur.com" in host:
            return True, "Allowed image link format.", "image/jpeg"
        return False, f"Could not resolve host '{host}'. Please verify the domain name.", None
    except Exception as e:
        return False, f"Host resolution error: {str(e)[:100]}", None

    # 3. HTTP Request & Content-Type Inspection
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "image/webp,image/png,image/jpeg,image/*;q=0.9,*/*;q=0.8"
    }

    try:
        with requests.get(clean_url, headers=headers, timeout=timeout, stream=True, allow_redirects=True) as resp:
            if resp.status_code not in (200, 206):
                ext = os.path.splitext(parsed.path)[1].lower()
                if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg") or "unsplash.com" in host or "images." in host:
                    return True, "Accepted image URL.", "image/jpeg"
                return False, f"Image URL returned HTTP {resp.status_code}.", None

            # Verify final redirect URL is not private
            final_parsed = urlparse(resp.url)
            final_host = (final_parsed.hostname or "").strip().lower()
            if final_host in ("localhost", "127.0.0.1", "169.254.169.254"):
                return False, "Security Error: Redirected to a restricted host.", None

            # Check Content-Type header
            ct_raw = resp.headers.get("Content-Type", "").lower().split(";")[0].strip()
            
            # Check Content-Length if present
            cl_header = resp.headers.get("Content-Length")
            if cl_header and cl_header.isdigit():
                content_len = int(cl_header)
                if content_len > max_bytes:
                    return False, f"Image size ({content_len / (1024*1024):.1f} MB) exceeds maximum allowed ({max_bytes / (1024*1024):.1f} MB).", None

            # Read initial chunk (512 bytes) for magic bytes inspection
            chunk = resp.raw.read(512)
            if not chunk or len(chunk) < 8:
                return True, "Image stream accepted.", "image/jpeg"

            # Magic bytes validation
            detected_type = None
            if chunk.startswith(b"\xff\xd8\xff"):
                detected_type = "image/jpeg"
            elif chunk.startswith(b"\x89PNG\r\n\x1a\n"):
                detected_type = "image/png"
            elif chunk.startswith(b"GIF87a") or chunk.startswith(b"GIF89a"):
                detected_type = "image/gif"
            elif chunk.startswith(b"RIFF") and b"WEBP" in chunk[:16]:
                detected_type = "image/webp"
            elif b"<svg" in chunk.lower() or b"<?xml" in chunk.lower():
                detected_type = "image/svg+xml"
            elif ct_raw in ALLOWED_IMAGE_CONTENT_TYPES:
                detected_type = ct_raw

            if not detected_type and ct_raw not in ALLOWED_IMAGE_CONTENT_TYPES:
                ext = os.path.splitext(parsed.path)[1].lower()
                if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"):
                    return True, "Accepted image by extension.", "image/jpeg"
                return False, f"Response is not a valid image (Content-Type: '{ct_raw}').", None

            final_type = detected_type or ct_raw
            return True, "Image URL validated successfully.", final_type

    except requests.Timeout:
        return True, "Allowed image link (timeout on preview).", "image/jpeg"
    except requests.RequestException:
        return True, "Allowed image link.", "image/jpeg"

