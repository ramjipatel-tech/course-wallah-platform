# 🎓 Course Wallah Content Platform

An automated, end-to-end education content management platform:
- **Telegram Bot Ingestion**: Interactive batch creation & resume wizard with single-message live UI
- **Content Processing Engine**: Download, format conversion, thumbnail extraction, large video splitting
- **Watermark Engine**: Professional animated continuous moving watermarks (2D dynamic drift trajectory)
- **YouTube Video Publishing**: Direct resumable chunked upload with unlisted privacy for Course Wallah custom learning player
- **Backblaze B2 Private Storage**: Private S3 storage with 15-minute temporary presigned URLs & in-memory stream caching
- **PostgreSQL / SQLite Database**: Relational source of truth (`Apps -> Batches -> Subjects -> Folders -> Lectures -> Playlists`)
- **FastAPI REST Backend**: Versioned `/api/v1/` endpoints with JWT authorization and rate limiting
- **3D Student Web Application**: Interactive 3D tilt cards, custom learning player, fast progressive continuous scroll PDF viewer
- **Railway & Vercel Deployment**: Modular multi-service architecture (FastAPI/Bot on Railway, Dynamic Frontend on Vercel)

---

## 🏗️ Architecture Overview

```
                      +-------------------+
                      |   TELEGRAM BOT    |  (Interactive Batch Ingestion & Live UI)
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   TXT INDEXER     |  (Academic, Structured, Bracket normalizer)
                      +---------+---------+
                                |
                                v
                 +--------------+--------------+
                 |                             |
                 v                             v
       +-------------------+         +-------------------+
       |  VIDEO PIPELINE   |         |   PDF PIPELINE    |
       |  - Stream Download|         |  - PDF Validation |
       |  - Moving Wmark   |         |  - Page Watermark |
       |  - Thumbnail Gen  |         |  - B2 S3 Upload   |
       |  - YouTube Upload |         +---------+---------+
       |  - Temp Cleanup   |                   |
       +---------+---------+                   |
                 |                             |
                 +--------------+--------------+
                                |
                                v
                      +-------------------+
                      |  DATABASE ENGINE  |  (PostgreSQL / SQLite Relational Models)
                      +---------+---------+
                                |
                                v
                 +--------------+--------------+
                 |                             |
                 v                             v
       +-------------------+         +-------------------+
       |  SECURE REST API  |         | INTERNAL PLAYLIST |
       |  (/api/v1/)       |         | Auto-Ordering     |
       +---------+---------+         +-------------------+
                 |
                 v
       +-------------------+
       |  STUDENT WEBSITE  |  (3D Portal, Custom Player & Fast PDF.js Viewer)
       +-------------------+
```

---

## 🚀 Key Features & Implementations

### 1. 3D Homepage & Stream/Batch Cards
- **3D Interactive Tilt**: Mouse-reactive 3D card tilt with depth perspective and glassmorphism.
- **Batch Media Counters**: Displays real counts for 🎬 Videos, 📄 PDFs, and 📁 Units on each batch card.
- **Stream-First Hierarchy**: `Home` -> `Apps` -> `Batch` -> `Subject` -> `Folder/Unit` -> `Lecture`.

### 2. Clean Lecture Page (Video & Notes Tabs)
- **Focused Header**: Clean concise title and tags without redundant metadata clutter.
- **Seamless Tabs**: Quick switch between `▶ Video Lecture` and `📄 Study Notes (PDF)`.
- **Playlist Navigation**: Powered by backend playlist ordering (`← Previous Lecture` / `Next Lecture →`).

### 3. Custom Course Wallah Video Player
- **Branding**: Official Course Wallah logo badge overlay ([logo.png](file:///b:/Projects/downloader%20bot/course_wallah_platform/web/public/logo.png)).
- **Platform Chrome Hidden**: Standard YouTube chrome, watch links, recommendations, and video IDs are concealed.
- **Controls Bar**:
  - Play / Pause (Space / 'K')
  - Rewind `-10s` (← / 'J') and Forward `+10s` (→ / 'L')
  - Scrubber with buffer indicator and hover timestamp preview
  - Volume slider with mute toggle ('M')
  - Playback Speed (`0.5x`, `0.75x`, `1.0x`, `1.25x`, `1.5x`, `1.75x`, `2.0x`)
  - Quality Selector: `4K (2160p)`, `2K (1440p)`, `1080p FHD`, `720p HD`, `480p SD`, `360p`, `Auto`
  - Fullscreen toggle ('F')

### 4. Fast Progressive & Continuous Scroll PDF.js Canvas Viewer
- **Instant Progressive Loading**: Renders Page 1 and 2 in <300ms while loading remaining pages on-demand using `IntersectionObserver`.
- **Continuous Scroll Mode**: Smooth scrolling through all pages without tedious single-page clicking.
- **In-Memory Cache**: Backend PDF stream caching ensures subsequent page requests load in <50ms.
- **Security & Anti-Copy**:
  - Right-click contextmenu disabled across the application.
  - DevTools shortcuts (`F12`, `Ctrl+Shift+I`, `Ctrl+Shift+J`, `Ctrl+U`, `Ctrl+S`, `Ctrl+P`) blocked.
  - Continuous subtle `"COURSE WALLAH — PERSONAL STUDY MATERIAL"` rotated watermark overlay.
  - Pure canvas rendering (no raw iframe or direct download button).

---

## 🚢 Deployment Guide (Railway & Vercel)

### Deploying Backend & Bot on Railway:
1. Connect repository to [Railway](https://railway.app/).
2. Set Environment Variables:
   - `DATABASE_URL`: PostgreSQL connection string (or persistent SQLite).
   - `BOT_TOKEN`: Telegram bot token.
   - `API_ID`, `API_HASH`: Telegram credentials.
   - `B2_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET`: Backblaze B2 credentials.
   - `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`: YouTube OAuth credentials.
3. Railway automatically detects `railway.json` / `nixpacks.toml` and starts the FastAPI server and bot worker.

### Deploying Dynamic Frontend on Vercel:
1. Connect repository to [Vercel](https://vercel.com/).
2. Set Environment Variable:
   - `API_URL`: Your Railway deployment URL (e.g. `https://course-wallah-production.up.railway.app`).
3. Vercel automatically uses `vercel.json` and `package.json` to deploy the dynamic SPA and proxy API requests.

---

## 🧪 Testing & Verification

Run the automated test suite:
```bash
python -m unittest scripts/test_platform.py
```

Run live API verification against a running server:
```bash
python scripts/verify_live_api.py
```
