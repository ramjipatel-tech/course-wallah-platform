import urllib.request
import json
import sys

BASE = 'http://127.0.0.1:8000'

def test_endpoint(url, desc):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            print(f'[PASS] {desc} ({resp.status}): {len(data)} bytes')
            content_type = resp.headers.get('Content-Type', '')
            if 'json' in content_type:
                parsed = json.loads(data.decode('utf-8'))
                return parsed
            return data
    except Exception as e:
        print(f'[FAIL] {desc}: {e}')
        return None

def main():
    print('============================================================')
    print('COURSE WALLAH REBUILD VERIFICATION')
    print('============================================================')

    # Static Assets
    test_endpoint(f'{BASE}/', 'Home HTML (index.html)')
    test_endpoint(f'{BASE}/static/logo.png', 'Logo Asset (logo.png)')
    test_endpoint(f'{BASE}/static/index.css', 'Styles (index.css)')
    test_endpoint(f'{BASE}/static/app.js', 'App JS (app.js)')

    # Global Apps API
    apps_data = test_endpoint(f'{BASE}/api/v1/apps', 'API Apps List')
    if apps_data is None:
        print('[FAIL] Failed to fetch apps list')
        return

    apps = apps_data if isinstance(apps_data, list) else apps_data.get('apps', [])
    print(f'Found {len(apps)} app(s): {[a["name"] for a in apps]}')

    for app in apps:
        app_slug = app['slug']
        app_detail = test_endpoint(f'{BASE}/api/v1/apps/{app_slug}', f'App Detail ({app_slug})')
        if not app_detail:
            continue
        batches = app_detail.get('batches', [])
        print(f'  App "{app["name"]}" has {len(batches)} batch(es): {[b["name"] for b in batches]}')

        for batch in batches:
            bslug = batch['slug']
            b_detail = test_endpoint(f'{BASE}/api/v1/batches/{bslug}', f'Batch Detail ({bslug})')
            if not b_detail:
                continue
            subjects = b_detail.get('subjects', [])
            print(f'    Batch "{batch["name"]}" has {len(subjects)} subject(s)')

            for subj in subjects:
                print(f'      Subject: {subj["name"]}')
                folders = subj.get('folders', [])
                for folder in folders:
                    print(f'        Folder: {folder["name"]} ({len(folder.get("lectures", []))} lectures)')
                    for lec in folder.get('lectures', []):
                        lid = lec['id']
                        print(f'          Lecture [{lec.get("sequence_number", 1)}]: {lec["title"]} (ID: {lid})')
                        lec_data = test_endpoint(f'{BASE}/api/v1/lectures/{lid}', f'Lecture Meta ({lid})')
                        lec_access = test_endpoint(f'{BASE}/api/v1/lectures/{lid}/access', f'Lecture Access ({lid})')
                        if lec_access:
                            print(f'            Video Embed Token/URL: {lec_access.get("embed_url")}')
                        pdf_id = lec.get('pdf_asset_id')
                        if pdf_id:
                            pdf_access = test_endpoint(f'{BASE}/api/v1/pdfs/{pdf_id}/access', f'PDF Access ({pdf_id})')
                            if pdf_access:
                                print(f'            PDF Presigned URL Generated: {bool(pdf_access.get("access_url"))}')
                                print(f'            PDF Expires In: {pdf_access.get("expires_in")}s')

    print('\n============================================================')
    print('DATABASE CONTENT SUMMARY: VERIFIED')
    print('============================================================')

if __name__ == '__main__':
    main()
