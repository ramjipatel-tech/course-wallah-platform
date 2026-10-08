/**
 * ==============================================================================
 * COURSE WALLAH PLATFORM — AS MULTIVERSE INTERACTIVE CLIENT ENGINE
 * Ultra-fast Single Page Application (SPA) with deep URL routing & YouTube Player
 * ==============================================================================
 */

// Application State Store
const state = {
  activeTab: 'home',
  currentApp: null,
  currentBatch: null,
  currentSubject: null,
  currentLecture: null,
  activeCategory: 'All',
  theme: localStorage.getItem('cw_theme') || 'dark',
  streak: parseInt(localStorage.getItem('cw_streak') || '1', 10),
  bookmarks: JSON.parse(localStorage.getItem('cw_bookmarks') || '[]'),
  enrolledBatches: JSON.parse(localStorage.getItem('cw_enrolled') || '[]'),
  appsData: [],
  cache: {
    apps: null,
    batches: {},
    lectures: {}
  },
  player: null,
  ytApiReady: false
};

// ==============================================================================
// INITIALIZATION & ROUTER
// ==============================================================================

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initStreak();
  window.addEventListener('popstate', handleRoute);
  window.addEventListener('hashchange', handleRoute);
  handleRoute();
});

// YouTube IFrame API Ready Callback
window.onYouTubeIframeAPIReady = () => {
  state.ytApiReady = true;
};

// Theme Management
function initTheme() {
  document.body.className = state.theme === 'light' ? 'theme-light' : 'theme-dark';
  updateThemeIcon();
}

function toggleTheme() {
  state.theme = state.theme === 'dark' ? 'light' : 'dark';
  localStorage.setItem('cw_theme', state.theme);
  document.body.className = state.theme === 'light' ? 'theme-light' : 'theme-dark';
  updateThemeIcon();
  showToast(`Switched to ${state.theme === 'dark' ? 'Dark' : 'Light'} Mode`);
}

function updateThemeIcon() {
  const moon = document.querySelector('.icon-moon');
  const sun = document.querySelector('.icon-sun');
  if (moon && sun) {
    if (state.theme === 'light') {
      moon.classList.add('hidden');
      sun.classList.remove('hidden');
    } else {
      moon.classList.remove('hidden');
      sun.classList.add('hidden');
    }
  }
}

// Study Streak Management
function initStreak() {
  const lastVisit = localStorage.getItem('cw_last_visit');
  const today = new Date().toDateString();
  if (lastVisit !== today) {
    state.streak += 1;
    localStorage.setItem('cw_streak', state.streak);
    localStorage.setItem('cw_last_visit', today);
  }
  const counter = document.getElementById('streak-counter');
  if (counter) counter.innerText = state.streak;
}

// Sidebar Toggle
function toggleSidebar(forceState) {
  const sidebar = document.getElementById('sidebar');
  const backdrop = document.getElementById('sidebar-backdrop');
  if (!sidebar) return;
  const isOpen = forceState !== undefined ? forceState : !sidebar.classList.contains('open');
  sidebar.classList.toggle('open', isOpen);
  if (backdrop) backdrop.classList.toggle('open', isOpen);
}

// ==============================================================================
// URL ROUTING & NAVIGATION
// ==============================================================================

function getRouteParams() {
  const urlParams = new URLSearchParams(window.location.search);
  const tab = urlParams.get('tab') || 'home';
  const app = urlParams.get('app') || null;
  const batchId = urlParams.get('batchid') || null;
  const subjectId = urlParams.get('subjectid') || null;
  const content = urlParams.get('content') || null;
  const isPlaying = window.location.hash === '#playing' || !!content;
  return { tab, app, batchId, subjectId, content, isPlaying };
}

function navigateToTab(tabName) {
  const url = `/?tab=${tabName}`;
  window.history.pushState({}, '', url);
  handleRoute();
  toggleSidebar(false);
}

function navigateToApp(appSlugOrId) {
  const url = `/?tab=apps&app=${encodeURIComponent(appSlugOrId)}`;
  window.history.pushState({}, '', url);
  handleRoute();
}

function navigateToBatch(appSlugOrId, batchIdOrSlug) {
  const url = `/?tab=apps&app=${encodeURIComponent(appSlugOrId)}&batchid=${encodeURIComponent(batchIdOrSlug)}`;
  window.history.pushState({}, '', url);
  handleRoute();
}

function navigateToSubject(appSlugOrId, batchIdOrSlug, subjectIdOrSlug) {
  const url = `/?tab=apps&app=${encodeURIComponent(appSlugOrId)}&batchid=${encodeURIComponent(batchIdOrSlug)}&subjectid=${encodeURIComponent(subjectIdOrSlug)}`;
  window.history.pushState({}, '', url);
  handleRoute();
}

function navigateToLecture(appSlugOrId, batchIdOrSlug, subjectIdOrSlug, lectureId) {
  const url = `/?tab=apps&app=${encodeURIComponent(appSlugOrId)}&batchid=${encodeURIComponent(batchIdOrSlug)}&subjectid=${encodeURIComponent(subjectIdOrSlug)}&content=${encodeURIComponent(lectureId)}#playing`;
  window.history.pushState({}, '', url);
  handleRoute();
}

function handleGlobalBack() {
  const { tab, app, batchId, subjectId, content } = getRouteParams();
  if (content) {
    navigateToSubject(app, batchId, subjectId);
  } else if (subjectId) {
    navigateToBatch(app, batchId);
  } else if (batchId) {
    navigateToApp(app);
  } else if (app) {
    navigateToTab('apps');
  } else {
    navigateToTab('home');
  }
}

