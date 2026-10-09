import os
import sys
import json
import sqlite3
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse

BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "web" / "public"
DB_PATH = BASE_DIR / "data" / "course_wallah.db"
API_REMOTE = "https://course-wallah-platform-production.up.railway.app"
PORT = 3000

def get_local_lecture_data(lecture_id: str, is_access: bool = False):
    if not DB_PATH.exists():
        return None
    try:
        con = sqlite3.connect(str(DB_PATH))
        con.row_factory = sqlite3.Row
        cur = con.cursor()

        lec = cur.execute("SELECT * FROM lectures WHERE id = ? OR slug = ?", (lecture_id, lecture_id)).fetchone()
        if not lec:
            con.close()
            return None
        lec = dict(lec)

        vid = cur.execute("SELECT * FROM videos WHERE lecture_id = ?", (lec["id"],)).fetchone()
        vid = dict(vid) if vid else None

        storages = []
        if vid:
            rows = cur.execute("SELECT * FROM video_storages WHERE video_id = ?", (vid["id"],)).fetchall()
            storages = [dict(r) for r in rows]

        if not is_access:
            siblings_rows = cur.execute(
                "SELECT id, title, lecture_index, has_video, has_pdf FROM lectures WHERE subject_id = ? ORDER BY lecture_index",
                (lec["subject_id"],)
            ).fetchall()
            siblings = [dict(r) for r in siblings_rows]

            prev_lec = None
            next_lec = None
            for i, s in enumerate(siblings):
                if s["id"] == lec["id"]:
                    if i > 0:
                        prev_lec = {"id": siblings[i-1]["id"], "title": siblings[i-1]["title"], "index": siblings[i-1]["lecture_index"]}
                    if i + 1 < len(siblings):
                        next_lec = {"id": siblings[i+1]["id"], "title": siblings[i+1]["title"], "index": siblings[i+1]["lecture_index"]}
                    break

            con.close()
            return {
                "id": lec["id"],
                "title": lec["title"],
                "index": lec["lecture_index"],
                "duration_seconds": lec.get("duration_seconds") or 0,
                "has_video": bool(lec.get("has_video")),
                "has_pdf": bool(lec.get("has_pdf")),
                "folder_name": "General",
                "subject_name": "Subject",
                "batch_name": "Lakshya JEE 2025",
                "batch_slug": "lakshya-jee-2025",
                "app_name": "Physics Wallah",
                "app_slug": "physics-wallah",
                "prev_lecture": prev_lec,
                "next_lecture": next_lec,
                "playlist": [
                    {
                        "id": s["id"],
                        "title": s["title"],
                        "index": s["lecture_index"],
                        "has_video": bool(s["has_video"]),
                        "has_pdf": bool(s["has_pdf"]),
                        "is_active": s["id"] == lec["id"]
                    }
                    for s in siblings
                ]
            }

        con.close()
        has_storage_video = False
        embed_url = None
        storage_provider = None
        if storages:
            for st in storages:
                if st.get("status") == "READY" and st.get("embed_url"):
                    embed_url = st.get("embed_url")
                    storage_provider = st.get("provider")
                    has_storage_video = True
                    break

        is_yt_valid = bool(
            vid and vid.get("youtube_video_id") and 
            not vid.get("youtube_video_id", "").startswith(("cw_temp_", "yt_id_", "EXISTING_YT", "YT_PERSIST", "dQw4w9WgXcQ"))
        )
        has_video = is_yt_valid or bool(lec.get("source_url")) or has_storage_video

        stream_url = None
        if lec.get("source_url") and any(lec["source_url"].lower().endswith(ext) or ext in lec["source_url"].lower() for ext in (".m3u8", ".mp4", "transcoded-videos", "liveclasses", "stream")):
            stream_url = lec["source_url"]

        return {
            "has_video": has_video,
            "has_pdf": bool(lec.get("has_pdf")),
            "title": lec["title"],
            "duration": vid.get("duration", 0) if vid else 0,
            "youtube_video_id": vid["youtube_video_id"] if is_yt_valid else None,
            "stream_url": stream_url,
            "embed_url": embed_url,
            "storage_provider": storage_provider,
            "pdf_download_url": lec.get("source_pdf_url"),
            "player_config": {
                "autoplay": False,
                "controls": True,
                "branding": "Course Wallah",
                "quality": (vid.get("resolution") if vid else None) or "1080p"
            }
        }
    except Exception as e:
        print(f"[DevServer] Local DB lookup error: {e}")
        return None

class DevProxyHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urllib.parse.urlsplit(path)
        clean_path = urllib.parse.unquote(parsed.path)
        if clean_path.startswith("/static/"):
            rel_path = clean_path[len("/static/"):].lstrip("/")
            return str(PUBLIC_DIR / rel_path)
        direct_target = PUBLIC_DIR / clean_path.lstrip("/")
        if clean_path != "/" and direct_target.is_file():
            return str(direct_target)
        return str(PUBLIC_DIR / "index.html")

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        clean_path = urllib.parse.unquote(parsed.path)
        if clean_path.startswith("/api/") or clean_path == "/api":
            if self._try_serve_local_api(clean_path):
                return
            self._proxy_api("GET")
            return

        if clean_path.startswith("/static/"):
            return super().do_GET()

        direct_target = PUBLIC_DIR / clean_path.lstrip("/")
        if clean_path != "/" and direct_target.is_file():
            return super().do_GET()

        # SPA root fallback for client-side routing
        index_file = PUBLIC_DIR / "index.html"
        if index_file.exists():
            with open(index_file, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        super().do_GET()

    def _try_serve_local_api(self, clean_path: str) -> bool:
        # Check /api/lectures/<id>/access or /api/lectures/<id>
        parts = [p for p in clean_path.strip("/").split("/") if p]
        if len(parts) >= 2 and parts[0] in ("api", "v1") and (parts[1] == "lectures" or (len(parts) >= 3 and parts[2] == "lectures")):
            lec_idx = parts.index("lectures")
            if len(parts) > lec_idx + 1:
                lec_id = parts[lec_idx + 1]
                is_access = len(parts) > lec_idx + 2 and parts[lec_idx + 2] == "access"
                data = get_local_lecture_data(lec_id, is_access=is_access)
                if data:
                    body = json.dumps(data).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(body)
                    return True
        return False

    def _proxy_api(self, method: str):
        remote_url = f"{API_REMOTE}{self.path}"
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None
            headers = {k: v for k, v in self.headers.items() if k.lower() != 'host'}
            req = urllib.request.Request(remote_url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req) as response:
                self.send_response(response.status)
                for k, v in response.headers.items():
                    if k.lower() not in ['transfer-encoding', 'content-encoding', 'content-length']:
                        self.send_header(k, v)
                data = response.read()
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(f"Proxy Error: {e}".encode())

    def do_POST(self):
        self._proxy_api("POST")

    def do_PUT(self):
        self._proxy_api("PUT")

    def do_DELETE(self):
        self._proxy_api("DELETE")

    def do_OPTIONS(self):
        self._proxy_api("OPTIONS")

def run():
    server = HTTPServer(("127.0.0.1", PORT), DevProxyHandler)
    print(f"Local Course Wallah Dev Server running at http://127.0.0.1:{PORT}")
    print(f"Proxying APIs to {API_REMOTE}")
    server.serve_forever()

if __name__ == "__main__":
    run()
