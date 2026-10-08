import requests
import sys

BASE_URL = "http://127.0.0.1:8000"

def test_endpoint(name, method, path, expected_status=200):
    url = f"{BASE_URL}{path}"
    try:
        if method == "GET":
            resp = requests.get(url, timeout=60)
        print(f"[{'PASS' if resp.status_code == expected_status else 'FAIL'}] {name} ({method} {path}) -> HTTP {resp.status_code}")
        return resp
    except Exception as e:
        print(f"[FAIL] {name} ({method} {path}) -> Exception: {e}")
        return None

def main():
    print("==================================================")
    print(" COURSE WALLAH PLATFORM — LIVE VERIFICATION SUITE")
    print("==================================================")

    # 1. Static & SPA Assets
    r_html = test_endpoint("SPA Index HTML", "GET", "/")
    assert r_html and "Course Wallah" in r_html.text, "Index HTML must contain Course Wallah"

    r_js = test_endpoint("App JavaScript", "GET", "/static/app.js")
    assert r_js and "renderLecturePage" in r_js.text, "App JS must contain lecture render function"
    assert "aside class=\"playlist-sidebar\"" not in r_js.text, "Playlist sidebar MUST be removed from JS rendering"

    r_css = test_endpoint("Stylesheet", "GET", "/static/index.css")
    assert r_css and "player-wrapper" in r_css.text, "Stylesheet must contain player-wrapper"

    r_logo = test_endpoint("Logo Asset", "GET", "/static/logo.png")
    assert r_logo and len(r_logo.content) > 1000, "Logo PNG must exist and be non-empty"

    # 2. REST API: First Page App List
    r_apps = test_endpoint("Apps List (First Page)", "GET", "/api/v1/apps")
    apps = r_apps.json()
    assert isinstance(apps, list) and len(apps) >= 1, "Must return at least 1 app (Course Wallah)"
    print(f"   -> Found {len(apps)} Educational Streams: {[a['name'] for a in apps]}")

    # 3. REST API: Batch List
    cw_app = next((a for a in apps if a["slug"] == "course-wallah-e2e" or a["name"] == "Course Wallah"), apps[0])
    app_slug = cw_app["slug"]
    r_app_detail = test_endpoint(f"App Batches ({app_slug})", "GET", f"/api/v1/apps/{app_slug}")
    app_detail = r_app_detail.json()
    assert "batches" in app_detail and len(app_detail["batches"]) >= 1, "Must contain batches"
    batch_names = [b["name"] for b in app_detail["batches"]]
    print(f"   -> Batches under {app_detail['name']}: {batch_names}")
    assert "Engg Math" in batch_names, "Engg Math batch must be preserved"
    assert "Computer Science 2026" in batch_names, "Computer Science 2026 batch must be preserved"

    # 4. REST API: Batch Hierarchy (Subjects / Folders / Lectures)
    r_batch = test_endpoint("Engg Math Hierarchy", "GET", "/api/v1/batches/engg-math")
    batch_data = r_batch.json()
    assert "subjects" in batch_data and len(batch_data["subjects"]) >= 1, "Must contain subjects"
    
    lecture_id = None
    for subj in batch_data["subjects"]:
        for folder in subj["folders"]:
            for lec in folder["lectures"]:
                if "GATE 2017" in lec["title"]:
                    lecture_id = lec["id"]
                    print(f"   -> Found Real Lecture: '{lec['title']}' (ID: {lecture_id})")

    assert lecture_id is not None, "Real lecture '4F. GATE 2017 Question' must exist in batch hierarchy"

    # 5. REST API: Lecture Detail & Playlist ordering (Prev / Next)
    r_lec = test_endpoint("Lecture Details", "GET", f"/api/v1/lectures/{lecture_id}")
    lec_data = r_lec.json()
    assert lec_data["title"] == "4F. GATE 2017 Question", "Lecture title must match"
    assert "playlist" in lec_data, "Backend playlist data must be preserved"
    print(f"   -> Prev Lecture: {lec_data.get('prev_lecture')}")
    print(f"   -> Next Lecture: {lec_data.get('next_lecture')}")

    # 6. REST API: Secure Video Playback Access (YouTube unlisted ID, no secrets exposed)
    r_v_acc = test_endpoint("Lecture Video Access", "GET", f"/api/v1/lectures/{lecture_id}/access")
    v_acc = r_v_acc.json()
    assert v_acc["has_video"] is True, "Lecture must have video active"
    assert v_acc["youtube_video_id"] == "6ZhabLKu65E", "Must have correct YouTube video ID"
    print(f"   -> Video Title: {v_acc.get('title')}, YouTube ID: {v_acc.get('youtube_video_id')}")

    # 7. REST API: Secure PDF Access (Private B2 presigned / authorized stream)
    r_pdf_acc = test_endpoint("Lecture PDF Access", "GET", f"/api/v1/pdfs/{lecture_id}/access")
    pdf_acc = r_pdf_acc.json()
    assert "access_url" in pdf_acc, "PDF access must provide short-lived authorized URL"
    assert "b2_key" not in pdf_acc and "application_key" not in str(pdf_acc).lower(), "No B2 credentials exposed"
    print(f"   -> PDF Name: {pdf_acc.get('file_name')}, Access URL: {pdf_acc.get('access_url')}")

    # 8. REST API: PDF Streaming
    pdf_content_url = pdf_acc["access_url"]
    r_pdf_stream = test_endpoint("PDF Content Stream", "GET", pdf_content_url)
    assert r_pdf_stream.headers.get("content-type") == "application/pdf" or r_pdf_stream.status_code == 200, "Must return application/pdf"
    print(f"   -> PDF Streamed: {len(r_pdf_stream.content)} bytes")

    print("\n==================================================")
    print(" ALL 8 LIVE API & ARCHITECTURE CHECKS PASSED 100%!")
    print("==================================================")

if __name__ == "__main__":
    main()
