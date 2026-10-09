import logging
import asyncio
from typing import Dict, Any, List

from storage.providers.vcdn import VcdnStorageProvider
from storage.providers.media_cm import MediaCmStorageProvider
from storage.providers.anonmp4 import AnonMp4StorageProvider
from storage.providers.vevocloud import VevocloudStorageProvider

logger = logging.getLogger(__name__)


class StorageHealthService:
    """
    Diagnostic service for checking live API connectivity and credential status
    across all 4 replication providers without exposing keys or tokens.
    """

    @staticmethod
    async def check_all_providers() -> List[Dict[str, Any]]:
        providers = [
            VcdnStorageProvider(),
            MediaCmStorageProvider(),
            AnonMp4StorageProvider(),
            VevocloudStorageProvider(),
        ]

        tasks = [p.health_check() for p in providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        health_list = []
        for p, res in zip(providers, results):
            if isinstance(res, Exception):
                health_list.append({
                    "provider": p.name,
                    "status": "ERROR",
                    "healthy": False,
                    "message": str(res),
                })
            else:
                health_list.append(res)

        return health_list
