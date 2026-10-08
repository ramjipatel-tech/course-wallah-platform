import sys
import asyncio
from pathlib import Path

# Add platform directory to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from bot.bot_app import start_bot

if __name__ == "__main__":
    asyncio.run(start_bot())
