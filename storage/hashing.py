import os
import hashlib
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: str, chunk_size: int = 65536) -> str:
    """
    Computes standard SHA-256 hexadecimal digest for a local file with 64KB chunking
    to avoid excessive RAM usage on large video files.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found for SHA-256 calculation: {file_path}")

    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    digest = hasher.hexdigest()
    return digest


async def compute_file_sha256_async(file_path: str, chunk_size: int = 65536) -> str:
    """
    Asynchronously runs SHA-256 computation in the default executor thread
    to avoid blocking the asyncio event loop during large video reads.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, compute_file_sha256, file_path, chunk_size)


compute_file_sha256_sync = compute_file_sha256
