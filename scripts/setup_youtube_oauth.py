import os
import sys
import re
import socket
import threading
import urllib.parse
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

local_env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=local_env_path, override=True)

from config.settings import YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def generate_auth_urls() -> Dict[str, str]:
    """Generates the Google OAuth 2.0 consent screen URLs for both standard redirect URIs."""
    urls = {}
    for r_uri, name in [("http://localhost:8080/", "port_8080"), ("http://localhost", "standard_localhost")]:
        params = {
            "client_id": YOUTUBE_CLIENT_ID,
            "redirect_uri": r_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent"
        }
        urls[name] = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return urls

def exchange_code_for_refresh_token(code: str, redirect_uri: str = "http://localhost:8080/") -> Optional[str]:
    """Exchanges authorization code for refresh token and updates .env and DB."""
    # Strip full URL if user pasted the entire address bar URL
    if "code=" in code:
        parsed = urllib.parse.urlparse(code)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            code = params["code"][0]
        else:
            match = re.search(r'code=([^&]+)', code)
            if match:
                code = urllib.parse.unquote(match.group(1))

    # Also detect redirect_uri from input if pasted
    if code.startswith("http://localhost") and not ("code=" in code):
        pass

    token_url = "https://oauth2.googleapis.com/token"
    
    # Try with both redirect_uri options
    candidates = [redirect_uri, "http://localhost:8080/", "http://localhost", "http://127.0.0.1:8080/"]
    # De-duplicate while preserving order
    seen = set()
    unique_candidates = [x for x in candidates if not (x in seen or seen.add(x))]

    last_error = ""
    for cand_uri in unique_candidates:
        payload = {
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "code": code.strip(),
            "grant_type": "authorization_code",
            "redirect_uri": cand_uri
        }
        try:
            resp = requests.post(token_url, data=payload, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                refresh_token = data.get("refresh_token")
                access_token = data.get("access_token")
                
                if not refresh_token:
                    print("[WARNING] Google returned access token without refresh token (did you select offline?).", flush=True)
                    return None
                
                # Update .env
                env_text = local_env_path.read_text(encoding="utf-8")
                if "YOUTUBE_REFRESH_TOKEN=" in env_text:
                    env_text = re.sub(r'YOUTUBE_REFRESH_TOKEN=.*', f'YOUTUBE_REFRESH_TOKEN="{refresh_token}"', env_text)
                else:
                    env_text += f'\nYOUTUBE_REFRESH_TOKEN="{refresh_token}"\n'
                local_env_path.write_text(env_text, encoding="utf-8")
                os.environ["YOUTUBE_REFRESH_TOKEN"] = refresh_token
                print("[SUCCESS] Refresh token captured and saved to .env", flush=True)

                # Sync to Database
                import asyncio
                from db.connection import get_db_session, init_db
                from db.repository import ContentRepository
                from db.models import YouTubeAccountStatus

                async def sync_db():
                    await init_db()
                    async with get_db_session() as s:
                        r = ContentRepository(s)
                        acc = await r.create_or_update_youtube_account(
                            name="Primary YouTube (.env)",
                            client_id=YOUTUBE_CLIENT_ID,
                            client_secret=YOUTUBE_CLIENT_SECRET,
                            refresh_token=refresh_token,
                            status=YouTubeAccountStatus.ACTIVE.value,
                            priority=1
                        )
                        print(f"[SUCCESS] Updated database account '{acc.name}' (ID: {acc.id}) -> ACTIVE", flush=True)

                asyncio.run(sync_db())
                return refresh_token
            else:
                last_error = f"HTTP {resp.status_code} - {resp.text}"
        except Exception as e:
            last_error = str(e)

    print(f"[ERROR] Token exchange failed with all redirect URIs: {last_error}", flush=True)
    return None

if __name__ == "__main__":
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--code" and len(sys.argv) > 2:
            code_input = sys.argv[2]
            r = exchange_code_for_refresh_token(code_input)
            if r:
                print("OAUTH SETUP COMPLETE! Ready for uploads.")
            else:
                print("Failed to exchange code.")
        elif arg.startswith("http") or arg.startswith("4/"):
            r = exchange_code_for_refresh_token(arg)
            if r:
                print("OAUTH SETUP COMPLETE! Ready for uploads.")
            else:
                print("Failed to exchange code.")
    else:
        urls = generate_auth_urls()
        print("\n=======================================================")
        print("GOOGLE YOUTUBE OAUTH AUTHORIZATION LINKS:")
        print("=======================================================")
        print("\n1. CLICK THIS LINK IN YOUR BROWSER:")
        print(urls["port_8080"])
        print("\n2. IF YOUR REDIRECT URI IS http://localhost (NO PORT), USE THIS:")
        print(urls["standard_localhost"])
        print("=======================================================\n")