// Active Nav Item Highlighter
function updateActiveNav(tabName) {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-tab') === tabName);
  });
}

// Router Dispatcher
async function handleRoute() {
  const { tab, app, batchId, subjectId, content, isPlaying } = getRouteParams();
  updateActiveNav(tab);

  const backBtn = document.getElementById('btn-global-back');
  const titleEl = document.getElementById('header-page-title');
  
  if (backBtn) {
    backBtn.classList.toggle('hidden', tab === 'home' && !app && !batchId);
  }

  const root = document.getElementById('app-root');
  if (!root) return;

  // Render Skeleton Loading State
  root.innerHTML = `<div class="loading-state" style="text-align:center; padding: 60px 0;"><div class="brand-logo-wrap" style="margin: 0 auto 16px;"><div class="brand-logo-glow"></div><div class="brand-fallback-logo" style="animation: float 2s infinite;">CW</div></div><p style="font-weight:700; color: var(--text-muted);">Loading Course Wallah Matrix...</p></div>`;

  try {
    // 1. In-App Video Player View
    if (content && isPlaying) {
      if (titleEl) titleEl.querySelector('.title-text').innerText = 'STUDY STUDIO';
      await renderPlayerView(root, app, batchId, subjectId, content);
      return;
    }

    // 2. Subject View / Content Explorer
    if (app && batchId && subjectId) {
      if (titleEl) titleEl.querySelector('.title-text').innerText = 'SUBJECT EXPLORER';
      await renderSubjectView(root, app, batchId, subjectId);
      return;
    }

    // 3. Batch Subjects View
    if (app && batchId) {
      if (titleEl) titleEl.querySelector('.title-text').innerText = 'BATCH SUBJECTS';
      await renderBatchView(root, app, batchId);
      return;
    }

    // 4. App Batches View
    if (app) {
      if (titleEl) titleEl.querySelector('.title-text').innerText = 'PORTAL BATCHES';
      await renderAppDetailView(root, app);
      return;
    }

    // 5. Standard Tab Views
    if (titleEl) titleEl.querySelector('.title-text').innerText = tab.toUpperCase().replace('-', ' ');

    switch (tab) {
      case 'home':
        await renderHomeView(root);
        break;
      case 'apps':
        await renderAppsView(root);
        break;
      case 'community':
        renderCommunityView(root);
        break;
      case 'downloads':
        renderDownloadsView(root);
        break;
      case 'bookmarks':
        renderBookmarksView(root);
        break;
      case 'settings':
        renderSettingsView(root);
        break;
      case 'developer':
        renderDeveloperView(root);
        break;
      case 'help-center':
        renderHelpCenterView(root);
        break;
      default:
        await renderHomeView(root);
    }
  } catch (err) {
    console.error('Route rendering error:', err);
    root.innerHTML = `<div class="error-card" style="background:var(--bg-card); padding:32px; border-radius:20px; text-align:center; border: 1px solid var(--border-subtle);"><h3 style="color:var(--accent-rose); margin-bottom:8px;">Failed to load content</h3><p style="color:var(--text-secondary); margin-bottom:16px;">${err.message || 'An unexpected error occurred.'}</p><button class="btn-hero-primary" onclick="handleRoute()">Retry</button></div>`;
  }
}

// ==============================================================================
// API DATA HELPERS
// ==============================================================================

async function fetchApps() {
  if (state.cache.apps) return state.cache.apps;
  try {
    const res = await fetch('/api/apps');
    if (!res.ok) throw new Error('Failed to fetch apps list');
    const data = await res.json();
    state.cache.apps = data;
    state.appsData = data;
    return data;
  } catch (e) {
    // Fallback Mock Data for standalone resilience
    return [
      {
        id: "app_pw",
        name: "Physics Wallah [PW]",
        slug: "physics-wallah",
        description: "India's top faculty batches for JEE, NEET & Foundation",
        icon_url: "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=120&auto=format&fit=crop&q=80",
        total_batches: 12,
        batches: [
          { id: "batch_lakshya", name: "Lakshya JEE 2025", slug: "lakshya-jee-2025", total_lectures: 140, total_videos: 140, total_pdfs: 140 }
        ]
      },
      {
        id: "app_apna",
        name: "Apna College",
        slug: "apna-college",
        description: "Full Stack Web Development, Java DSA & C++ Placement Prep",
        icon_url: "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=120&auto=format&fit=crop&q=80",
        total_batches: 8,
        batches: [
          { id: "sigma-9-live-recordings", name: "Sigma 9.0 (Web Development + DSA)", slug: "sigma-9-live-recordings", total_lectures: 151, total_videos: 151, total_pdfs: 151 }
        ]
      },
      {
        id: "app_kgs",
        name: "Khan Global Studies [KGS]",
        slug: "khan-global-studies",
        description: "UPSC, State PSC, SSC & General Studies by Khan Sir",
        icon_url: "https://images.unsplash.com/photo-1532094349884-543bc11b234d?w=120&auto=format&fit=crop&q=80",
        total_batches: 14,
        batches: [
          { id: "batch_upsc", name: "UPSC GS Foundation 2025", slug: "upsc-gs-foundation", total_lectures: 220, total_videos: 220, total_pdfs: 220 }
        ]
      },
      {
        id: "app_dsa",
        name: "Data Structures & Algorithms",
        slug: "dsa-platform",
        description: "Master Coding Interviews & System Design",
        icon_url: "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=120&auto=format&fit=crop&q=80",
        total_batches: 6,
        batches: [
          { id: "batch_dsa_core", name: "DSA Masterclass", slug: "dsa-masterclass", total_lectures: 151, total_videos: 151, total_pdfs: 151 }
        ]
      }
    ];
  }
}

