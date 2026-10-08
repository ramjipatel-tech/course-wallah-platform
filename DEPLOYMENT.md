# 🚀 Course Wallah — Complete Online Deployment Guide

Ye guide aapko **Course Wallah Platform (Telegram Bot + Backend API + Worker + Website)** ko **Railway** aur **Vercel** par 100% live karne ka step-by-step process batati hai.

---

## 🏗️ Architecture Overview

```
┌───────────────────────────────────────────────────────────┐
│                    VERCEL (Frontend)                      │
│   • Next.js 14 Web App (Students Portal, Batches, Videos) │
│   • Auto-proxies /api/* calls to Railway Backend          │
└─────────────────────────────┬─────────────────────────────┘
                              │ HTTPS REST API
                              ▼
┌───────────────────────────────────────────────────────────┐
│              RAILWAY (Backend + Bot + Worker)             │
│   • FastAPI Web Server (REST API + Admin /ragni/admin)    │
│   • Telegram Bot (24/7 Pyrogram Bot)                      │
│   • Background Ingestion Worker (FFmpeg, Watermark, DL)   │
│   • Multi-Channel YouTube Auto-Failover Engine            │
│   • PostgreSQL Database                                   │
└───────────────────────────────────────────────────────────┘
```

---

## 🟣 PART 1: Railway par Deploy Karna (Backend + Bot + Worker + Database)

Railway par aapka **FastAPI Web Server, Telegram Bot, Background Queue Worker, aur Database** ek saath seamlessly 24/7 chalenge.

### Step 1: GitHub Repository Push
Aapka code GitHub repository me push hona chahiye.

### Step 2: Railway Project Create Karein
1. [Railway.app](https://railway.app) par login karein.
2. **"New Project"** par click karein -> **"Deploy from GitHub repo"** select karein.
3. Apni repository `course_wallah_platform` select karein.

### Step 3: PostgreSQL Database Add Karein (Recommended)
1. Railway Dashboard me **"+ New"** par click karein -> **"Database"** -> **"Add PostgreSQL"**.
2. Railway automatically `DATABASE_URL` generate kar dega jo aapke app ke saath connect ho jayegi.

### Step 4: Environment Variables (Variables Tab me set karein)
Railway ke **Variables** tab me jaakar ye keys add karein:

| Variable Name | Value / Description | Example |
| :--- | :--- | :--- |
| `API_ID` | Telegram API ID (my.telegram.org se) | `12345678` |
| `API_HASH` | Telegram API Hash | `0123456789abcdef...` |
| `BOT_TOKEN` | Telegram Bot Token (@BotFather se) | `7123456789:AA...` |
| `BOT_NAME` | Bot Display Name | `Course Wallah` |
| `OWNER_ID` | Aapki Telegram User ID | `1791439219` |
| `ADMINS` | Admin IDs (comma separated) | `1791439219` |
| `SECRET_KEY` | Random 64-character secret key | `cw_super_secret_railway_2026` |
| `ADMIN_SECRET_PATH` | Admin Dashboard secret route | `ragni` |
| `ADMIN_USERNAME` | Admin panel username | `admin` |
| `ADMIN_PASSWORD` | Strong password for Admin Panel | `CourseWallah@2026#Secure` |
| `B2_ENDPOINT` | Backblaze B2 S3 endpoint | `https://s3.us-east-005.backblazeb2.com` |
| `B2_REGION` | B2 Region | `us-east-005` |
| `B2_BUCKET` | B2 Bucket Name | `course-wallah-pdfs` |
| `B2_KEY_ID` | B2 Application Key ID | `005xxxxxxxxxxxx00001` |
| `B2_APPLICATION_KEY` | B2 Secret Application Key | `K005xxxxxxxxxxxxxxxx` |
| `WATERMARK_TEXT` | Watermark text for videos | `COURSE WALLAH` |
| `SECURITY_TEST_MODE` | Set `false` for production | `false` |

*(Note: YouTube credentials aap seedhe Telegram bot me `/yt_add` command se add kar sakte hain!)*

### Step 5: Start Command & Deploy
* Railway `nixpacks.toml` aur `railway.json` ko automatically detect kar lega aur `python start.py` execute karega.
* Railway aapko ek public URL dega jaise: `https://course-wallah-production.up.railway.app`.
* **Health Check endpoint**: `https://your-app.up.railway.app/health` par `{"status": "healthy"}` dikhega.
* **Admin Portal**: `https://your-app.up.railway.app/ragni/admin` par open hoga.

---

## ▲ PART 2: Vercel par Frontend Deploy Karna (Next.js 14 Website)

### Step 1: Vercel Project Import
1. [Vercel.com](https://vercel.com) par login karein.
2. **"Add New..."** -> **"Project"** par click karein.
3. Apni GitHub repository `course_wallah_platform` choose karein.

### Step 2: Build & Project Settings
* **Framework Preset**: `Next.js` (automatically detected)
* **Root Directory**: `./` (default)
* **Build Command**: `npm run build` (default)
* **Output Directory**: `.next` (default)

### Step 3: Environment Variables
Vercel dashboard me **Environment Variables** add karein:

| Variable Name | Value |
| :--- | :--- |
| `NEXT_PUBLIC_API_URL` | Aapka Railway backend URL (e.g. `https://course-wallah-production.up.railway.app`) |
| `NEXT_PUBLIC_SITE_NAME` | `Course Wallah` |

### Step 4: Deploy
* **"Deploy"** button dabayein.
* 1 se 2 minute me aapki website Vercel par live ho jayegi (e.g. `https://course-wallah.vercel.app`).

---

## 🎬 PART 3: Multi-Channel YouTube Configuration (Bot se)

Deploy hote hi aapko kisi `.env` file ko baar-baar edit karne ki zaroorat nahi hai:
1. Telegram me apne Bot ko open karein.
2. `/start` ya `/yt_list` command bhejein.
3. Naya channel add karne ke liye:
   ```text
   /yt_add Main Channel | 12345.apps.googleusercontent.com | GOCSPX-secret | 1//04refreshtoken
   ```
4. Ya channel ka Google secret `.json` file seedhe bot me upload karein.
5. Bot token test karke channel name aur subscribers auto-detect kar lega.
6. Daily quota (20 videos) poora hone par bot automatically agle channel par switch karega.

---

## 🔒 Security & Admin Panel Check

* **Admin Portal URL**: `https://your-backend.up.railway.app/ragni/admin`
* **Features**:
  * ✅ Batch Upload & Ingestion Monitor
  * ✅ Live Thumbnail & Watermark Update
  * ✅ Student Problem & Support Ticket Resolution
  * ✅ Student Batch Access Grant / Revoke
  * ✅ Multi-Channel Quota Inspector