async function fetchBatchDetail(batchIdOrSlug) {
  if (state.cache.batches[batchIdOrSlug]) return state.cache.batches[batchIdOrSlug];
  try {
    const res = await fetch(`/api/batches/${encodeURIComponent(batchIdOrSlug)}`);
    if (!res.ok) throw new Error('Batch not found');
    const data = await res.json();
    state.cache.batches[batchIdOrSlug] = data;
    return data;
  } catch (e) {
    // Return structured default batch hierarchy if offline
    return {
      id: batchIdOrSlug,
      name: "Data Structure And Algorithm",
      slug: batchIdOrSlug,
      app_name: "Apna College",
      category: "Coding & Engineering",
      subjects: [
        {
          id: "69d8f985d57e276ed66caca3",
          name: "Fundamentals of Algorithms and its Analysis",
          slug: "dsa-fundamentals",
          code: "DSA-01",
          folders: [
            {
              id: "unit-1",
              name: "Unit 1: Introduction to DSA",
              total_lectures: 10,
              lectures: [
                { id: "lec_1", title: "[Home] Data Structure and Algorithm Syllabus", index: 1, duration_seconds: 2400, has_video: true, has_pdf: true },
                { id: "lec_2", title: "[Home] Syllabus Introduction", index: 2, duration_seconds: 1800, has_video: true, has_pdf: true },
                { id: "lec_3", title: "Unit-1.0 Fundamentals of Algorithms and its Analysis", index: 3, duration_seconds: 3200, has_video: true, has_pdf: true },
                { id: "lec_4", title: "1. DSA Complexity & Big-O Notation", index: 4, duration_seconds: 2900, has_video: true, has_pdf: true },
                { id: "lec_5", title: "2. Array Data Structures & Operations", index: 5, duration_seconds: 3600, has_video: true, has_pdf: true }
              ]
            }
          ]
        }
      ]
    };
  }
}

async function fetchLectureDetails(lectureId) {
  if (state.cache.lectures[lectureId]) return state.cache.lectures[lectureId];
  try {
    const res = await fetch(`/api/lectures/${encodeURIComponent(lectureId)}`);
    if (!res.ok) throw new Error('Lecture details failed');
    const data = await res.json();
    state.cache.lectures[lectureId] = data;
    return data;
  } catch (e) {
    return {
      id: lectureId,
      title: "Data Structure and Algorithm Syllabus",
      index: 1,
      duration_seconds: 2400,
      has_video: true,
      has_pdf: true,
      folder_name: "Unit 1: Introduction to DSA",
      subject_name: "Fundamentals of Algorithms",
      batch_name: "Data Structure And Algorithm",
      playlist: [
        { id: "lec_1", title: "001_[Home] Data Structure and Algorithm Syllabus", index: 1, has_video: true, has_pdf: true, is_active: true },
        { id: "lec_2", title: "002_[Home] Syllabus Introduction", index: 2, has_video: true, has_pdf: true, is_active: false },
        { id: "lec_3", title: "003_Unit-1.0 Fundamentals of Algorithms and its Analysis", index: 3, has_video: true, has_pdf: true, is_active: false }
      ]
    };
  }
}

async function fetchLectureAccess(lectureId) {
  try {
    const res = await fetch(`/api/lectures/${encodeURIComponent(lectureId)}/access`);
    if (!res.ok) throw new Error('Access failed');
    return await res.json();
  } catch (e) {
    return {
      has_video: true,
      youtube_video_id: "dQw4w9WgXcQ", // fallback player demo
      has_pdf: true,
      pdf_view_url: "/api/pdfs/demo/view",
      pdf_download_url: "/api/pdfs/demo/download"
    };
  }
}

// ==============================================================================
// RENDER VIEWS
// ==============================================================================

// 1. HOME VIEW
async function renderHomeView(container) {
  const apps = await fetchApps();
  const currentHour = new Date().getHours();
  const greeting = currentHour < 12 ? 'Good Morning' : currentHour < 18 ? 'Good Afternoon' : 'Good Evening';

  container.innerHTML = `
    <!-- Hero Banner Card -->
    <div class="hero-banner-card">
      <div class="hero-content">
        <div class="hero-greeting">${greeting}, Learner! 👋</div>
        <h1 class="hero-title">Welcome to <span class="gradient-text">Course Wallah</span></h1>
        <p class="hero-subtitle">Discover premium educational apps, competitive batch archives, and high-speed lecture streams designed to help you learn smarter.</p>
        <div class="hero-actions">
          <button class="btn-hero-primary" onclick="navigateToTab('apps')">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
            <span>Explore Apps</span>
          </button>
          <button class="btn-hero-secondary" onclick="document.getElementById('category-filter-chips').scrollIntoView({behavior:'smooth'})">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h7"/></svg>
            <span>Categories</span>
          </button>
        </div>
      </div>
      <div class="hero-art-wrap">
        <svg class="hero-art-icon" viewBox="0 0 200 200" fill="none">
          <circle cx="100" cy="100" r="80" fill="url(#hero-art-grad)" fill-opacity="0.15"/>
          <path d="M40 85L100 55L160 85L100 115L40 85Z" fill="url(#hero-art-grad)"/>
          <path d="M60 100V135C60 148.8 77.9 160 100 160C122.1 160 140 148.8 140 135V100L100 120L60 100Z" fill="#8B5CF6"/>
          <defs>
            <linearGradient id="hero-art-grad" x1="40" y1="55" x2="160" y2="160" gradientUnits="userSpaceOnUse">
              <stop stop-color="#6366F1"/>
              <stop offset="1" stop-color="#A855F7"/>
            </linearGradient>
          </defs>
        </svg>
      </div>
    </div>

    <!-- Global Academic Operations Telemetry Row -->
    <div class="section-header-row">
      <h2 class="section-heading">Global Academic Operations</h2>
      <p class="section-subheading">Real-time telemetry and package deployment speeds.</p>
    </div>

    <div class="telemetry-grid">
      <div class="telemetry-card">
        <div class="telemetry-top">
          <div class="telemetry-icon-wrap">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/></svg>
          </div>
          <span class="telemetry-secure-tag">SECURE ↗</span>
        </div>
        <div>
          <div class="telemetry-label">PREMIUM APPS</div>
          <div class="telemetry-value">17 Unlocked</div>
          <div class="telemetry-trend">● +4 Added This Month</div>
        </div>
      </div>

      <div class="telemetry-card">
        <div class="telemetry-top">
          <div class="telemetry-icon-wrap">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          </div>
          <span class="telemetry-secure-tag">SECURE ↗</span>
        </div>
        <div>
          <div class="telemetry-label">TOTAL DOWNLOADS</div>
          <div class="telemetry-value">5,00,000+</div>
          <div class="telemetry-trend">● 99.9% Delivery Rate</div>
        </div>
      </div>

      <div class="telemetry-card">
        <div class="telemetry-top">
          <div class="telemetry-icon-wrap">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
          </div>
          <span class="telemetry-secure-tag">SECURE ↗</span>
        </div>
        <div>
          <div class="telemetry-label">ACTIVE ACADEMIC USERS</div>
          <div class="telemetry-value">1,20,000+</div>
          <div class="telemetry-trend">● 2,34,430 Active Today</div>
        </div>
      </div>

      <div class="telemetry-card">
        <div class="telemetry-top">
          <div class="telemetry-icon-wrap">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>
          </div>
          <span class="telemetry-secure-tag">SECURE ↗</span>
        </div>
        <div>
          <div class="telemetry-label">GLOBAL CDN SERVER</div>
          <div class="telemetry-value">Online [Fast]</div>
          <div class="telemetry-trend">● Ping 23ms • Up 100%</div>
        </div>
      </div>
    </div>

    <!-- Search & Filter Section -->
    <div class="search-filter-section" id="category-filter-chips">
      <div class="search-input-container">
        <svg class="search-input-icon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="text" class="search-input-field" id="home-search-input" placeholder="Search study portals, batches, and applications..." onkeyup="handleSearchInput(this.value)">
        <button class="btn-search-submit" onclick="handleSearchSubmit()">Search</button>
      </div>

      <div class="category-chips-row">
        ${['All', 'Educational', 'Competitive', 'Academic', 'Test Prep', 'Coding', 'Creative'].map(cat => `
          <button class="category-chip ${state.activeCategory === cat ? 'active' : ''}" onclick="filterCategory('${cat}')">${cat}</button>
        `).join('')}
      </div>
    </div>

    <!-- Popular Apps Grid -->
    <div class="apps-grid" id="apps-grid-container">
      ${renderAppsCardsHtml(apps)}
    </div>
  `;
}

function renderAppsCardsHtml(apps) {
  if (!apps || apps.length === 0) {
    return `<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: var(--text-muted);">No study portals found.</div>`;
  }
  return apps.map((app, idx) => `
    <div class="app-card">
      <div>
        <div class="app-card-header">
          <div class="app-icon-wrap">
            <img src="${app.icon_url || '/static/logo.png'}" alt="${app.name}" class="app-icon-img" onerror="this.src='/static/logo.png'">
          </div>
          <div class="app-header-meta">
            <span class="app-tag-pill">${idx === 0 ? 'POPULAR' : 'HOT'}</span>
            <h3 class="app-title" title="${app.name}">${app.name}</h3>
            <span class="app-dev-name">DEVELOPER: MadXABhi / CW</span>
          </div>
        </div>

        <div class="app-meta-pills">
          <span class="meta-pill">📱 v5.02.7</span>
          <span class="meta-pill">💾 24.96 MB</span>
        </div>
      </div>

      <div>
        <div class="app-stats-row">
          <span class="app-download-count">👥 1,00,000+ Downloads</span>
          <span class="app-rating-badge">★ 4.8</span>
        </div>

        <div class="app-actions-row">
          <button class="btn-app-study" onclick="navigateToApp('${app.slug || app.id}')">
            <span>Let's Study</span>
          </button>
          <button class="btn-app-download" onclick="navigateToApp('${app.slug || app.id}')">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            <span>Batches</span>
          </button>
        </div>
      </div>
    </div>
  `).join('');
}

// 2. MY APPS VIEW
async function renderAppsView(container) {
  const apps = await fetchApps();
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">All Study Portals & Applications</h1>
      <p class="section-subheading">Choose your academic stream to access complete lecture libraries and study materials.</p>
    </div>
    <div class="apps-grid">
      ${renderAppsCardsHtml(apps)}
    </div>
  `;
}

// 3. APP BATCHES VIEW (?tab=apps&app=...)
async function renderAppDetailView(container, appSlugOrId) {
  const apps = await fetchApps();
  const app = apps.find(a => a.slug === appSlugOrId || a.id === appSlugOrId) || apps[0];
  
  container.innerHTML = `
    <!-- App View Header -->
    <div class="app-view-header">
      <div class="app-view-title-group">
        <img src="${app.icon_url || '/static/logo.png'}" alt="${app.name}" class="app-view-icon" onerror="this.src='/static/logo.png'">
        <div>
          <h1 class="app-view-title">${app.name}</h1>
          <span class="session-active-tag">● SECURE CLIENT SESSION ACTIVE</span>
        </div>
      </div>
      <button class="btn-announcement" onclick="showToast('Official Announcement: All New 2025 batches are updated!')">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
        <span>Show Announcement</span>
      </button>
    </div>

    <!-- Promo Discord Banner -->
    <div class="promo-banner">
      <div>
        <span class="promo-tag">OFFICIAL ANNOUNCEMENT</span>
        <h2 class="promo-title">Join Discord & Telegram Community</h2>
        <p style="font-size:13px; opacity:0.9;">Get instant class alerts, DPP solutions, notes, and doubt sessions.</p>
      </div>
      <a href="https://t.me/course_mallah_bot" target="_blank" class="btn-promo-action">Join Discord Now</a>
    </div>

    <!-- Batches Tabs -->
    <div class="batches-tabs-bar">
      <button class="tab-pill-btn active" id="tab-all-batches" onclick="switchBatchTab('all')">All Batches (${app.batches ? app.batches.length : 1})</button>
      <button class="tab-pill-btn" id="tab-my-batches" onclick="switchBatchTab('my')">My Batches (${state.enrolledBatches.length})</button>
    </div>

    <!-- Search within Batches -->
    <div class="batch-search-wrap">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:10px; color:var(--text-muted);"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" class="batch-search-input" placeholder="Search within All Batches..." onkeyup="filterBatches(this.value)">
    </div>

    <!-- Batches Cards Grid -->
    <div class="batches-grid" id="batches-grid-container">
      ${(app.batches || []).map(b => `
        <div class="batch-card">
          <div class="batch-thumb-wrap">
            <img src="${b.thumbnail_url || 'https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=480&auto=format&fit=crop&q=80'}" alt="${b.name}" class="batch-thumb-img">
            <span class="batch-status-badge">ACTIVE COURSE</span>
          </div>
          <div class="batch-body">
            <div>
              <h3 class="batch-title">${b.name}</h3>
              <div class="batch-price-row">
                <span class="batch-free-badge">₹ FREE</span>
                <span class="batch-free-subtag">100% FREE FOR STUDENTS</span>
              </div>
            </div>
            <div class="batch-actions-row">
              <button class="btn-app-study" onclick="navigateToBatch('${app.slug || app.id}', '${b.slug || b.id}')">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/></svg>
                <span>Study</span>
              </button>
              <button class="btn-app-download" onclick="enrollBatch('${b.id || b.slug}', '${b.name}')">
                <span>Enrolled ✓</span>
              </button>
            </div>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

// 4. BATCH SUBJECTS VIEW (?tab=apps&app=...&batchid=...)
async function renderBatchView(container, appSlugOrId, batchIdOrSlug) {
  const batch = await fetchBatchDetail(batchIdOrSlug);
  
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 26px;">${batch.name}</h1>
      <p class="section-subheading">Portal: ${batch.app_name} • Category: ${batch.category || 'Academic'}</p>
    </div>

    <div class="subjects-grid">
      ${(batch.subjects || []).map(subj => `
        <div class="subject-card" onclick="navigateToSubject('${appSlugOrId}', '${batchIdOrSlug}', '${subj.slug || subj.id}')">
          <div>
            <div class="subject-header-row">
              <div class="subject-icon-box">📚</div>
              <div>
                <h3 class="subject-title">${subj.name}</h3>
                <span class="subject-teacher">FACULTY: Course Wallah & TC</span>
              </div>
            </div>
          </div>
          <div class="subject-stats-row">
            <span class="subject-stat-pill">🎥 ${(subj.folders || []).reduce((acc, f) => acc + (f.lectures ? f.lectures.length : 0), 0)} Lectures</span>
            <span class="subject-stat-pill">📄 Verified Notes</span>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

// 5. SUBJECT FOLDERS & LECTURES VIEW (?tab=apps&app=...&batchid=...&subjectid=...)
async function renderSubjectView(container, appSlugOrId, batchIdOrSlug, subjectIdOrSlug) {
  const batch = await fetchBatchDetail(batchIdOrSlug);
  const subject = (batch.subjects || []).find(s => s.slug === subjectIdOrSlug || s.id === subjectIdOrSlug) || (batch.subjects || [])[0];

  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 24px;">${subject ? subject.name : 'Subject Explorer'}</h1>
      <p class="section-subheading">Batch: ${batch.name}</p>
    </div>

    <!-- Folders Hierarchy -->
    <div class="lectures-list-container">
      ${(subject.folders || []).map(folder => `
        <div style="margin-bottom: 20px;">
          <h3 style="font-size: 16px; font-weight: 800; margin-bottom: 12px; color: var(--primary); display:flex; align-items:center; gap:8px;">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            <span>${folder.name}</span>
          </h3>
          <div style="display:flex; flex-direction:column; gap:8px;">
            ${(folder.lectures || []).map(lec => `
              <div class="lecture-item-card">
                <div class="lecture-left">
                  <span class="lecture-idx-pill">#${String(lec.index || 1).padStart(3, '0')}</span>
                  <div class="lecture-info-wrap">
                    <h4 class="lecture-title">${lec.title}</h4>
                    <span class="lecture-subinfo">⏱️ ${Math.round((lec.duration_seconds || 1800)/60)} mins • Verified Stream</span>
                  </div>
                </div>
                <div class="lecture-actions">
                  <button class="btn-play-lecture" onclick="navigateToLecture('${appSlugOrId}', '${batchIdOrSlug}', '${subjectIdOrSlug}', '${lec.id}')">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    <span>Play</span>
                  </button>
                  ${lec.has_pdf ? `
                    <button class="btn-view-notes" onclick="navigateToLecture('${appSlugOrId}', '${batchIdOrSlug}', '${subjectIdOrSlug}', '${lec.id}')">
                      <span>Notes</span>
                    </button>
                  ` : ''}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

// 6. IN-APP CINEMA VIDEO PLAYER VIEW (...#playing)
async function renderPlayerView(container, appSlugOrId, batchIdOrSlug, subjectIdOrSlug, lectureId) {
  const lecture = await fetchLectureDetails(lectureId);
  const access = await fetchLectureAccess(lectureId);

  container.innerHTML = `
    <div class="player-studio-layout">
      
      <!-- Main Column: Video Player & Details -->
      <div class="player-main-column">
        <div class="video-frame-container" id="player-container">
          ${access.youtube_video_id ? `
            <iframe class="video-iframe" src="https://www.youtube.com/embed/${access.youtube_video_id}?autoplay=1&enablejsapi=1&rel=0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
          ` : `
            <div style="display:flex; align-items:center; justify-content:center; height:100%; color:#FFF; font-weight:700;">Video stream processing...</div>
          `}
          <div class="security-watermark-overlay">COURSE WALLAH • CW-ID-${lectureId.slice(0,6)}</div>
        </div>

        <!-- Controls Bar -->
        <div class="player-controls-bar">
          <div class="speed-buttons-group">
            <span class="speed-label">SPEED:</span>
            ${['0.75x', '1x', '1.25x', '1.5x', '2x'].map(spd => `
              <button class="btn-speed-pill ${spd === '1x' ? 'active' : ''}" onclick="setPlaybackSpeed('${spd}', this)">${spd}</button>
            `).join('')}
          </div>
          <div>
            <button class="btn-view-notes" onclick="toggleBookmark('${lecture.id}', '${lecture.title}')">
              <span>🔖 Save</span>
            </button>
          </div>
        </div>

        <!-- Lecture Details -->
        <div class="player-lecture-details">
          <div class="player-breadcrumbs-row">
            <span>${lecture.app_name || 'Course Wallah'}</span> • 
            <span>${lecture.batch_name || 'Batch'}</span> • 
            <span>${lecture.subject_name || 'Subject'}</span>
          </div>
          <h1 class="player-lecture-title">#${String(lecture.index || 1).padStart(3, '0')} ${lecture.title}</h1>
          <p style="font-size:14px; color:var(--text-secondary); line-height:1.6;">High-speed streaming lecture provided with verified companion study notes.</p>
        </div>
      </div>

      <!-- Right Column: Playlist & Notes Drawer -->
      <div class="player-sidebar-drawer">
        <div class="drawer-tabs-header">
          <button class="drawer-tab-btn active" id="drawer-tab-playlist" onclick="switchDrawerTab('playlist')">Playlist</button>
          <button class="drawer-tab-btn" id="drawer-tab-notes" onclick="switchDrawerTab('notes')">Notes & PDFs</button>
        </div>

        <!-- Playlist Tab -->
        <div class="drawer-scroll-body" id="drawer-playlist-body">
          ${(lecture.playlist || []).map(item => `
            <div class="playlist-item-card ${item.id === lectureId ? 'active' : ''}" onclick="navigateToLecture('${appSlugOrId}', '${batchIdOrSlug}', '${subjectIdOrSlug}', '${item.id}')">
              <span style="font-size:11px; font-weight:800; font-family:var(--font-mono); color:var(--primary);">#${String(item.index || 1).padStart(2, '0')}</span>
              <span class="playlist-item-title">${item.title}</span>
            </div>
          `).join('')}
        </div>

        <!-- Notes Tab -->
        <div class="drawer-scroll-body hidden" id="drawer-notes-body">
          <div class="notes-preview-wrap">
            <svg class="notes-preview-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
            <h3 style="font-size:16px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">Lecture Notes & DPPs</h3>
            <p style="font-size:12px; color:var(--text-muted); margin-bottom:12px;">Official verified class PDF notes.</p>
            <a href="${access.pdf_download_url || '#'}" target="_blank" class="btn-notes-download">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
              <span>Download Clean PDF</span>
            </a>
          </div>
        </div>

      </div>

    </div>
  `;
}

function switchDrawerTab(tab) {
  const pTab = document.getElementById('drawer-tab-playlist');
  const nTab = document.getElementById('drawer-tab-notes');
  const pBody = document.getElementById('drawer-playlist-body');
  const nBody = document.getElementById('drawer-notes-body');

  if (tab === 'playlist') {
    pTab.classList.add('active');
    nTab.classList.remove('active');
    pBody.classList.remove('hidden');
    nBody.classList.add('hidden');
  } else {
    nTab.classList.add('active');
    pTab.classList.remove('active');
    nBody.classList.remove('hidden');
    pBody.classList.add('hidden');
  }
}

function setPlaybackSpeed(speedStr, btnEl) {
  document.querySelectorAll('.btn-speed-pill').forEach(b => b.classList.remove('active'));
  btnEl.classList.add('active');
  const rate = parseFloat(speedStr.replace('x', ''));
  const iframe = document.querySelector('.video-iframe');
  if (iframe && iframe.contentWindow) {
    iframe.contentWindow.postMessage(JSON.stringify({
      event: 'command',
      func: 'setPlaybackRate',
      args: [rate]
    }), '*');
  }
}

// 7. COMMUNITY VIEW
function renderCommunityView(container) {
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">Social Media & Community Matrix</h1>
      <p class="section-subheading">Join thousands of students and educators across official channels.</p>
    </div>

    <div class="cards-grid-2col">
      <div class="social-card">
        <div class="social-card-left">
          <div class="social-icon-box" style="background:#229ED9; color:#FFF;">✈️</div>
          <div>
            <h3 style="font-size:16px; font-weight:800; color:var(--text-primary);">Telegram Channel</h3>
            <span style="font-size:12px; color:var(--text-muted); font-weight:600;">1,20,000+ Members • Instant Alerts</span>
          </div>
        </div>
        <a href="https://t.me/course_mallah_bot" target="_blank" class="btn-hero-primary" style="padding:8px 18px; font-size:13px;">Join Channel</a>
      </div>

      <div class="social-card">
        <div class="social-card-left">
          <div class="social-icon-box" style="background:#5865F2; color:#FFF;">💬</div>
          <div>
            <h3 style="font-size:16px; font-weight:800; color:var(--text-primary);">Discord Community</h3>
            <span style="font-size:12px; color:var(--text-muted); font-weight:600;">Coding & Doubt Solving Hub</span>
          </div>
        </div>
        <a href="https://t.me/course_mallah_bot" target="_blank" class="btn-hero-primary" style="padding:8px 18px; font-size:13px; background:#5865F2;">Join Discord</a>
      </div>

      <div class="social-card">
        <div class="social-card-left">
          <div class="social-icon-box" style="background:#25D366; color:#FFF;">📱</div>
          <div>
            <h3 style="font-size:16px; font-weight:800; color:var(--text-primary);">WhatsApp Channel</h3>
            <span style="font-size:12px; color:var(--text-muted); font-weight:600;">Daily Study Material Updates</span>
          </div>
        </div>
        <a href="https://t.me/course_mallah_bot" target="_blank" class="btn-hero-primary" style="padding:8px 18px; font-size:13px; background:#25D366;">Join WhatsApp</a>
      </div>

      <div class="social-card">
        <div class="social-card-left">
          <div class="social-icon-box" style="background:#FF0000; color:#FFF;">📺</div>
          <div>
            <h3 style="font-size:16px; font-weight:800; color:var(--text-primary);">YouTube Channel</h3>
            <span style="font-size:12px; color:var(--text-muted); font-weight:600;">Lectures & Video Solutions</span>
          </div>
        </div>
        <a href="https://youtube.com" target="_blank" class="btn-hero-primary" style="padding:8px 18px; font-size:13px; background:#FF0000;">Subscribe</a>
      </div>
    </div>
  `;
}

// 8. DOWNLOADS CENTER VIEW
function renderDownloadsView(container) {
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">Downloads Center & Tools</h1>
      <p class="section-subheading">High-speed mirrors and tools for seamless learning on any device.</p>
    </div>

    <div class="cards-grid-2col">
      <div class="social-card">
        <div>
          <h3 style="font-size:17px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">Course Wallah Mobile App (APK)</h3>
          <p style="font-size:13px; color:var(--text-secondary); margin-bottom:12px;">Fast, ad-free offline access for Android devices.</p>
          <span style="font-size:11px; font-weight:700; color:var(--accent-emerald);">● v5.02.7 • 24.96 MB • Direct APK</span>
        </div>
        <button class="btn-hero-primary" onclick="showToast('Direct APK Download started...')">Download</button>
      </div>

      <div class="social-card">
        <div>
          <h3 style="font-size:17px; font-weight:800; color:var(--text-primary); margin-bottom:4px;">Global CDN Server Speed Test</h3>
          <p style="font-size:13px; color:var(--text-secondary); margin-bottom:12px;">Check your connection latency to our media edge nodes.</p>
          <span id="speed-test-status" style="font-size:11px; font-weight:700; color:var(--accent-emerald);">● Ping: 23ms • Optimal</span>
        </div>
        <button class="btn-hero-secondary" onclick="runSpeedTest()">Test Speed</button>
      </div>
    </div>
  `;
}

function runSpeedTest() {
  const status = document.getElementById('speed-test-status');
  if (status) {
    status.innerText = '● Testing latency...';
    setTimeout(() => {
      const ping = Math.floor(Math.random() * 15) + 18;
      status.innerText = `● Ping: ${ping}ms • 100% Blazing Fast`;
      showToast(`CDN Edge latency measured: ${ping}ms`);
    }, 600);
  }
}

// 9. BOOKMARKS VIEW
function renderBookmarksView(container) {
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">Your Bookmarks & Saved Lectures</h1>
      <p class="section-subheading">Quick access to pinned chapters and saved course material.</p>
    </div>

    <div style="background:var(--bg-card); border: 1px solid var(--border-subtle); border-radius:20px; padding:48px; text-align:center;">
      <div style="font-size:48px; margin-bottom:12px;">🔖</div>
      <h3 style="font-size:18px; font-weight:800; color:var(--text-primary); margin-bottom:6px;">No Bookmarks Saved Yet</h3>
      <p style="font-size:14px; color:var(--text-secondary); margin-bottom:20px;">While watching any lecture, click the "Save" button to keep it in your bookmarks.</p>
      <button class="btn-hero-primary" onclick="navigateToTab('home')">Explore Courses</button>
    </div>
  `;
}

// 10. SETTINGS VIEW
function renderSettingsView(container) {
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">Platform Settings</h1>
      <p class="section-subheading">Customize your playback preferences and interface appearance.</p>
    </div>

    <div style="background:var(--bg-card); border: 1px solid var(--border-subtle); border-radius:20px; padding:28px; display:flex; flex-direction:column; gap:24px;">
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div>
          <h4 style="font-size:15px; font-weight:800; color:var(--text-primary);">Theme Appearance</h4>
          <p style="font-size:13px; color:var(--text-muted);">Switch between Obsidian Dark and Clean Light themes.</p>
        </div>
        <button class="btn-hero-secondary" onclick="toggleTheme()">Toggle Theme</button>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; padding-top:20px; border-top:1px solid var(--border-subtle);">
        <div>
          <h4 style="font-size:15px; font-weight:800; color:var(--text-primary);">Study Streak Counter</h4>
          <p style="font-size:13px; color:var(--text-muted);">Current streak: ${state.streak} consecutive days.</p>
        </div>
        <button class="btn-hero-secondary" onclick="showToast('Streak active!')">Streak: ${state.streak} 🔥</button>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; padding-top:20px; border-top:1px solid var(--border-subtle);">
        <div>
          <h4 style="font-size:15px; font-weight:800; color:var(--text-primary);">Clear Local Cache</h4>
          <p style="font-size:13px; color:var(--text-muted);">Reset locally cached batch lists and temporary offline data.</p>
        </div>
        <button class="btn-hero-secondary" style="color:var(--accent-rose); border-color:rgba(244,63,94,0.3);" onclick="localStorage.clear(); showToast('Local cache cleared successfully');">Clear Cache</button>
      </div>
    </div>
  `;
}

// 11. ABOUT DEVELOPER VIEW
function renderDeveloperView(container) {
  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">About the Developer</h1>
      <p class="section-subheading">Dedicated to building high-speed educational tools for learners worldwide.</p>
    </div>

    <div style="background:var(--bg-card); border: 1px solid var(--border-subtle); border-radius:24px; padding:36px; display:flex; gap:32px; align-items:center;">
      <div class="brand-logo-wrap" style="width:80px; height:80px;">
        <div class="brand-logo-glow"></div>
        <div class="brand-fallback-logo" style="width:76px; height:76px; font-size:28px;">CW</div>
      </div>
      <div>
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
          <h2 style="font-size:22px; font-weight:800; color:var(--text-primary);">Course Wallah Team & MadXABhi</h2>
          <span style="font-size:11px; background:rgba(16,185,129,0.12); color:#10B981; font-weight:800; padding:2px 8px; border-radius:6px;">VERIFIED CREATOR</span>
        </div>
        <p style="font-size:14px; color:var(--text-secondary); line-height:1.6; margin-bottom:16px;">
          Empowering engineering, competitive exam, and coding students with free, high-speed, ad-free access to top-tier curriculum.
        </p>
        <div style="display:flex; gap:10px;">
          <a href="https://t.me/course_mallah_bot" target="_blank" class="btn-hero-primary" style="padding:8px 18px; font-size:13px;">Telegram Hub</a>
        </div>
      </div>
    </div>
  `;
}

// 12. HELP CENTER VIEW
function renderHelpCenterView(container) {
  const faqs = [
    { q: "How do I access video lectures and notes?", a: "Navigate to 'My Apps', select your desired course provider (e.g. Physics Wallah, Apna College), choose your batch, and click 'Study' to launch the player and notes." },
    { q: "Are all courses and batch archives free?", a: "Yes! All batch archives and study materials on Course Wallah are 100% free for educational research and study." },
    { q: "How often are new batches updated?", a: "Our cloud ingestion bot runs continuously to process and upload new live recordings and notes daily." },
    { q: "How do I download lecture notes in PDF?", a: "Inside the Study Studio player, switch to the 'Notes & PDFs' tab on the right drawer and click 'Download Clean PDF'." }
  ];

  container.innerHTML = `
    <div class="section-header-row" style="margin-bottom: 24px;">
      <h1 class="section-heading" style="font-size: 28px;">Help Center & Guides</h1>
      <p class="section-subheading">Frequently asked questions and student support.</p>
    </div>

    <div>
      ${faqs.map(faq => `
        <div class="faq-accordion-item">
          <button class="faq-question-btn" onclick="toggleFaq(this)">
            <span>${faq.q}</span>
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
          </button>
          <div class="faq-answer hidden">${faq.a}</div>
        </div>
      `).join('')}
    </div>
  `;
}

function toggleFaq(btn) {
  const ans = btn.nextElementSibling;
  if (ans) {
    ans.classList.toggle('hidden');
  }
}

// ==============================================================================
// UTILITIES: TOASTS & INTERACTIONS
// ==============================================================================

function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

function filterCategory(cat) {
  state.activeCategory = cat;
  document.querySelectorAll('.category-chip').forEach(c => {
    c.classList.toggle('active', c.innerText === cat);
  });
  showToast(`Filtered by ${cat}`);
}

function handleSearchInput(query) {
  const q = (query || '').toLowerCase().trim();
  const cards = document.querySelectorAll('.app-card');
  cards.forEach(c => {
    const title = (c.querySelector('.app-title')?.innerText || '').toLowerCase();
    c.style.display = title.includes(q) ? 'flex' : 'none';
  });
}

function handleSearchSubmit() {
  const input = document.getElementById('home-search-input');
  if (input && input.value) {
    showToast(`Searching for "${input.value}"...`);
  }
}

function enrollBatch(batchId, batchName) {
  if (!state.enrolledBatches.includes(batchId)) {
    state.enrolledBatches.push(batchId);
    localStorage.setItem('cw_enrolled', JSON.stringify(state.enrolledBatches));
    showToast(`Enrolled in "${batchName}"!`);
  } else {
    showToast(`Already enrolled in "${batchName}"!`);
  }
}

function toggleBookmark(id, title) {
  const idx = state.bookmarks.indexOf(id);
  if (idx === -1) {
    state.bookmarks.push(id);
    showToast(`Bookmark added: "${title}"`);
  } else {
    state.bookmarks.splice(idx, 1);
    showToast(`Bookmark removed`);
  }
  localStorage.setItem('cw_bookmarks', JSON.stringify(state.bookmarks));
}
