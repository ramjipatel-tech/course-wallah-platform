/**
 * COURSE WALLAH PLATFORM — COMPLETE MODERN SPA CLIENT (3D DESIGN & FAST STREAMING)
 * Architecture: App List (Streams) -> Batch List -> Subjects & Units -> Lecture (Cinematic Player + PDF.js Scroll Viewer)
 */

// Global State
const State = {
  currentRoute: 'home',
  routeParams: {},
  ytPlayer: null,
  isPlayerReady: false,
  isPlaying: false,
  currentTime: 0,
  duration: 0,
  playbackSpeed: 1.0,
  selectedQuality: 'auto',
  controlsTimeout: null,
  activePdfDoc: null,
  currentPdfPage: 1,
  totalPdfPages: 1,
  pdfScale: 1.25,
  pdfRenderingQueue: new Set(),
  renderedPages: new Set(),
  activeTab: 'video', // 'video' or 'notes'
  searchDebounce: null,
  availableQualities: [],
  hasCaptions: false,
  captionsEnabled: false,
  captionTracks: [],
  selectedCaptionTrack: null
};

// API Base Path
const API_BASE = '/api/v1';

// PDF.js worker setup
if (window.pdfjsLib) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
}

// ==============================================================================
// 1. SECURITY & ANTI-INSPECT DETERRENTS
// ==============================================================================

function initSecurityDeterrents() {
  // Prevent context menu (right click)
  document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    showToast('Right-click is disabled for content protection');
    return false;
  });

  // Block DevTools & Download keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // F12
    if (e.keyCode === 123) {
      e.preventDefault();
      return false;
    }
    // Ctrl+Shift+I (DevTools), Ctrl+Shift+J (Console), Ctrl+Shift+C (Inspect)
    if (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'i' || e.key === 'J' || e.key === 'j' || e.key === 'C' || e.key === 'c')) {
      e.preventDefault();
      return false;
    }
    // Ctrl+U (View Source)
    if (e.ctrlKey && (e.key === 'u' || e.key === 'U')) {
      e.preventDefault();
      return false;
    }
    // Ctrl+S (Save Page), Ctrl+P (Print)
    if (e.ctrlKey && (e.key === 's' || e.key === 'S' || e.key === 'p' || e.key === 'P')) {
      e.preventDefault();
      return false;
    }
  });
}

// ==============================================================================
// 2. ROUTER & 3D INTERACTIVITY
// ==============================================================================

function parseHash() {
  let hash = window.location.hash.replace(/^#\/?/, '');
  const pathname = window.location.pathname;

  if (pathname.includes('/ragni/admin') || pathname.includes('/ragni') || hash.startsWith('ragni/admin') || hash.startsWith('ragni')) {
    let subParams = [];
    if (hash.startsWith('ragni/admin/')) {
      subParams = hash.replace(/^ragni\/admin\//, '').split('/');
    } else if (hash.startsWith('ragni/')) {
      const parts = hash.split('/');
      subParams = parts.slice(1);
    }
    return {
      route: 'ragni_admin',
      params: subParams
    };
  }

  // Block public /admin path - redirect to home
  if (hash === 'admin' || hash.startsWith('admin/')) {
    return {
      route: 'home',
      params: []
    };
  }

  hash = hash || 'home';
  const parts = hash.split('/');
  return {
    route: parts[0] || 'home',
    params: parts.slice(1)
  };
}

function navigateTo(route, ...params) {
  const hash = params.length > 0 ? `#/${route}/${params.join('/')}` : `#/${route}`;
  window.location.hash = hash;
}

window.addEventListener('hashchange', handleRouteChange);
window.addEventListener('DOMContentLoaded', () => {
  initSecurityDeterrents();
  setupGlobalSearch();
  handleRouteChange();
});

async function handleRouteChange() {
  const { route, params } = parseHash();
  State.currentRoute = route;
  State.routeParams = params;

  cleanupActiveMedia();

  const root = document.getElementById('app-root');
  if (!root) return;
  root.innerHTML = renderSkeleton();

  try {
    switch (route) {
      case 'home':
      case 'apps':
        await renderAppList(root);
        break;
      case 'app':
        await renderBatchList(root, params[0]);
        break;
      case 'batch':
        await renderSubjectList(root, params[0]);
        break;
      case 'lecture':
        await renderLecturePage(root, params[0]);
        break;
      case 'ragni_admin':
        await renderAdminPortal(root, params[0] || 'overview');
        break;
      default:
        await renderAppList(root);
    }
    init3DTiltEffects();
  } catch (err) {
    console.error('Route error:', err);
    root.innerHTML = renderErrorState('Failed to load page content', err.message);
  }
}

function cleanupActiveMedia() {
  if (State.ytPlayer) {
    try {
      State.ytPlayer.destroy();
    } catch (e) {}
    State.ytPlayer = null;
    State.isPlayerReady = false;
    State.isPlaying = false;
  }
  clearTimeout(State.controlsTimeout);
  State.activePdfDoc = null;
  State.currentPdfPage = 1;
  State.totalPdfPages = 1;
  State.pdfRenderingQueue.clear();
  State.renderedPages.clear();
  State.activeTab = 'video';
  State.availableQualities = [];
  State.selectedQuality = 'auto';
  State.hasCaptions = false;
  State.captionsEnabled = false;
  State.captionTracks = [];
  State.selectedCaptionTrack = null;
}

function init3DTiltEffects() {
  const cards = document.querySelectorAll('.tilt-3d');
  cards.forEach(card => {
    card.addEventListener('mousemove', (e) => {
      const rect = card.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      const rotateX = ((y - centerY) / centerY) * -8;
      const rotateY = ((x - centerX) / centerX) * 8;

      card.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-6px) scale3d(1.02, 1.02, 1.02)`;
    });

    card.addEventListener('mouseleave', () => {
      card.style.transform = 'perspective(1000px) rotateX(0deg) rotateY(0deg) translateY(0) scale3d(1, 1, 1)';
    });
  });
}

// ==============================================================================
// 3. PAGE 1: 3D EDUCATIONAL STREAMS (HOMEPAGE)
// ==============================================================================

async function renderAppList(container) {
  setBreadcrumbs([]);
  const resp = await fetch(`${API_BASE}/apps`);
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const apps = await resp.json();

  let html = `
    <div class="hero-section">
      <div class="hero-badge">
        <span class="pulse-dot"></span>
        <span>COURSE WALLAH 3D LEARNING PORTAL</span>
      </div>
      <h1 class="hero-title">Your Learning, Organized.</h1>
      <p class="hero-subtitle">High-definition lectures, chapter-wise notes, and complete structured academic streams.</p>
    </div>

    <div class="section-header">
      <div class="section-title-wrap">
        <span class="section-icon">📚</span>
        <h2 class="section-title">Educational Streams</h2>
        <span class="section-count">${apps.length} Active Streams</span>
      </div>
    </div>
  `;

  if (!apps || apps.length === 0) {
    html += `
      <div class="empty-state">
        <div class="empty-icon">📁</div>
        <h3 class="empty-title">No Educational Streams Available</h3>
        <p class="empty-desc">Courses are currently being ingested. Check back shortly.</p>
      </div>
    `;
    container.innerHTML = html;
    return;
  }

  html += `<div class="app-grid">`;
  for (const app of apps) {
    html += `
      <div class="app-card tilt-3d" onclick="navigateTo('app', '${app.slug}')">
        <div class="card-glow-bg"></div>
        <div class="app-card-top">
          <div class="app-card-icon-3d">
            <img src="/static/logo.png" alt="${escapeHtml(app.name)}" onerror="this.src='/static/logo.png'">
          </div>
          <div class="app-card-info">
            <h3 class="app-card-title">${escapeHtml(app.name)}</h3>
            <p class="app-card-desc">${escapeHtml(app.description || 'Verified engineering curriculum with video lectures & study notes.')}</p>
          </div>
        </div>
        <div class="app-card-bottom">
          <span class="app-batch-badge">📚 ${app.total_batches} Batches Available</span>
          <span class="app-open-btn">Explore Stream →</span>
        </div>
      </div>
    `;
  }
  html += `</div>`;

  container.innerHTML = html;
}

// ==============================================================================
// 4. PAGE 2: BATCH LIST (3D THUMBNAIL CARDS + VIDEO & PDF COUNTS)
// ==============================================================================

async function renderBatchList(container, appSlug) {
  const resp = await fetch(`${API_BASE}/apps/${appSlug}`);
  if (!resp.ok) throw new Error('Stream not found');
  const app = await resp.json();

  setBreadcrumbs([
    { label: 'All Streams', route: 'apps' },
    { label: app.name, active: true }
  ]);

  let html = `
    <div class="subject-header-banner">
      <div class="hero-badge">STREAM: ${escapeHtml(app.name.toUpperCase())}</div>
      <h1 class="subject-banner-title">${escapeHtml(app.name)}</h1>
      <p class="hero-subtitle" style="margin: 0; text-align: left;">${escapeHtml(app.description || 'Select an active academic batch to begin studying.')}</p>
    </div>

    <div class="section-header">
      <div class="section-title-wrap">
        <span class="section-icon">🎓</span>
        <h2 class="section-title">Available Batches</h2>
        <span class="section-count">${app.batches.length} Batches</span>
      </div>
    </div>
  `;

  if (!app.batches || app.batches.length === 0) {
    html += `
      <div class="empty-state">
        <div class="empty-icon">⏳</div>
        <h3 class="empty-title">This Stream is Being Prepared</h3>
        <p class="empty-desc">No batches published yet in this stream.</p>
      </div>
    `;
    container.innerHTML = html;
    return;
  }

  html += `<div class="batch-grid">`;
  for (const b of app.batches) {
    html += `
      <div class="batch-card tilt-3d" onclick="navigateTo('batch', '${b.slug}')">
        <div class="batch-thumbnail-wrap">
          <img src="${escapeHtml(b.thumbnail_url || '/static/logo.png')}" alt="${escapeHtml(b.name)}" class="batch-thumb-img" onerror="this.src='/static/logo.png'">
          <div class="batch-thumb-overlay">
            <span class="batch-category-badge">${escapeHtml(b.category || 'Curriculum')}</span>
          </div>
        </div>

        <div class="batch-body">
          <h3 class="batch-card-title">${escapeHtml(b.name)}</h3>
          
          <div class="batch-tags-row">
            ${b.branch ? `<span class="batch-tag">${escapeHtml(b.branch)}</span>` : ''}
            ${b.semester ? `<span class="batch-tag">${escapeHtml(b.semester)}</span>` : ''}
            ${b.academic_year ? `<span class="batch-tag">${escapeHtml(b.academic_year)}</span>` : ''}
          </div>

          <!-- Video, PDF and Unit Counts -->
          <div class="batch-stats-ribbon">
            <div class="stat-pill"><span class="pill-icon">🎬</span> <b>${b.total_videos || 0}</b> Videos</div>
            <div class="stat-pill"><span class="pill-icon">📄</span> <b>${b.total_pdfs || 0}</b> PDFs</div>
            <div class="stat-pill"><span class="pill-icon">📁</span> <b>${b.total_units || 0}</b> Units</div>
          </div>
        </div>

        <div class="app-card-bottom" style="margin-top: 14px; padding-top: 12px;">
          <span class="app-batch-badge">Verified Curriculum</span>
          <span class="app-open-btn">Open Batch →</span>
        </div>
      </div>
    `;
  }
  html += `</div>`;

  container.innerHTML = html;
}

// ==============================================================================
// 5. PAGE 3 & 4: BATCH HIERARCHY (SUBJECTS & UNITS ACCORDION)
// ==============================================================================

async function renderSubjectList(container, batchSlug) {
  const resp = await fetch(`${API_BASE}/batches/${batchSlug}`);
  if (!resp.ok) throw new Error('Batch not found');
  const batch = await resp.json();

  setBreadcrumbs([
    { label: 'All Streams', route: 'apps' },
    { label: batch.app_name, route: `app/${batch.app_slug || 'course-wallah-e2e'}` },
    { label: batch.name, active: true }
  ]);

  let html = `
    <div class="subject-header-banner">
      <div class="hero-badge">BATCH OVERVIEW</div>
      <h1 class="subject-banner-title">${escapeHtml(batch.name)}</h1>
      <div class="subject-banner-meta">
        <span>📚 Stream: <b>${escapeHtml(batch.app_name)}</b></span>
        ${batch.branch ? `<span>🔬 Branch: <b>${escapeHtml(batch.branch)}</b></span>` : ''}
        ${batch.semester ? `<span>🎓 Semester: <b>${escapeHtml(batch.semester)}</b></span>` : ''}
        ${batch.academic_year ? `<span>📅 Year: <b>${escapeHtml(batch.academic_year)}</b></span>` : ''}
      </div>
    </div>
  `;

  if (!batch.subjects || batch.subjects.length === 0) {
    html += `
      <div class="empty-state">
        <div class="empty-icon">📂</div>
        <h3 class="empty-title">No Subjects Published Yet</h3>
        <p class="empty-desc">The content worker is processing syllabus data for this batch.</p>
      </div>
    `;
    container.innerHTML = html;
    return;
  }

  for (const subj of batch.subjects) {
    html += `
      <div style="margin-bottom: 36px;">
        <div class="section-header">
          <div class="section-title-wrap">
            <span class="section-icon">📖</span>
            <h2 class="section-title">${escapeHtml(subj.name)}</h2>
            <span class="section-count">${subj.folders.length} Units</span>
          </div>
        </div>

        <div class="folder-accordion">
    `;

    for (const folder of subj.folders) {
      html += `
        <div class="folder-card">
          <div class="folder-header" onclick="toggleFolder(this)">
            <div class="folder-title-left">
              ${folder.unit_number ? `<span class="folder-unit-badge">${escapeHtml(folder.unit_number)}</span>` : ''}
              <span class="folder-name">${escapeHtml(folder.name)}</span>
            </div>
            <span class="folder-count-badge">${folder.lectures.length} Lectures ▼</span>
          </div>
          <div class="lectures-list">
      `;

      for (const lec of folder.lectures) {
        const hasVideo = Boolean(lec.has_video);
        const hasPdf = Boolean(lec.has_pdf);
        const isImage = (lec.category === 'image') || (!hasVideo && !hasPdf && lec.thumbnail_url);

        let badgeHtml = '';
        if (hasVideo) badgeHtml += `<span class="media-badge video">▶ Video</span>`;
        if (hasPdf) badgeHtml += `<span class="media-badge pdf">📄 PDF Notes</span>`;
        if (isImage) badgeHtml += `<span class="media-badge image" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);">🖼️ Image / Notes</span>`;

        let actionBtnsHtml = '';
        if (hasVideo) {
          actionBtnsHtml += `<button class="btn-action-sm btn-play-sm" onclick="navigateTo('lecture', '${lec.id}')">▶ Play</button>`;
        }
        if (hasPdf) {
          actionBtnsHtml += `<button class="btn-action-sm btn-notes-sm" onclick="navigateTo('lecture', '${lec.id}'); setTimeout(()=>switchLectureTab('notes', '${lec.id}'), 300)">📄 Notes</button>`;
        }
        if (isImage && !hasVideo && !hasPdf) {
          actionBtnsHtml += `<button class="btn-action-sm btn-notes-sm" onclick="navigateTo('lecture', '${lec.id}')">🖼️ View</button>`;
        }

        html += `
          <div class="lecture-row">
            <div class="lecture-row-left" onclick="navigateTo('lecture', '${lec.id}')">
              <span class="lecture-num">#${lec.index}</span>
              <span class="lecture-title">${escapeHtml(lec.title)}</span>
              <div class="lecture-badges">
                ${badgeHtml}
              </div>
            </div>
            <div class="lecture-action-btns">
              ${actionBtnsHtml}
            </div>
          </div>
        `;
      }

      html += `
          </div>
        </div>
      `;
    }

    html += `
        </div>
      </div>
    `;
  }

  container.innerHTML = html;
}

function toggleFolder(headerEl) {
  const listEl = headerEl.nextElementSibling;
  if (listEl) {
    listEl.classList.toggle('hidden');
    const badge = headerEl.querySelector('.folder-count-badge');
    if (badge) {
      badge.textContent = listEl.classList.contains('hidden')
        ? badge.textContent.replace('▲', '▼')
        : badge.textContent.replace('▼', '▲');
    }
  }
}

// ==============================================================================
// 6. PAGE 5: CLEAN LECTURE PAGE (VIDEO PLAYER + FAST SCROLL PDF VIEWER)
// ==============================================================================

async function renderLecturePage(container, lectureId) {
  const [lecResp, accessResp] = await Promise.all([
    fetch(`${API_BASE}/lectures/${lectureId}`),
    fetch(`${API_BASE}/lectures/${lectureId}/access`)
  ]);

  if (!lecResp.ok) throw new Error('Lecture not found or unpublished');
  const lecture = await lecResp.json();
  const access = accessResp.ok ? await accessResp.json() : {};

  // Clean Breadcrumbs
  setBreadcrumbs([
    { label: 'All Streams', route: 'apps' },
    { label: lecture.app_name || 'Course Wallah', route: `app/${lecture.app_slug || 'course-wallah-e2e'}` },
    { label: lecture.batch_name || 'Batch', route: `batch/${lecture.batch_slug || 'engg-math'}` },
    { label: lecture.title, active: true }
  ]);

  const hasVideo = Boolean(lecture.has_video);
  const hasPdf = Boolean(lecture.has_pdf);
  const isImageOnly = !hasVideo && !hasPdf && Boolean(lecture.thumbnail_url);
  const defaultTab = hasVideo ? 'video' : 'notes';
  State.activeTab = defaultTab;

  let tabsHtml = '';
  if (hasVideo && hasPdf) {
    tabsHtml = `
      <div class="lecture-tabs-wrap">
        <button class="lecture-tab-btn active" id="tab-btn-video" onclick="switchLectureTab('video')">
          <span>▶ Video Lecture</span>
        </button>
        <button class="lecture-tab-btn" id="tab-btn-notes" onclick="switchLectureTab('notes', '${lecture.id}')">
          <span>📄 Study Notes (PDF)</span>
        </button>
      </div>
    `;
  } else if (hasVideo) {
    tabsHtml = `
      <div class="lecture-tabs-wrap">
        <button class="lecture-tab-btn active" id="tab-btn-video" onclick="switchLectureTab('video')">
          <span>▶ Video Lecture</span>
        </button>
      </div>
    `;
  } else if (hasPdf) {
    tabsHtml = `
      <div class="lecture-tabs-wrap">
        <button class="lecture-tab-btn active" id="tab-btn-notes" onclick="switchLectureTab('notes', '${lecture.id}')">
          <span>📄 Study Notes (PDF)</span>
        </button>
      </div>
    `;
  } else if (isImageOnly) {
    tabsHtml = `
      <div class="lecture-tabs-wrap">
        <button class="lecture-tab-btn active" id="tab-btn-notes">
          <span>🖼️ Study Material</span>
        </button>
      </div>
    `;
  }

  let html = `
    <div class="lecture-page-layout-clean">
      
      <!-- LECTURE HEADER WITH CLEAN CONCISE METADATA -->
      <div class="lecture-header-bar">
        <div class="lecture-title-wrap">
          <span class="lecture-index-chip">LECTURE #${lecture.index}</span>
          <h1 class="lecture-page-title">${escapeHtml(lecture.title)}</h1>
        </div>

        <!-- Mode Toggle Tabs (Video Lecture vs Study Notes vs Material) -->
        ${tabsHtml}
      </div>

      ${hasVideo ? `
      <!-- 1. VIDEO PLAYER VIEW -->
      <div id="lecture-video-view">
        <div class="player-wrapper" id="custom-player-wrapper">
          <!-- Top Branded Overlay (Course Wallah Logo) -->
          <div class="player-watermark">
            <img src="/static/logo.png" alt="Course Wallah" class="player-logo-badge">
            <span>Course Wallah Player</span>
          </div>

          <!-- YouTube Video IFrame Container (Hidden platform chrome) -->
          <div id="yt-player-target" class="player-video-container"></div>

          <!-- Big Center Play Button -->
          <div class="player-center-play" id="center-play-btn" onclick="togglePlayPause()" title="Play Lecture">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
          </div>

          <!-- Interactive Custom Controls Bar -->
          <div class="player-controls-bar" id="player-controls-bar">
            <!-- Scrubber / Timeline Bar with Tooltip -->
            <div class="player-scrubber-container" id="player-scrubber" onclick="handleScrub(event)" onmousemove="handleScrubHover(event)">
              <div class="player-scrubber-buffered" id="scrubber-buffered"></div>
              <div class="player-scrubber-progress" id="scrubber-progress">
                <div class="player-scrubber-handle"></div>
              </div>
              <div class="player-scrubber-tooltip" id="scrubber-tooltip">00:00</div>
            </div>

            <!-- Controls Row -->
            <div class="player-controls-row">
              <div class="controls-left">
                <!-- Play / Pause -->
                <button class="ctrl-btn" id="btn-play-pause" onclick="togglePlayPause()" title="Play/Pause (Space)">
                  <svg id="icon-play" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                  <svg id="icon-pause" class="hidden" viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><rect x="6" y="4" width="4" height="16"></rect><rect x="14" y="4" width="4" height="16"></rect></svg>
                </button>

                <!-- -10s Rewind -->
                <button class="ctrl-btn ctrl-skip" onclick="seekRelative(-10)" title="Rewind 10s (←)">
                  <span class="skip-icon">↺</span> 10s
                </button>

                <!-- +10s Forward -->
                <button class="ctrl-btn ctrl-skip" onclick="seekRelative(10)" title="Forward 10s (→)">
                  <span class="skip-icon">↻</span> 10s
                </button>

                <!-- Volume Control -->
                <div class="volume-control-wrap">
                  <button class="ctrl-btn" id="btn-mute" onclick="toggleMute()" title="Mute (M)">
                    <svg id="icon-vol-high" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
                    <svg id="icon-vol-mute" class="hidden" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><line x1="23" y1="9" x2="17" y2="15"></line><line x1="17" y1="9" x2="23" y2="15"></line></svg>
                  </button>
                  <input type="range" class="volume-slider" id="volume-slider" min="0" max="100" value="100" oninput="handleVolumeChange(this.value)">
                </div>

                <!-- Time Display -->
                <span class="time-display" id="time-display">00:00 / 00:00</span>
              </div>

              <div class="controls-right">
                <!-- Playback Speed Menu -->
                <div class="settings-menu-btn">
                  <button class="ctrl-btn speed-badge-btn" onclick="toggleSpeedMenu()" title="Playback Speed">
                    <span id="speed-label">1x</span>
                  </button>
                  <div class="menu-popup" id="speed-popup">
                    <div class="menu-header">Playback Speed</div>
                    <div class="menu-item" onclick="setSpeed(0.5)">0.5x</div>
                    <div class="menu-item" onclick="setSpeed(0.75)">0.75x</div>
                    <div class="menu-item active" onclick="setSpeed(1.0)">1.0x (Normal)</div>
                    <div class="menu-item" onclick="setSpeed(1.25)">1.25x</div>
                    <div class="menu-item" onclick="setSpeed(1.5)">1.5x</div>
                    <div class="menu-item" onclick="setSpeed(1.75)">1.75x</div>
                    <div class="menu-item" onclick="setSpeed(2.0)">2.0x</div>
                  </div>
                </div>

                <!-- Quality Menu (Dynamic based on source stream) -->
                <div class="settings-menu-btn">
                  <button class="ctrl-btn" onclick="toggleQualityMenu()" title="Video Quality">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
                  </button>
                  <div class="menu-popup" id="quality-popup">
                    <div class="menu-header">Streaming Quality</div>
                    <div id="quality-options-list">
                      <div class="menu-item active" onclick="setQuality('auto')">Auto (Adaptive Bitrate)</div>
                    </div>
                  </div>
                </div>

                <!-- Captions (CC) Menu (Hidden by default, shown only if available) -->
                <div class="settings-menu-btn" id="cc-btn-wrapper">
                  <button class="ctrl-btn hidden" id="btn-captions" onclick="toggleCaptions()" title="Subtitles / Captions (C)">
                    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="2" y="4" width="20" height="16" rx="3"></rect>
                      <path d="M7 15h2a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2H7v6z"></path>
                      <path d="M14 15h2a2 2 0 0 0 2-2v-2a2 2 0 0 0-2-2h-2v6z"></path>
                    </svg>
                  </button>
                  <div class="menu-popup" id="captions-popup">
                    <div class="menu-header">Subtitles / Captions</div>
                    <div id="captions-options-list">
                      <div class="menu-item active" onclick="setCaptionTrack(null)">Off</div>
                    </div>
                  </div>
                </div>

                <!-- Fullscreen -->
                <button class="ctrl-btn" id="btn-fullscreen" onclick="toggleFullscreen()" title="Fullscreen (F)">
                  <svg id="icon-fs-enter" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"></path></svg>
                  <svg id="icon-fs-exit" class="hidden" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"></path></svg>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      ` : ''}

      ${hasPdf ? `
      <!-- 2. FAST IN-SITE PDF NOTES VIEW (CONTINUOUS SMOOTH SCROLL) -->
      <div id="lecture-notes-view" class="${hasVideo ? 'hidden' : ''}">
        <div class="pdf-viewer-section" id="pdf-viewer-wrapper">
          <!-- PDF Floating Control Toolbar -->
          <div class="pdf-toolbar">
            <div class="pdf-toolbar-left">
              <span class="pdf-badge-title">VERIFIED NOTES</span>
              <button class="pdf-btn" id="pdf-prev-btn" onclick="changePdfPage(-1)" title="Previous Page">◀ Prev</button>
              <button class="pdf-btn" id="pdf-next-btn" onclick="changePdfPage(1)" title="Next Page">Next ▶</button>
              <span class="pdf-page-indicator" id="pdf-page-num">Loading...</span>
            </div>
            <div class="pdf-toolbar-right">
              <button class="pdf-btn" onclick="zoomPdf(-0.2)" title="Zoom Out">－</button>
              <button class="pdf-btn" onclick="zoomPdf(0.2)" title="Zoom In">＋</button>
              <button class="pdf-btn" onclick="fitPdfWidth()" title="Fit Width">↔ Fit Width</button>
              <button class="pdf-btn" onclick="togglePdfFullscreen()" title="Fullscreen PDF">⛶ Fullscreen</button>
            </div>
          </div>

          <!-- PDF Continuous Scroll Canvas Viewport -->
          <div class="pdf-canvas-viewport" id="pdf-viewport" oncontextmenu="return false;">
            <div class="pdf-loading-box">
              <div class="spinner"></div>
              <p>Loading encrypted study notes securely...</p>
            </div>
          </div>
        </div>
      </div>
      ` : ''}

      ${isImageOnly ? `
      <!-- 3. IMAGE STUDY MATERIAL VIEW -->
      <div id="lecture-image-view">
        <div class="image-viewer-card" style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 16px; padding: 24px; text-align: center; margin-bottom: 24px;">
          <img src="${escapeHtml(lecture.thumbnail_url)}" alt="${escapeHtml(lecture.title)}" style="max-width: 100%; max-height: 70vh; border-radius: 12px; object-fit: contain; box-shadow: 0 10px 30px rgba(0,0,0,0.5);">
          <div style="margin-top: 16px; color: var(--text-muted); font-size: 0.9rem;">
            <span>📸 Verified Study Material Reference Image</span>
          </div>
        </div>
      </div>
      ` : ''}

      <!-- PREVIOUS / NEXT LECTURE NAVIGATION -->
      <div class="lecture-nav-buttons">
        <button class="nav-arrow-btn" ${lecture.prev_lecture ? `onclick="navigateTo('lecture', '${lecture.prev_lecture.id}')"` : 'disabled'}>
          ← Previous: ${lecture.prev_lecture ? escapeHtml(lecture.prev_lecture.title) : 'Start'}
        </button>
        <button class="nav-arrow-btn" ${lecture.next_lecture ? `onclick="navigateTo('lecture', '${lecture.next_lecture.id}')"` : 'disabled'}>
          Next: ${lecture.next_lecture ? escapeHtml(lecture.next_lecture.title) : 'End'} →
        </button>
      </div>

    </div>
  `;

  container.innerHTML = html;

  // Initialize YouTube IFrame Player
  if (hasVideo && access && access.has_video && access.youtube_video_id) {
    initYouTubePlayer(access.youtube_video_id);
  }

  // Auto-preload PDF if active
  if (hasPdf) {
    loadLecturePdf(lecture.id);
  }

  setupPlayerShortcuts();
}

function switchLectureTab(tabName, lectureId) {
  State.activeTab = tabName;
  const btnVideo = document.getElementById('tab-btn-video');
  const btnNotes = document.getElementById('tab-btn-notes');
  const viewVideo = document.getElementById('lecture-video-view');
  const viewNotes = document.getElementById('lecture-notes-view');

  if (tabName === 'video') {
    if (btnVideo) btnVideo.classList.add('active');
    if (btnNotes) btnNotes.classList.remove('active');
    if (viewVideo) viewVideo.classList.remove('hidden');
    if (viewNotes) viewNotes.classList.add('hidden');
  } else {
    if (btnVideo) btnVideo.classList.remove('active');
    if (btnNotes) btnNotes.classList.add('active');
    if (viewVideo) viewVideo.classList.add('hidden');
    if (viewNotes) viewNotes.classList.remove('hidden');

    requestAnimationFrame(() => {
      setTimeout(() => {
        if (State.activePdfDoc) {
          fitPdfWidth();
        } else if (lectureId) {
          loadLecturePdf(lectureId);
        }
      }, 50);
    });
  }
}

// ==============================================================================
// 7. YOUTUBE CUSTOM LEARNING PLAYER CONTROLLER
// ==============================================================================

function initYouTubePlayer(videoId) {
  if (!window.YT || !window.YT.Player) {
    window.onYouTubeIframeAPIReady = () => createPlayerInstance(videoId);
  } else {
    createPlayerInstance(videoId);
  }
}

function createPlayerInstance(videoId) {
  State.ytPlayer = new YT.Player('yt-player-target', {
    videoId: videoId,
    playerVars: {
      autoplay: 0,
      controls: 0,
      modestbranding: 1,
      rel: 0,
      fs: 0,
      disablekb: 1,
      iv_load_policy: 3,
      playsinline: 1,
      cc_load_policy: 0,
      origin: window.location.origin
    },
    events: {
      onReady: onPlayerReady,
      onStateChange: onPlayerStateChange,
      onPlaybackQualityChange: onPlaybackQualityChange
    }
  });
}

function onPlayerReady(event) {
  State.isPlayerReady = true;
  State.duration = State.ytPlayer.getDuration() || 0;
  updateTimeDisplay(0, State.duration);

  // Dynamic quality and captions detection
  detectQualityLevels();
  detectCaptionTracks();

  // Setup time & buffer update loop
  setInterval(() => {
    if (State.isPlayerReady && State.ytPlayer) {
      if (State.isPlaying) {
        State.currentTime = State.ytPlayer.getCurrentTime() || 0;
        updateScrubber(State.currentTime, State.duration);
        updateTimeDisplay(State.currentTime, State.duration);
      }
      if (State.ytPlayer.getVideoLoadedFraction) {
        const buffered = State.ytPlayer.getVideoLoadedFraction();
        const bufEl = document.getElementById('scrubber-buffered');
        if (bufEl) bufEl.style.width = `${buffered * 100}%`;
      }
    }
  }, 350);

  // Auto-hide controls during playback
  const wrapper = document.getElementById('custom-player-wrapper');
  if (wrapper) {
    wrapper.addEventListener('mousemove', showControls);
    wrapper.addEventListener('mouseleave', hideControls);
  }
}

const QUALITY_MAP = {
  'highres': { label: '2160p / 4K UHD', rank: 6 },
  'hd2160': { label: '2160p / 4K UHD', rank: 6 },
  'hd1440': { label: '1440p / 2K QHD', rank: 5 },
  'hd1080': { label: '1080p / Full HD', rank: 4 },
  'hd720': { label: '720p / HD', rank: 3 },
  'large': { label: '480p / SD', rank: 2 },
  'medium': { label: '360p', rank: 1 },
  'small': { label: '240p', rank: 0 },
  'tiny': { label: '144p', rank: -1 }
};

function detectQualityLevels() {
  if (!State.ytPlayer || typeof State.ytPlayer.getAvailableQualityLevels !== 'function') return;
  try {
    const levels = State.ytPlayer.getAvailableQualityLevels();
    if (Array.isArray(levels)) {
      State.availableQualities = levels;
      renderQualityMenu(levels);
    }
  } catch (e) {
    console.warn('Could not detect quality levels:', e);
  }
}

function renderQualityMenu(levels) {
  const listEl = document.getElementById('quality-options-list');
  if (!listEl) return;

  let html = `<div class="menu-item ${State.selectedQuality === 'auto' ? 'active' : ''}" onclick="setQuality('auto')">Auto (Adaptive Bitrate)</div>`;

  let activeLevels = levels;
  if (!Array.isArray(activeLevels) || activeLevels.length === 0) {
    const rawRes = (State.currentLecture?.video?.resolution || '720p').toLowerCase().trim();
    const fallbackTiers = {
      '2160p': ['hd2160', 'hd1440', 'hd1080', 'hd720', 'large', 'medium', 'small'],
      '1440p': ['hd1440', 'hd1080', 'hd720', 'large', 'medium', 'small'],
      '1080p': ['hd1080', 'hd720', 'large', 'medium', 'small'],
      '720p': ['hd720', 'large', 'medium', 'small'],
      '480p': ['large', 'medium', 'small'],
      '360p': ['medium', 'small'],
      '240p': ['small']
    };
    activeLevels = fallbackTiers[rawRes] || fallbackTiers['720p'];
  }

  if (Array.isArray(activeLevels) && activeLevels.length > 0) {
    const seenRanks = new Set();
    const filtered = [];

    for (const lvl of activeLevels) {
      if (lvl === 'auto' || lvl === 'default' || !QUALITY_MAP[lvl]) continue;
      const qMeta = QUALITY_MAP[lvl];
      if (!seenRanks.has(qMeta.rank)) {
        seenRanks.add(qMeta.rank);
        filtered.push({ code: lvl, label: qMeta.label, rank: qMeta.rank });
      }
    }

    filtered.sort((a, b) => b.rank - a.rank);

    for (const q of filtered) {
      const isActive = State.selectedQuality === q.code;
      html += `<div class="menu-item ${isActive ? 'active' : ''}" onclick="setQuality('${q.code}')">${escapeHtml(q.label)}</div>`;
    }
  }

  listEl.innerHTML = html;
}

function onPlaybackQualityChange(event) {
  detectQualityLevels();
}

function onPlayerStateChange(event) {
  const centerBtn = document.getElementById('center-play-btn');
  const iconPlay = document.getElementById('icon-play');
  const iconPause = document.getElementById('icon-pause');

  if (event.data === YT.PlayerState.PLAYING) {
    State.isPlaying = true;
    if (centerBtn) centerBtn.classList.add('hidden');
    if (iconPlay) iconPlay.classList.add('hidden');
    if (iconPause) iconPause.classList.remove('hidden');
    showControls();
    detectQualityLevels();
    detectCaptionTracks();
  } else {
    State.isPlaying = false;
    if (centerBtn) centerBtn.classList.remove('hidden');
    if (iconPlay) iconPlay.classList.remove('hidden');
    if (iconPause) iconPause.classList.add('hidden');
    showControls();
  }
}

function togglePlayPause() {
  if (!State.ytPlayer || !State.isPlayerReady) return;
  if (State.isPlaying) {
    State.ytPlayer.pauseVideo();
  } else {
    State.ytPlayer.playVideo();
  }
}

function seekRelative(seconds) {
  if (!State.ytPlayer || !State.isPlayerReady) return;
  const target = Math.max(0, Math.min(State.duration, State.currentTime + seconds));
  State.ytPlayer.seekTo(target, true);
  State.currentTime = target;
  updateScrubber(target, State.duration);
  updateTimeDisplay(target, State.duration);
  showControls();
}

function handleScrub(e) {
  if (!State.ytPlayer || !State.isPlayerReady || !State.duration) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const targetTime = pos * State.duration;
  State.ytPlayer.seekTo(targetTime, true);
  State.currentTime = targetTime;
  updateScrubber(targetTime, State.duration);
  updateTimeDisplay(targetTime, State.duration);
}

function handleScrubHover(e) {
  if (!State.duration) return;
  const rect = e.currentTarget.getBoundingClientRect();
  const pos = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  const hoverTime = pos * State.duration;
  const tooltip = document.getElementById('scrubber-tooltip');
  if (tooltip) {
    tooltip.textContent = formatTime(hoverTime);
    tooltip.style.left = `${pos * 100}%`;
  }
}

function updateScrubber(current, duration) {
  const progress = document.getElementById('scrubber-progress');
  if (progress && duration > 0) {
    const pct = (current / duration) * 100;
    progress.style.width = `${pct}%`;
  }
}

function updateTimeDisplay(current, duration) {
  const el = document.getElementById('time-display');
  if (el) {
    el.textContent = `${formatTime(current)} / ${formatTime(duration)}`;
  }
}

function formatTime(sec) {
  sec = Math.floor(sec || 0);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) {
    return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

function handleVolumeChange(val) {
  if (!State.ytPlayer || !State.isPlayerReady) return;
  State.ytPlayer.setVolume(val);
  const iconHigh = document.getElementById('icon-vol-high');
  const iconMute = document.getElementById('icon-vol-mute');
  if (val == 0) {
    if (iconHigh) iconHigh.classList.add('hidden');
    if (iconMute) iconMute.classList.remove('hidden');
  } else {
    if (iconHigh) iconHigh.classList.remove('hidden');
    if (iconMute) iconMute.classList.add('hidden');
  }
}

function toggleMute() {
  if (!State.ytPlayer || !State.isPlayerReady) return;
  const iconHigh = document.getElementById('icon-vol-high');
  const iconMute = document.getElementById('icon-vol-mute');
  const slider = document.getElementById('volume-slider');

  if (State.ytPlayer.isMuted()) {
    State.ytPlayer.unMute();
    if (iconHigh) iconHigh.classList.remove('hidden');
    if (iconMute) iconMute.classList.add('hidden');
    if (slider) slider.value = State.ytPlayer.getVolume() || 100;
  } else {
    State.ytPlayer.mute();
    if (iconHigh) iconHigh.classList.add('hidden');
    if (iconMute) iconMute.classList.remove('hidden');
    if (slider) slider.value = 0;
  }
}

function setSpeed(speed) {
  if (!State.ytPlayer || !State.isPlayerReady) return;
  State.ytPlayer.setPlaybackRate(speed);
  State.playbackSpeed = speed;
  const label = document.getElementById('speed-label');
  if (label) label.textContent = `${speed}x`;

  const popup = document.getElementById('speed-popup');
  if (popup) {
    popup.querySelectorAll('.menu-item').forEach(el => {
      el.classList.toggle('active', el.textContent.startsWith(`${speed}x`));
    });
    popup.classList.remove('show');
  }
  showToast(`Playback Speed: ${speed}x`);
}

function setQuality(quality) {
  if (!State.ytPlayer || !State.isPlayerReady) return;
  if (quality === 'auto') {
    if (typeof State.ytPlayer.setPlaybackQuality === 'function') {
      State.ytPlayer.setPlaybackQuality('default');
    }
    State.selectedQuality = 'auto';
    showToast('Resolution Quality: Auto (Adaptive)');
  } else {
    if (typeof State.ytPlayer.setPlaybackQuality === 'function') {
      State.ytPlayer.setPlaybackQuality(quality);
    }
    State.selectedQuality = quality;
    const label = QUALITY_MAP[quality]?.label || quality.toUpperCase();
    showToast(`Resolution Quality: ${label}`);
  }

  renderQualityMenu(State.availableQualities);
  const popup = document.getElementById('quality-popup');
  if (popup) popup.classList.remove('show');
}

function detectCaptionTracks() {
  const btn = document.getElementById('btn-captions');
  if (!State.ytPlayer || !State.isPlayerReady) {
    if (btn) btn.classList.add('hidden');
    return;
  }

  let tracks = [];
  try {
    if (typeof State.ytPlayer.getOption === 'function') {
      tracks = State.ytPlayer.getOption('captions', 'tracklist') || State.ytPlayer.getOption('cc', 'tracklist') || [];
    }
  } catch (e) {
    tracks = [];
  }

  if (Array.isArray(tracks) && tracks.length > 0) {
    State.hasCaptions = true;
    State.captionTracks = tracks;
    if (btn) btn.classList.remove('hidden');
    renderCaptionsMenu(tracks);
  } else {
    State.hasCaptions = false;
    State.captionTracks = [];
    if (btn) btn.classList.add('hidden');
    const popup = document.getElementById('captions-popup');
    if (popup) popup.classList.remove('show');
  }
}

function renderCaptionsMenu(tracks) {
  const listEl = document.getElementById('captions-options-list');
  if (!listEl) return;
  let html = `<div class="menu-item ${!State.captionsEnabled ? 'active' : ''}" onclick="setCaptionTrack(null)">Off</div>`;
  if (Array.isArray(tracks)) {
    tracks.forEach((track, idx) => {
      const label = track.displayName || track.name || track.languageCode || `Track ${idx + 1}`;
      const isActive = State.captionsEnabled && State.selectedCaptionTrack && (State.selectedCaptionTrack.languageCode === track.languageCode);
      const trackParam = JSON.stringify(track).replace(/"/g, '&quot;');
      html += `<div class="menu-item ${isActive ? 'active' : ''}" onclick="setCaptionTrack(${trackParam})">${escapeHtml(label)}</div>`;
    });
  }
  listEl.innerHTML = html;
}

function toggleCaptions() {
  if (!State.hasCaptions || State.captionTracks.length === 0) return;
  const popup = document.getElementById('captions-popup');

  if (State.captionTracks.length === 1) {
    if (State.captionsEnabled) {
      setCaptionTrack(null);
    } else {
      setCaptionTrack(State.captionTracks[0]);
    }
  } else {
    if (popup) popup.classList.toggle('show');
    const qPopup = document.getElementById('quality-popup');
    if (qPopup) qPopup.classList.remove('show');
    const sPopup = document.getElementById('speed-popup');
    if (sPopup) sPopup.classList.remove('show');
  }
}

function setCaptionTrack(track) {
  const btn = document.getElementById('btn-captions');
  const popup = document.getElementById('captions-popup');
  if (popup) popup.classList.remove('show');

  if (!track) {
    State.captionsEnabled = false;
    State.selectedCaptionTrack = null;
    try {
      if (State.ytPlayer && typeof State.ytPlayer.setOption === 'function') {
        State.ytPlayer.setOption('captions', 'track', {});
      }
      if (State.ytPlayer && typeof State.ytPlayer.unloadModule === 'function') {
        State.ytPlayer.unloadModule('captions');
      }
    } catch (e) {}
    if (btn) btn.classList.remove('active');
    showToast('Captions: Off');
  } else {
    State.captionsEnabled = true;
    State.selectedCaptionTrack = track;
    try {
      if (State.ytPlayer && typeof State.ytPlayer.loadModule === 'function') {
        State.ytPlayer.loadModule('captions');
      }
      if (State.ytPlayer && typeof State.ytPlayer.setOption === 'function') {
        State.ytPlayer.setOption('captions', 'track', {
          languageCode: track.languageCode,
          name: track.name || ''
        });
      }
    } catch (e) {}
    if (btn) btn.classList.add('active');
    const label = track.displayName || track.name || track.languageCode || 'On';
    showToast(`Captions: ${label}`);
  }
  renderCaptionsMenu(State.captionTracks);
}

function toggleSpeedMenu() {
  const popup = document.getElementById('speed-popup');
  if (popup) popup.classList.toggle('show');
  const qPopup = document.getElementById('quality-popup');
  if (qPopup) qPopup.classList.remove('show');
  const cPopup = document.getElementById('captions-popup');
  if (cPopup) cPopup.classList.remove('show');
}

function toggleQualityMenu() {
  const popup = document.getElementById('quality-popup');
  if (popup) popup.classList.toggle('show');
  const sPopup = document.getElementById('speed-popup');
  if (sPopup) sPopup.classList.remove('show');
  const cPopup = document.getElementById('captions-popup');
  if (cPopup) cPopup.classList.remove('show');
}

function toggleFullscreen() {
  const el = document.getElementById('custom-player-wrapper');
  if (!el) return;

  const iconEnter = document.getElementById('icon-fs-enter');
  const iconExit = document.getElementById('icon-fs-exit');

  if (!document.fullscreenElement && !document.webkitFullscreenElement) {
    if (el.requestFullscreen) {
      el.requestFullscreen();
    } else if (el.webkitRequestFullscreen) {
      el.webkitRequestFullscreen();
    }
    if (iconEnter) iconEnter.classList.add('hidden');
    if (iconExit) iconExit.classList.remove('hidden');
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
      document.webkitExitFullscreen();
    }
    if (iconEnter) iconEnter.classList.remove('hidden');
    if (iconExit) iconExit.classList.add('hidden');
  }
}

function showControls() {
  const bar = document.getElementById('player-controls-bar');
  if (bar) bar.classList.remove('fade-out');
  clearTimeout(State.controlsTimeout);
  if (State.isPlaying) {
    State.controlsTimeout = setTimeout(hideControls, 3000);
  }
}

function hideControls() {
  if (State.isPlaying) {
    const bar = document.getElementById('player-controls-bar');
    if (bar) bar.classList.add('fade-out');
    const sPopup = document.getElementById('speed-popup');
    if (sPopup) sPopup.classList.remove('show');
    const qPopup = document.getElementById('quality-popup');
    if (qPopup) qPopup.classList.remove('show');
    const cPopup = document.getElementById('captions-popup');
    if (cPopup) cPopup.classList.remove('show');
  }
}

function setupPlayerShortcuts() {
  document.onkeydown = (e) => {
    if (['input', 'textarea'].includes(e.target.tagName.toLowerCase())) return;
    switch (e.code) {
      case 'Space':
      case 'KeyK':
        e.preventDefault();
        togglePlayPause();
        break;
      case 'ArrowLeft':
      case 'KeyJ':
        e.preventDefault();
        seekRelative(-10);
        break;
      case 'ArrowRight':
      case 'KeyL':
        e.preventDefault();
        seekRelative(10);
        break;
      case 'KeyM':
        toggleMute();
        break;
      case 'KeyF':
        toggleFullscreen();
        break;
      case 'KeyC':
        if (State.hasCaptions) {
          toggleCaptions();
        }
        break;
      case 'ArrowUp':
        e.preventDefault();
        if (State.ytPlayer) {
          const v = Math.min(100, (State.ytPlayer.getVolume() || 100) + 5);
          handleVolumeChange(v);
          const s = document.getElementById('volume-slider');
          if (s) s.value = v;
        }
        break;
      case 'ArrowDown':
        e.preventDefault();
        if (State.ytPlayer) {
          const v = Math.max(0, (State.ytPlayer.getVolume() || 100) - 5);
          handleVolumeChange(v);
          const s = document.getElementById('volume-slider');
          if (s) s.value = v;
        }
        break;
    }
  };
}

// ==============================================================================
// 8. FAST PROGRESSIVE & CONTINUOUS SCROLL PDF.JS CANVAS VIEWER
// ==============================================================================

async function loadLecturePdf(lectureId) {
  const viewport = document.getElementById('pdf-viewport');
  if (!viewport) return;

  try {
    const resp = await fetch(`${API_BASE}/pdfs/${lectureId}/access`);
    if (!resp.ok) throw new Error('PDF access request failed');
    const data = await resp.json();

    const loadingTask = pdfjsLib.getDocument({
      url: data.access_url,
      withCredentials: false
    });

    State.activePdfDoc = await loadingTask.promise;
    State.totalPdfPages = State.activePdfDoc.numPages;
    State.currentPdfPage = 1;

    // Dynamically calculate initial scale based on real PDF page aspect ratio (16:9 landscape vs A4 portrait)
    try {
      const firstPage = await State.activePdfDoc.getPage(1);
      const unscaled = firstPage.getViewport({ scale: 1.0 });
      let availableWidth = viewport.clientWidth;
      if (!availableWidth || availableWidth <= 0) {
        const parentCard = document.querySelector('.lecture-player-card') || document.querySelector('.main-content');
        availableWidth = parentCard ? parentCard.clientWidth : window.innerWidth;
      }
      availableWidth = Math.max(280, availableWidth - 48);
      State.pdfScale = Math.min(2.5, Math.max(0.2, availableWidth / unscaled.width));
    } catch (scaleErr) {
      State.pdfScale = 1.0;
    }

    updatePdfPageIndicator();
    initPdfContinuousView(viewport);

  } catch (err) {
    console.error('PDF load error:', err);
    if (viewport) {
      viewport.innerHTML = `
        <div class="pdf-error-box">
          <p>⚠️ Unable to load verified study notes.</p>
          <button class="pdf-btn" style="margin-top: 12px; margin-inline: auto;" onclick="loadLecturePdf('${lectureId}')">Retry Access</button>
        </div>
      `;
    }
  }
}

function initPdfContinuousView(container) {
  if (!State.activePdfDoc) return;
  container.innerHTML = '';
  State.renderedPages.clear();

  // Create placeholders for all pages so scrollbar represents true document height
  for (let pageNum = 1; pageNum <= State.totalPdfPages; pageNum++) {
    const wrap = document.createElement('div');
    wrap.className = 'pdf-page-canvas-wrap';
    wrap.id = `pdf-page-wrap-${pageNum}`;
    wrap.dataset.pageNumber = pageNum;

    // Placeholder until rendered
    wrap.innerHTML = `
      <div class="pdf-page-placeholder">
        <div class="spinner-sm"></div>
        <span>Loading Page ${pageNum}...</span>
      </div>
    `;

    container.appendChild(wrap);
  }

  // Setup Lazy Rendering via IntersectionObserver
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const pageNum = parseInt(entry.target.dataset.pageNumber, 10);
        renderIndividualPdfPage(pageNum);
        State.currentPdfPage = pageNum;
        updatePdfPageIndicator();
      }
    });
  }, {
    root: container,
    rootMargin: '400px 0px 400px 0px'
  });

  document.querySelectorAll('.pdf-page-canvas-wrap').forEach(el => observer.observe(el));

  // Render Page 1 and 2 immediately
  renderIndividualPdfPage(1);
  if (State.totalPdfPages > 1) {
    renderIndividualPdfPage(2);
  }
}

async function renderIndividualPdfPage(pageNum) {
  if (!State.activePdfDoc || State.renderedPages.has(pageNum) || State.pdfRenderingQueue.has(pageNum)) return;

  const wrap = document.getElementById(`pdf-page-wrap-${pageNum}`);
  if (!wrap) return;

  State.pdfRenderingQueue.add(pageNum);

  try {
    const page = await State.activePdfDoc.getPage(pageNum);
    const dpr = window.devicePixelRatio || 1;
    // Scale viewport directly by (pdfScale * dpr) for pixel-perfect HiDPI canvas rendering without double transform clipping
    const viewport = page.getViewport({ scale: State.pdfScale * dpr });
    const cssWidth = Math.floor(viewport.width / dpr);
    const cssHeight = Math.floor(viewport.height / dpr);

    wrap.innerHTML = '';
    wrap.style.width = '100%';
    wrap.style.maxWidth = `${cssWidth}px`;
    wrap.style.minHeight = `${cssHeight}px`;

    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d', { alpha: false });
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = '100%';
    canvas.style.maxWidth = `${cssWidth}px`;
    canvas.style.height = 'auto';
    canvas.style.display = 'block';

    const renderContext = {
      canvasContext: context,
      viewport: viewport
    };

    await page.render(renderContext).promise;

    // Security Watermark Overlay
    const watermark = document.createElement('div');
    watermark.className = 'pdf-watermark-overlay';
    watermark.textContent = 'COURSE WALLAH — PERSONAL STUDY';

    const pageBadge = document.createElement('div');
    pageBadge.className = 'pdf-page-badge';
    pageBadge.textContent = `Page ${pageNum} of ${State.totalPdfPages}`;

    wrap.appendChild(canvas);
    wrap.appendChild(watermark);
    wrap.appendChild(pageBadge);

    State.renderedPages.add(pageNum);
  } catch (e) {
    console.error(`Page ${pageNum} render error:`, e);
  } finally {
    State.pdfRenderingQueue.delete(pageNum);
  }
}

function updatePdfPageIndicator() {
  const ind = document.getElementById('pdf-page-num');
  if (ind) ind.textContent = `Page ${State.currentPdfPage} / ${State.totalPdfPages}`;
}

function zoomPdf(delta) {
  State.pdfScale = Math.max(0.2, Math.min(3.0, State.pdfScale + delta));
  const viewport = document.getElementById('pdf-viewport');
  if (viewport && State.activePdfDoc) {
    initPdfContinuousView(viewport);
  }
}

async function fitPdfWidth() {
  const viewport = document.getElementById('pdf-viewport');
  if (viewport && State.activePdfDoc) {
    try {
      const page = await State.activePdfDoc.getPage(State.currentPdfPage || 1);
      const unscaled = page.getViewport({ scale: 1.0 });
      let availableWidth = viewport.clientWidth;
      if (!availableWidth || availableWidth <= 0) {
        const parentCard = document.querySelector('.lecture-player-card') || document.querySelector('.main-content');
        availableWidth = parentCard ? parentCard.clientWidth : window.innerWidth;
      }
      availableWidth = Math.max(280, availableWidth - 48);
      State.pdfScale = Math.min(2.5, Math.max(0.2, availableWidth / unscaled.width));
      initPdfContinuousView(viewport);
    } catch (e) {
      console.error('Fit width error:', e);
    }
  }
}

function changePdfPage(delta) {
  const target = Math.max(1, Math.min(State.totalPdfPages, State.currentPdfPage + delta));
  State.currentPdfPage = target;
  updatePdfPageIndicator();

  const el = document.getElementById(`pdf-page-wrap-${target}`);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

function togglePdfFullscreen() {
  const el = document.getElementById('pdf-viewer-wrapper');
  if (!el) return;
  if (!document.fullscreenElement) {
    if (el.requestFullscreen) {
      el.requestFullscreen().then(() => {
        setTimeout(() => fitPdfWidth(), 120);
      });
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen().then(() => {
        setTimeout(() => fitPdfWidth(), 120);
      });
    }
  }
}

// Global responsive auto-fit listener on window resize and fullscreen
let pdfResizeTimeout = null;
window.addEventListener('resize', () => {
  if (State.activePdfDoc && State.activeTab === 'notes') {
    clearTimeout(pdfResizeTimeout);
    pdfResizeTimeout = setTimeout(() => {
      fitPdfWidth();
    }, 150);
  }
});

document.addEventListener('fullscreenchange', () => {
  if (State.activePdfDoc && State.activeTab === 'notes') {
    setTimeout(() => fitPdfWidth(), 150);
  }
});

// ==============================================================================
// 9. GLOBAL SEARCH & BREADCRUMBS
// ==============================================================================

function setupGlobalSearch() {
  const input = document.getElementById('global-search-input');
  const dropdown = document.getElementById('search-results-dropdown');
  if (!input || !dropdown) return;

  input.addEventListener('input', (e) => {
    clearTimeout(State.searchDebounce);
    const query = e.target.value.trim();
    if (!query) {
      dropdown.classList.add('hidden');
      return;
    }
    State.searchDebounce = setTimeout(() => performSearch(query, dropdown), 250);
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.nav-search-wrapper')) {
      dropdown.classList.add('hidden');
    }
  });

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      input.focus();
    }
  });
}

async function performSearch(query, dropdown) {
  try {
    const resp = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`);
    if (!resp.ok) return;
    const data = await resp.json();

    const results = [];
    if (Array.isArray(data)) {
      results.push(...data);
    } else if (data && typeof data === 'object') {
      if (data.apps) {
        data.apps.forEach(a => results.push({ type: 'app', id: a.id, slug: a.slug, title: a.name, hierarchy: 'Educational Stream' }));
      }
      if (data.batches) {
        data.batches.forEach(b => results.push({ type: 'batch', id: b.id, slug: b.slug, title: b.name, hierarchy: b.category || 'Academic Batch' }));
      }
      if (data.lectures) {
        data.lectures.forEach(l => results.push({ type: 'lecture', id: l.id, title: l.title, hierarchy: `${l.batch_name || ''} • ${l.subject_name || ''}` }));
      }
    }

    if (results.length === 0) {
      dropdown.innerHTML = `<div style="padding: 16px; color: var(--text-muted); font-size: 0.85rem; text-align: center;">No matches found for "${escapeHtml(query)}"</div>`;
      dropdown.classList.remove('hidden');
      return;
    }

    dropdown.innerHTML = results.map(item => `
      <div class="search-item" onclick="handleSearchResultClick('${item.type}', '${item.slug || item.id}')">
        <div class="search-item-icon">
          ${item.type === 'app' ? '📚' : item.type === 'batch' ? '🎓' : item.type === 'subject' ? '📖' : '▶'}
        </div>
        <div class="search-item-info">
          <div class="search-item-title">${escapeHtml(item.title)}</div>
          <div class="search-item-hierarchy">${escapeHtml(item.hierarchy || item.type.toUpperCase())}</div>
        </div>
        <span class="search-item-badge">${item.type.toUpperCase()}</span>
      </div>
    `).join('');

    dropdown.classList.remove('hidden');
  } catch (err) {
    console.error('Search error:', err);
  }
}

function handleSearchResultClick(type, idOrSlug) {
  const dropdown = document.getElementById('search-results-dropdown');
  const input = document.getElementById('global-search-input');
  if (dropdown) dropdown.classList.add('hidden');
  if (input) input.value = '';

  if (type === 'app') navigateTo('app', idOrSlug);
  else if (type === 'batch') navigateTo('batch', idOrSlug);
  else if (type === 'lecture') navigateTo('lecture', idOrSlug);
  else navigateTo('home');
}

function setBreadcrumbs(items) {
  const bar = document.getElementById('breadcrumb-bar');
  const container = document.getElementById('breadcrumb-items');
  if (!bar || !container) return;

  if (!items || items.length === 0) {
    bar.classList.add('hidden');
    return;
  }

  bar.classList.remove('hidden');
  let html = `<span class="breadcrumb-item" onclick="navigateTo('home')">🏠 Home</span>`;
  items.forEach(it => {
    html += `<span class="breadcrumb-separator">/</span>`;
    if (it.active) {
      html += `<span class="breadcrumb-item active">${escapeHtml(it.label)}</span>`;
    } else {
      html += `<span class="breadcrumb-item" onclick="navigateTo('${it.route}')">${escapeHtml(it.label)}</span>`;
    }
  });
  container.innerHTML = html;
}

// ==============================================================================
// 10. UI SKELETONS & NOTIFICATIONS
// ==============================================================================

function renderSkeleton() {
  return `
    <div class="skeleton-grid">
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
    </div>
  `;
}

function renderErrorState(title, detail) {
  return `
    <div class="empty-state" style="border-color: rgba(244, 63, 94, 0.3);">
      <div class="empty-icon" style="color: var(--accent-rose);">⚠️</div>
      <h3 class="empty-title">${escapeHtml(title)}</h3>
      <p class="empty-desc">${escapeHtml(detail || 'An unexpected error occurred.')}</p>
      <button class="nav-btn" style="margin-top: 16px; margin-inline: auto;" onclick="navigateTo('home')">Return to Home</button>
    </div>
  `;
}

function showToast(msg) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 3200);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// ==============================================================================
// 11. ADMIN CONTROL CENTER (FULL MANAGEMENT SUITE)
// ==============================================================================

function getAdminAuthHeaders() {
  const token = localStorage.getItem('cw_admin_token') || '';
  return {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  };
}

async function renderAdminPortal(root, activeTab = 'overview') {
  setBreadcrumbs([
    { label: 'Control Center (Admin)', route: 'ragni/admin', active: true }
  ]);

  const token = localStorage.getItem('cw_admin_token');
  if (!token) {
    renderAdminLoginForm(root);
    return;
  }

  try {
    const statsResp = await fetch(`${API_BASE}/admin/stats`, {
      headers: getAdminAuthHeaders()
    });

    if (statsResp.status === 401 || statsResp.status === 403) {
      localStorage.removeItem('cw_admin_token');
      renderAdminLoginForm(root);
      return;
    }

    const stats = await statsResp.json();
    await renderAdminDashboard(root, stats, activeTab);
  } catch (err) {
    console.error('Admin portal load error:', err);
    renderAdminLoginForm(root);
  }
}

function renderAdminLoginForm(root) {
  root.innerHTML = `
    <div class="admin-login-wrapper">
      <div class="admin-login-card">
        <div class="admin-login-header">
          <div class="admin-shield-icon">
            <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
            </svg>
          </div>
          <h2 class="admin-login-title">Course Wallah Control Center</h2>
          <p class="admin-login-subtitle">Sign in to manage batches, student access, YouTube pool, and problem tickets.</p>
        </div>

        <form id="admin-login-form" onsubmit="handleAdminLogin(event)" class="admin-login-form">
          <div class="admin-form-group">
            <label class="admin-label">Administrator Username</label>
            <div class="admin-input-wrap">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              <input type="text" id="admin-user-input" required placeholder="admin" value="admin" autocomplete="username">
            </div>
          </div>

          <div class="admin-form-group">
            <label class="admin-label">Security Password</label>
            <div class="admin-input-wrap">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
              <input type="password" id="admin-pass-input" required placeholder="••••••••••••" value="CourseWallah@2026#Secure" autocomplete="current-password">
            </div>
          </div>

          <button type="submit" class="admin-submit-btn" id="btn-admin-submit">
            <span>Authenticate & Enter Dashboard</span>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"></path></svg>
          </button>
        </form>

        <div class="admin-login-footer">
          <span class="auth-hint-badge">🔒 AES-256 JWT Signed Session</span>
          <p class="auth-note">Credentials: <code>admin</code> / <code>CourseWallah@2026#Secure</code></p>
        </div>
      </div>
    </div>
  `;
}

async function handleAdminLogin(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-admin-submit');
  const user = document.getElementById('admin-user-input').value.trim();
  const pass = document.getElementById('admin-pass-input').value.trim();

  if (btn) btn.disabled = true;

  try {
    const resp = await fetch(`${API_BASE}/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    });

    if (!resp.ok) {
      throw new Error('Invalid username or password');
    }

    const data = await resp.json();
    localStorage.setItem('cw_admin_token', data.token);
    showToast('✨ Admin authentication successful!');
    navigateTo('ragni/admin');
  } catch (err) {
    showToast(`⚠️ Login failed: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

async function renderAdminDashboard(root, stats, activeTab = 'overview') {
  root.innerHTML = `
    <div class="admin-dashboard-container">
      
      <!-- Top Admin Header Bar -->
      <div class="admin-header-card">
        <div class="admin-header-info">
          <div class="admin-avatar-badge">⚡</div>
          <div>
            <div class="admin-header-tag-row">
              <span class="admin-badge-role">SUPER ADMIN</span>
              <span class="admin-live-pulse"><span class="pulse-dot"></span> Operations Live</span>
            </div>
            <h1 class="admin-dashboard-title">Platform Operations Center</h1>
          </div>
        </div>

        <div class="admin-header-actions">
          <button class="admin-secondary-btn" onclick="navigateTo('home')">← Student Portal</button>
          <button class="admin-danger-btn" onclick="handleAdminLogout()">🚪 Sign Out</button>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <div class="admin-nav-tabs">
        <button class="admin-tab-btn ${activeTab === 'overview' ? 'active' : ''}" onclick="switchAdminTab('overview')">
          <span>📊 Overview & Stats</span>
        </button>
        <button class="admin-tab-btn ${activeTab === 'batches' ? 'active' : ''}" onclick="switchAdminTab('batches')">
          <span>📚 Batches & Thumbnails</span>
        </button>
        <button class="admin-tab-btn ${activeTab === 'students' ? 'active' : ''}" onclick="switchAdminTab('students')">
          <span>👥 Students & Enrollments</span>
        </button>
        <button class="admin-tab-btn ${activeTab === 'support' ? 'active' : ''}" onclick="switchAdminTab('support')">
          <span>🛠️ Student Problems & Tickets</span>
        </button>
        <button class="admin-tab-btn ${activeTab === 'youtube' ? 'active' : ''}" onclick="switchAdminTab('youtube')">
          <span>🎬 YouTube Multi-Account Pool</span>
        </button>
        <button class="admin-tab-btn ${activeTab === 'jobs' ? 'active' : ''}" onclick="switchAdminTab('jobs')">
          <span>⚡ Live Jobs & Queues</span>
        </button>
        <button class="admin-tab-btn ${activeTab === 'watermark' ? 'active' : ''}" onclick="switchAdminTab('watermark')">
          <span>🎨 Watermark & DRM</span>
        </button>
      </div>

      <!-- Tab Content Area -->
      <div class="admin-tab-content" id="admin-tab-content">
        <div class="spinner-center"><div class="spinner"></div></div>
      </div>

      <!-- Dynamic Admin Modal Container -->
      <div id="admin-modal-container" class="admin-modal-overlay hidden"></div>

    </div>
  `;

  await loadAdminTabContent(activeTab, stats);
}

function handleAdminLogout() {
  localStorage.removeItem('cw_admin_token');
  showToast('Logged out of Admin Control Center');
  navigateTo('home');
}

function switchAdminTab(tabName) {
  navigateTo('ragni/admin', tabName);
}

async function loadAdminTabContent(tabName, stats) {
  const container = document.getElementById('admin-tab-content');
  if (!container) return;

  try {
    switch (tabName) {
      case 'overview':
        await renderAdminOverviewTab(container, stats);
        break;
      case 'batches':
        await renderAdminBatchesTab(container);
        break;
      case 'students':
        await renderAdminStudentsTab(container);
        break;
      case 'support':
        await renderAdminSupportTab(container);
        break;
      case 'youtube':
        await renderAdminYouTubeTab(container);
        break;
      case 'jobs':
        await renderAdminJobsTab(container);
        break;
      case 'watermark':
        await renderAdminWatermarkTab(container);
        break;
      default:
        await renderAdminOverviewTab(container, stats);
    }
  } catch (err) {
    console.error('Tab render error:', err);
    container.innerHTML = `<div class="empty-state"><p>⚠️ Error loading tab: ${escapeHtml(err.message)}</p></div>`;
  }
}

// ==============================================================================
// MODAL HELPERS
// ==============================================================================

function closeAdminModal() {
  const modal = document.getElementById('admin-modal-container');
  if (modal) {
    modal.classList.add('hidden');
    modal.innerHTML = '';
  }
}

function openAdminModal(contentHtml) {
  const modal = document.getElementById('admin-modal-container');
  if (!modal) return;
  modal.innerHTML = `
    <div class="admin-modal-box">
      <button class="modal-close-x" onclick="closeAdminModal()">✕</button>
      ${contentHtml}
    </div>
  `;
  modal.classList.remove('hidden');
}

// ==============================================================================
// TAB 1: OVERVIEW & STATS
// ==============================================================================

async function renderAdminOverviewTab(container, stats) {
  container.innerHTML = `
    <div class="admin-stats-grid">
      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(56, 189, 248, 0.15); color: var(--accent-cyan);">📱</div>
        <div class="stat-meta">
          <span class="stat-label">Total Course Apps</span>
          <span class="stat-value">${stats.apps}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(129, 140, 248, 0.15); color: var(--accent-indigo);">📦</div>
        <div class="stat-meta">
          <span class="stat-label">Active Batches</span>
          <span class="stat-value">${stats.batches}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(16, 185, 129, 0.15); color: #10b981;">📖</div>
        <div class="stat-meta">
          <span class="stat-label">Total Lectures</span>
          <span class="stat-value">${stats.lectures}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(234, 179, 8, 0.15); color: #eab308;">🚀</div>
        <div class="stat-meta">
          <span class="stat-label">Published Lectures</span>
          <span class="stat-value">${stats.published_lectures}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(244, 63, 94, 0.15); color: var(--accent-rose);">🎥</div>
        <div class="stat-meta">
          <span class="stat-label">YouTube Videos</span>
          <span class="stat-value">${stats.videos}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(168, 85, 247, 0.15); color: #a855f7;">📄</div>
        <div class="stat-meta">
          <span class="stat-label">Encrypted B2 PDFs</span>
          <span class="stat-value">${stats.pdfs}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(56, 189, 248, 0.15); color: var(--accent-cyan);">⚡</div>
        <div class="stat-meta">
          <span class="stat-label">Active Ingestion Jobs</span>
          <span class="stat-value">${stats.active_jobs}</span>
        </div>
      </div>

      <div class="admin-stat-card">
        <div class="stat-icon-wrap" style="background: rgba(239, 68, 68, 0.15); color: #ef4444;">⚠️</div>
        <div class="stat-meta">
          <span class="stat-label">Failed Ingestion Jobs</span>
          <span class="stat-value">${stats.failed_jobs}</span>
        </div>
      </div>
    </div>

    <div class="admin-quick-links-card">
      <h3 class="admin-section-subtitle">Management Shortcuts</h3>
      <div class="admin-shortcuts-row">
        <button class="admin-action-btn" onclick="openAddBatchModal()">➕ Add New Batch</button>
        <button class="admin-action-btn" onclick="openAddStudentModal()">👤 Add Student to Batch</button>
        <button class="admin-action-btn" onclick="openNewTicketModal()">🛠️ Log Student Problem</button>
        <button class="admin-action-btn" onclick="switchAdminTab('youtube')">🎬 Manage YouTube Quotas</button>
        <button class="admin-action-btn" onclick="switchAdminTab('watermark')">🎨 Watermark Settings</button>
      </div>
    </div>
  `;
}

// ==============================================================================
// TAB 2: BATCHES & THUMBNAILS (ADD, EDIT, THUMBNAIL, STATUS)
// ==============================================================================

async function renderAdminBatchesTab(container) {
  container.innerHTML = `<div class="spinner-center"><div class="spinner"></div></div>`;

  const resp = await fetch(`${API_BASE}/admin/batches`, { headers: getAdminAuthHeaders() });
  if (!resp.ok) throw new Error('Failed to fetch batches');
  const batches = await resp.json();

  container.innerHTML = `
    <div class="admin-toolbar-row">
      <div>
        <h3 class="admin-section-title">Course Batches & Publishing</h3>
        <p class="admin-section-desc">Create new batches, edit metadata, update thumbnail cards, toggle publication, and manage lecture streams.</p>
      </div>
      <button class="admin-success-btn" onclick="openAddBatchModal()">➕ Add New Batch</button>
    </div>

    <div class="admin-batches-list">
      ${batches.map(b => `
        <div class="admin-batch-row-card" id="batch-card-${b.id}">
          <div class="batch-card-main-grid">
            <div class="batch-thumb-preview">
              ${b.thumbnail_url ? `<img src="${escapeHtml(b.thumbnail_url)}" alt="thumb" class="b-thumb-img" onerror="this.src='/static/logo.png'">` : `<div class="b-thumb-ph">📦</div>`}
            </div>
            <div class="batch-info-block">
              <div class="b-tag-row">
                <span class="admin-badge-role">${escapeHtml(b.app_name)}</span>
                <span class="badge-tag tag-cyan">${escapeHtml(b.category || 'Semester')}</span>
                <span class="admin-badge-status ${b.status === 'ACTIVE' ? 'active' : 'muted'}">${b.status}</span>
              </div>
              <h4 class="b-title">${escapeHtml(b.name)}</h4>
              <p class="b-meta-line">${escapeHtml(b.branch || 'General')} • ${escapeHtml(b.semester || 'Semester')} • Year: ${escapeHtml(b.academic_year || '2026')} • <strong>${b.subject_count || 0} Subjects</strong></p>
            </div>
            <div class="batch-actions-block">
              <button class="admin-sm-btn" onclick="openEditBatchModal('${b.id}', '${escapeHtml(b.name).replace(/'/g, "\\'")}', '${escapeHtml(b.category || '')}', '${escapeHtml(b.branch || '')}', '${escapeHtml(b.semester || '')}', '${escapeHtml(b.academic_year || '')}', '${b.status}')">✏️ Edit</button>
              <button class="admin-sm-btn" onclick="openUpdateThumbModal('${b.id}', '${escapeHtml(b.thumbnail_url || '')}')">🖼️ Thumbnail</button>
              <button class="admin-sm-btn" onclick="toggleBatchStatus('${b.id}', '${b.status}')">🔄 ${b.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}</button>
              <button class="admin-sm-btn" onclick="toggleBatchLecturesView('${b.id}', '${b.slug}')">📂 Lectures ▾</button>
              <button class="admin-sm-btn btn-del" onclick="deleteBatch('${b.id}', '${escapeHtml(b.name).replace(/'/g, "\\'")}')">🗑️</button>
            </div>
          </div>

          <!-- Collapsible Lectures List -->
          <div class="batch-lectures-drawer hidden" id="lectures-drawer-${b.id}">
            <div class="spinner-center"><div class="spinner-sm"></div></div>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function openAddBatchModal() {
  openAdminModal(`
    <h3 class="modal-title">➕ Add New Course Batch</h3>
    <p class="modal-subtitle">Create a new batch container to organize subjects, video lectures, and PDF study notes.</p>
    
    <form onsubmit="submitAddBatch(event)" class="admin-login-form">
      <div class="admin-form-group">
        <label class="admin-label">Batch Title / Name *</label>
        <div class="admin-input-wrap">
          <input type="text" id="add-b-name" required placeholder="e.g. 5th Sem Electronics & Communication">
        </div>
      </div>

      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Category / Stream</label>
          <div class="admin-input-wrap">
            <input type="text" id="add-b-cat" placeholder="e.g. Polytechnic / B.Tech" value="Polytechnic">
          </div>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Branch</label>
          <div class="admin-input-wrap">
            <input type="text" id="add-b-branch" placeholder="e.g. Electronics / Civil" value="Electronics">
          </div>
        </div>
      </div>

      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Semester</label>
          <div class="admin-input-wrap">
            <input type="text" id="add-b-sem" placeholder="e.g. 5th Semester" value="5th Semester">
          </div>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Academic Year</label>
          <div class="admin-input-wrap">
            <input type="text" id="add-b-year" placeholder="2026" value="2026">
          </div>
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Thumbnail Image URL</label>
        <div class="admin-input-wrap">
          <input type="url" id="add-b-thumb" placeholder="https://example.com/banner.jpg" oninput="previewModalThumb(this.value)">
        </div>
        <div id="modal-thumb-preview" class="thumb-preview-box hidden"></div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Initial Status</label>
        <select id="add-b-status" class="admin-select">
          <option value="ACTIVE" selected>ACTIVE (Visible to students)</option>
          <option value="DRAFT">DRAFT (Hidden)</option>
        </select>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-success-btn" id="btn-submit-add-b">Create Batch</button>
      </div>
    </form>
  `);
}

function previewModalThumb(url) {
  const prev = document.getElementById('modal-thumb-preview');
  if (!prev) return;
  if (url && url.startsWith('http')) {
    prev.innerHTML = `<img src="${escapeHtml(url)}" alt="preview" style="max-height: 120px; border-radius: 6px; margin-top: 8px;">`;
    prev.classList.remove('hidden');
  } else {
    prev.classList.add('hidden');
  }
}

async function submitAddBatch(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-add-b');
  if (btn) btn.disabled = true;

  const payload = {
    name: document.getElementById('add-b-name').value.trim(),
    category: document.getElementById('add-b-cat').value.trim(),
    branch: document.getElementById('add-b-branch').value.trim(),
    semester: document.getElementById('add-b-sem').value.trim(),
    academic_year: document.getElementById('add-b-year').value.trim(),
    thumbnail_url: document.getElementById('add-b-thumb').value.trim() || null,
    status: document.getElementById('add-b-status').value
  };

  try {
    const resp = await fetch(`${API_BASE}/admin/batches`, {
      method: 'POST',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (!resp.ok) throw new Error('Failed to create batch');
    showToast('✨ Batch created successfully!');
    closeAdminModal();
    await renderAdminBatchesTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

function openEditBatchModal(batchId, name, cat, branch, sem, year, status) {
  openAdminModal(`
    <h3 class="modal-title">✏️ Edit Batch Details</h3>
    <p class="modal-subtitle">Update batch name, semester, branch, and status.</p>
    
    <form onsubmit="submitEditBatch(event, '${batchId}')" class="admin-login-form">
      <div class="admin-form-group">
        <label class="admin-label">Batch Title *</label>
        <div class="admin-input-wrap">
          <input type="text" id="edit-b-name" required value="${escapeHtml(name)}">
        </div>
      </div>

      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Category</label>
          <div class="admin-input-wrap">
            <input type="text" id="edit-b-cat" value="${escapeHtml(cat)}">
          </div>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Branch</label>
          <div class="admin-input-wrap">
            <input type="text" id="edit-b-branch" value="${escapeHtml(branch)}">
          </div>
        </div>
      </div>

      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Semester</label>
          <div class="admin-input-wrap">
            <input type="text" id="edit-b-sem" value="${escapeHtml(sem)}">
          </div>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Year</label>
          <div class="admin-input-wrap">
            <input type="text" id="edit-b-year" value="${escapeHtml(year)}">
          </div>
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Status</label>
        <select id="edit-b-status" class="admin-select">
          <option value="ACTIVE" ${status === 'ACTIVE' ? 'selected' : ''}>ACTIVE</option>
          <option value="DRAFT" ${status === 'DRAFT' ? 'selected' : ''}>DRAFT</option>
          <option value="ARCHIVED" ${status === 'ARCHIVED' ? 'selected' : ''}>ARCHIVED</option>
        </select>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-action-btn" id="btn-submit-edit-b">Save Changes</button>
      </div>
    </form>
  `);
}

async function submitEditBatch(e, batchId) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-edit-b');
  if (btn) btn.disabled = true;

  const payload = {
    name: document.getElementById('edit-b-name').value.trim(),
    category: document.getElementById('edit-b-cat').value.trim(),
    branch: document.getElementById('edit-b-branch').value.trim(),
    semester: document.getElementById('edit-b-sem').value.trim(),
    academic_year: document.getElementById('edit-b-year').value.trim(),
    status: document.getElementById('edit-b-status').value
  };

  try {
    const resp = await fetch(`${API_BASE}/admin/batches/${batchId}`, {
      method: 'PUT',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (!resp.ok) throw new Error('Update failed');
    showToast('✨ Batch updated successfully!');
    closeAdminModal();
    await renderAdminBatchesTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

function openUpdateThumbModal(batchId, currentThumb) {
  openAdminModal(`
    <h3 class="modal-title">🖼️ Update Batch Thumbnail</h3>
    <p class="modal-subtitle">Paste a direct image URL (JPG, PNG, WebP) to display as the batch cover card.</p>
    
    <form onsubmit="submitUpdateThumb(event, '${batchId}')" class="admin-login-form">
      <div class="admin-form-group">
        <label class="admin-label">Thumbnail URL *</label>
        <div class="admin-input-wrap">
          <input type="url" id="thumb-url-input" required placeholder="https://example.com/banner.jpg" value="${escapeHtml(currentThumb)}" oninput="previewModalThumb(this.value)">
        </div>
        <div id="modal-thumb-preview" class="thumb-preview-box ${currentThumb ? '' : 'hidden'}">
          ${currentThumb ? `<img src="${escapeHtml(currentThumb)}" alt="preview" style="max-height: 140px; border-radius: 8px; margin-top: 10px;">` : ''}
        </div>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-action-btn" id="btn-submit-thumb">Update Thumbnail</button>
      </div>
    </form>
  `);
}

async function submitUpdateThumb(e, batchId) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-thumb');
  if (btn) btn.disabled = true;

  const url = document.getElementById('thumb-url-input').value.trim();

  try {
    const resp = await fetch(`${API_BASE}/admin/batches/${batchId}`, {
      method: 'PUT',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify({ thumbnail_url: url })
    });
    if (!resp.ok) throw new Error('Failed to update thumbnail');
    showToast('✨ Thumbnail updated successfully!');
    closeAdminModal();
    await renderAdminBatchesTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

async function toggleBatchStatus(batchId, currentStatus) {
  const newStatus = currentStatus === 'ACTIVE' ? 'DRAFT' : 'ACTIVE';
  try {
    const resp = await fetch(`${API_BASE}/admin/batches/${batchId}`, {
      method: 'PUT',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify({ status: newStatus })
    });
    if (!resp.ok) throw new Error('Failed to toggle status');
    showToast(`Batch status set to: ${newStatus}`);
    await renderAdminBatchesTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

async function deleteBatch(batchId, name) {
  if (!confirm(`Are you sure you want to delete batch "${name}"? All nested subjects and lectures will be deleted.`)) return;
  try {
    const resp = await fetch(`${API_BASE}/admin/batches/${batchId}`, {
      method: 'DELETE',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Delete failed');
    showToast(`Batch "${name}" deleted`);
    await renderAdminBatchesTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

// ==============================================================================
// TAB 3: STUDENTS & BATCH ENROLLMENTS
// ==============================================================================

async function renderAdminStudentsTab(container) {
  container.innerHTML = `<div class="spinner-center"><div class="spinner"></div></div>`;

  const resp = await fetch(`${API_BASE}/admin/students`, { headers: getAdminAuthHeaders() });
  if (!resp.ok) throw new Error('Failed to fetch students');
  const students = await resp.json();

  container.innerHTML = `
    <div class="admin-toolbar-row">
      <div>
        <h3 class="admin-section-title">Student Management & Batch Access</h3>
        <p class="admin-section-desc">Add new students, assign batches, revoke or extend access, and manage student account statuses.</p>
      </div>
      <button class="admin-success-btn" onclick="openAddStudentModal()">👤 Add New Student</button>
    </div>

    ${students.length > 0 ? `
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>Student Name</th>
              <th>Email / Phone</th>
              <th>Status</th>
              <th>Enrolled Batches</th>
              <th>Joined Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${students.map(s => `
              <tr>
                <td><strong>${escapeHtml(s.name)}</strong></td>
                <td><code>${escapeHtml(s.email)}</code></td>
                <td>
                  <span class="admin-badge-status ${s.status === 'ACTIVE' ? 'active' : 'danger'}">${s.status}</span>
                </td>
                <td>
                  <div class="enrolled-badges-wrap">
                    ${(s.enrolled_batches && s.enrolled_batches.length > 0) ? s.enrolled_batches.map(eb => `
                      <span class="batch-chip">
                        ${escapeHtml(eb.batch_name)}
                        <span class="chip-del-x" title="Remove Access" onclick="unenrollStudentFromBatch('${s.id}', '${eb.batch_id}', '${escapeHtml(eb.batch_name).replace(/'/g, "\\'")}')">✕</span>
                      </span>
                    `).join('') : `<span class="badge-tag tag-muted">No Batches</span>`}
                  </div>
                </td>
                <td style="font-size: 0.78rem; color: var(--text-muted);">
                  ${s.created_at ? new Date(s.created_at).toLocaleDateString() : '—'}
                </td>
                <td>
                  <button class="admin-sm-btn" onclick="openEnrollStudentModal('${s.id}', '${escapeHtml(s.name).replace(/'/g, "\\'")}')">➕ Assign Batch</button>
                  <button class="admin-sm-btn" onclick="toggleStudentStatus('${s.id}', '${s.status}')">
                    ${s.status === 'ACTIVE' ? '🚫 Suspend' : '✅ Activate'}
                  </button>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    ` : `
      <div class="admin-empty-box">
        <span style="font-size: 1.5rem;">👥</span>
        <p>No students registered yet. Click "Add New Student" to enroll your first student.</p>
      </div>
    `}
  `;
}

async function openAddStudentModal() {
  const resp = await fetch(`${API_BASE}/admin/batches`, { headers: getAdminAuthHeaders() });
  const batches = resp.ok ? await resp.json() : [];

  openAdminModal(`
    <h3 class="modal-title">👤 Add New Student</h3>
    <p class="modal-subtitle">Enter student details and optionally grant access to a course batch.</p>
    
    <form onsubmit="submitAddStudent(event)" class="admin-login-form">
      <div class="admin-form-group">
        <label class="admin-label">Student Full Name *</label>
        <div class="admin-input-wrap">
          <input type="text" id="std-name-input" required placeholder="e.g. Rahul Sharma">
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Student Phone / Email *</label>
        <div class="admin-input-wrap">
          <input type="text" id="std-email-input" required placeholder="e.g. 9876543210 or student@gmail.com">
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Initial Batch Enrollment</label>
        <select id="std-batch-select" class="admin-select">
          <option value="">-- No Initial Batch (Grant Later) --</option>
          ${batches.map(b => `<option value="${b.id}">${escapeHtml(b.name)} (${escapeHtml(b.branch || 'General')})</option>`).join('')}
        </select>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-success-btn" id="btn-submit-std">Add Student</button>
      </div>
    </form>
  `);
}

async function submitAddStudent(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-std');
  if (btn) btn.disabled = true;

  const payload = {
    name: document.getElementById('std-name-input').value.trim(),
    email: document.getElementById('std-email-input').value.trim(),
    batch_id: document.getElementById('std-batch-select').value || null
  };

  try {
    const resp = await fetch(`${API_BASE}/admin/students`, {
      method: 'POST',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (!resp.ok) throw new Error('Failed to create student');
    showToast('✨ Student added successfully!');
    closeAdminModal();
    await renderAdminStudentsTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

async function openEnrollStudentModal(studentId, studentName) {
  const resp = await fetch(`${API_BASE}/admin/batches`, { headers: getAdminAuthHeaders() });
  const batches = resp.ok ? await resp.json() : [];

  openAdminModal(`
    <h3 class="modal-title">➕ Assign Batch to Student</h3>
    <p class="modal-subtitle">Grant <strong>${escapeHtml(studentName)}</strong> access to a course batch.</p>
    
    <form onsubmit="submitEnrollStudent(event, '${studentId}')" class="admin-login-form">
      <div class="admin-form-group">
        <label class="admin-label">Select Batch *</label>
        <select id="enroll-batch-select" class="admin-select" required>
          ${batches.map(b => `<option value="${b.id}">${escapeHtml(b.name)} (${escapeHtml(b.branch || 'General')})</option>`).join('')}
        </select>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-action-btn" id="btn-submit-enroll">Grant Access</button>
      </div>
    </form>
  `);
}

async function submitEnrollStudent(e, studentId) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-enroll');
  if (btn) btn.disabled = true;

  const batchId = document.getElementById('enroll-batch-select').value;

  try {
    const resp = await fetch(`${API_BASE}/admin/students/${studentId}/enroll`, {
      method: 'POST',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify({ batch_id: batchId })
    });
    if (!resp.ok) throw new Error('Enrollment failed');
    showToast('✨ Access granted to student!');
    closeAdminModal();
    await renderAdminStudentsTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

async function unenrollStudentFromBatch(studentId, batchId, batchName) {
  if (!confirm(`Revoke access to "${batchName}" for this student?`)) return;
  try {
    const resp = await fetch(`${API_BASE}/admin/students/${studentId}/batches/${batchId}`, {
      method: 'DELETE',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Failed to revoke access');
    showToast('Batch access revoked');
    await renderAdminStudentsTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

async function toggleStudentStatus(studentId, currentStatus) {
  const newStatus = currentStatus === 'ACTIVE' ? 'SUSPENDED' : 'ACTIVE';
  try {
    const resp = await fetch(`${API_BASE}/admin/students/${studentId}/status`, {
      method: 'PUT',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify({ status: newStatus })
    });
    if (!resp.ok) throw new Error('Failed to update status');
    showToast(`Student status updated to ${newStatus}`);
    await renderAdminStudentsTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

// ==============================================================================
// TAB 4: STUDENT PROBLEMS & SUPPORT DESK
// ==============================================================================

async function renderAdminSupportTab(container) {
  container.innerHTML = `<div class="spinner-center"><div class="spinner"></div></div>`;

  const resp = await fetch(`${API_BASE}/admin/tickets`, { headers: getAdminAuthHeaders() });
  if (!resp.ok) throw new Error('Failed to fetch support tickets');
  const tickets = await resp.json();

  container.innerHTML = `
    <div class="admin-toolbar-row">
      <div>
        <h3 class="admin-section-title">Student Problems & Support Desk</h3>
        <p class="admin-section-desc">Track student playback issues, PDF notes access problems, batch enrollment questions, and log resolution notes.</p>
      </div>
      <button class="admin-action-btn" onclick="openNewTicketModal()">🛠️ Log Student Problem</button>
    </div>

    ${tickets.length > 0 ? `
      <div class="admin-tickets-grid">
        ${tickets.map(t => `
          <div class="ticket-card ${t.status === 'RESOLVED' ? 'ticket-resolved' : ''}">
            <div class="ticket-top-row">
              <div class="ticket-cat-badge">${escapeHtml(t.category)}</div>
              <span class="admin-badge-status ${t.status === 'RESOLVED' ? 'active' : (t.status === 'IN_PROGRESS' ? 'warning' : 'danger')}">${t.status}</span>
            </div>

            <h4 class="ticket-subject">${escapeHtml(t.subject)}</h4>
            <p class="ticket-desc">${escapeHtml(t.description)}</p>

            <div class="ticket-meta-box">
              <p><span>Student:</span> <strong>${escapeHtml(t.student_name)}</strong> (<code>${escapeHtml(t.student_contact)}</code>)</p>
              <p><span>Batch:</span> ${escapeHtml(t.batch_name || 'General')}</p>
              <p><span>Priority:</span> <strong style="color: ${t.priority === 'URGENT' ? '#ef4444' : '#38bdf8'};">${t.priority}</strong></p>
              ${t.admin_note ? `<p class="ticket-note"><span>Admin Note:</span> ${escapeHtml(t.admin_note)}</p>` : ''}
            </div>

            <div class="ticket-footer-row">
              <span class="ticket-time">${t.created_at ? new Date(t.created_at).toLocaleString() : 'Recent'}</span>
              <div class="ticket-btn-group">
                <button class="admin-sm-btn" onclick="openUpdateTicketModal('${t.id}', '${t.status}', '${escapeHtml(t.admin_note || '').replace(/'/g, "\\'")}', '${t.priority}')">✏️ Resolve / Note</button>
                <button class="admin-sm-btn btn-del" onclick="deleteTicket('${t.id}')">🗑️</button>
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    ` : `
      <div class="admin-empty-box">
        <span style="font-size: 1.5rem;">🎉</span>
        <p>No open student problems or tickets! Everything is running smoothly.</p>
      </div>
    `}
  `;
}

async function openNewTicketModal() {
  const resp = await fetch(`${API_BASE}/admin/batches`, { headers: getAdminAuthHeaders() });
  const batches = resp.ok ? await resp.json() : [];

  openAdminModal(`
    <h3 class="modal-title">🛠️ Log Student Problem / Inquiry</h3>
    <p class="modal-subtitle">Create a support ticket to track and resolve a student issue.</p>
    
    <form onsubmit="submitNewTicket(event)" class="admin-login-form">
      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Student Name *</label>
          <div class="admin-input-wrap">
            <input type="text" id="t-name" required placeholder="e.g. Amit Kumar">
          </div>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Contact (Phone / Email) *</label>
          <div class="admin-input-wrap">
            <input type="text" id="t-contact" required placeholder="e.g. 9155563777">
          </div>
        </div>
      </div>

      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Issue Category</label>
          <select id="t-cat" class="admin-select">
            <option value="ACCESS_ISSUE">Batch Access Issue</option>
            <option value="VIDEO_PLAYBACK">Video Streaming / Playback Problem</option>
            <option value="PDF_NOTES">PDF / Study Notes Issue</option>
            <option value="PAYMENT">Payment / Verification</option>
            <option value="GENERAL">General Query</option>
          </select>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Priority</label>
          <select id="t-priority" class="admin-select">
            <option value="MEDIUM" selected>MEDIUM</option>
            <option value="HIGH">HIGH</option>
            <option value="URGENT">URGENT</option>
            <option value="LOW">LOW</option>
          </select>
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Related Batch</label>
        <select id="t-batch" class="admin-select">
          <option value="">-- General (No Specific Batch) --</option>
          ${batches.map(b => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('')}
        </select>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Subject / Issue Title *</label>
        <div class="admin-input-wrap">
          <input type="text" id="t-subject" required placeholder="e.g. Video #2 buffering or PDF not opening">
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Problem Description *</label>
        <textarea id="t-desc" class="admin-textarea" rows="3" required placeholder="Describe what the student reported..."></textarea>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-action-btn" id="btn-submit-ticket">Log Ticket</button>
      </div>
    </form>
  `);
}

async function submitNewTicket(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-ticket');
  if (btn) btn.disabled = true;

  const payload = {
    student_name: document.getElementById('t-name').value.trim(),
    student_contact: document.getElementById('t-contact').value.trim(),
    category: document.getElementById('t-cat').value,
    priority: document.getElementById('t-priority').value,
    batch_id: document.getElementById('t-batch').value || null,
    subject: document.getElementById('t-subject').value.trim(),
    description: document.getElementById('t-desc').value.trim()
  };

  try {
    const resp = await fetch(`${API_BASE}/admin/tickets`, {
      method: 'POST',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (!resp.ok) throw new Error('Failed to create ticket');
    showToast('✨ Ticket logged successfully!');
    closeAdminModal();
    await renderAdminSupportTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

function openUpdateTicketModal(ticketId, currentStatus, currentNote, currentPriority) {
  openAdminModal(`
    <h3 class="modal-title">✏️ Update Problem Status</h3>
    <p class="modal-subtitle">Change ticket progress and record admin resolution note.</p>
    
    <form onsubmit="submitUpdateTicket(event, '${ticketId}')" class="admin-login-form">
      <div class="admin-form-row">
        <div class="admin-form-group">
          <label class="admin-label">Status</label>
          <select id="u-status" class="admin-select">
            <option value="PENDING" ${currentStatus === 'PENDING' ? 'selected' : ''}>PENDING</option>
            <option value="IN_PROGRESS" ${currentStatus === 'IN_PROGRESS' ? 'selected' : ''}>IN PROGRESS</option>
            <option value="RESOLVED" ${currentStatus === 'RESOLVED' ? 'selected' : ''}>RESOLVED</option>
            <option value="CLOSED" ${currentStatus === 'CLOSED' ? 'selected' : ''}>CLOSED</option>
          </select>
        </div>

        <div class="admin-form-group">
          <label class="admin-label">Priority</label>
          <select id="u-priority" class="admin-select">
            <option value="LOW" ${currentPriority === 'LOW' ? 'selected' : ''}>LOW</option>
            <option value="MEDIUM" ${currentPriority === 'MEDIUM' ? 'selected' : ''}>MEDIUM</option>
            <option value="HIGH" ${currentPriority === 'HIGH' ? 'selected' : ''}>HIGH</option>
            <option value="URGENT" ${currentPriority === 'URGENT' ? 'selected' : ''}>URGENT</option>
          </select>
        </div>
      </div>

      <div class="admin-form-group">
        <label class="admin-label">Admin Resolution Note</label>
        <textarea id="u-note" class="admin-textarea" rows="3" placeholder="e.g. Added student to batch manually / Re-uploaded PDF">${escapeHtml(currentNote)}</textarea>
      </div>

      <div class="modal-btn-row">
        <button type="button" class="admin-secondary-btn" onclick="closeAdminModal()">Cancel</button>
        <button type="submit" class="admin-action-btn" id="btn-submit-u-ticket">Save Update</button>
      </div>
    </form>
  `);
}

async function submitUpdateTicket(e, ticketId) {
  e.preventDefault();
  const btn = document.getElementById('btn-submit-u-ticket');
  if (btn) btn.disabled = true;

  const payload = {
    status: document.getElementById('u-status').value,
    priority: document.getElementById('u-priority').value,
    admin_note: document.getElementById('u-note').value.trim()
  };

  try {
    const resp = await fetch(`${API_BASE}/admin/tickets/${ticketId}`, {
      method: 'PUT',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify(payload)
    });
    if (!resp.ok) throw new Error('Update failed');
    showToast('✨ Ticket updated successfully!');
    closeAdminModal();
    await renderAdminSupportTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}

async function deleteTicket(ticketId) {
  if (!confirm('Delete this support ticket?')) return;
  try {
    const resp = await fetch(`${API_BASE}/admin/tickets/${ticketId}`, {
      method: 'DELETE',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Delete failed');
    showToast('Ticket deleted');
    await renderAdminSupportTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

// ==============================================================================
// TAB 5: YOUTUBE MULTI-ACCOUNT & LIMITS
// ==============================================================================

async function renderAdminYouTubeTab(container) {
  container.innerHTML = `<div class="spinner-center"><div class="spinner"></div></div>`;

  const resp = await fetch(`${API_BASE}/admin/youtube`, { headers: getAdminAuthHeaders() });
  if (!resp.ok) throw new Error('Failed to fetch YouTube diagnostics');
  const data = await resp.json();

  const channel = data.channel || {};
  const history = data.platform_upload_history || {};
  const queues = data.queues || {};
  const accountsMgr = data.accounts_manager || {};

  container.innerHTML = `
    <!-- Top Action Toolbar -->
    <div class="admin-toolbar-row">
      <div>
        <h3 class="admin-section-title">YouTube Multi-Account Publishing Engine</h3>
        <p class="admin-section-desc">Automatic daily limit failover, channel health diagnostics, quota checkpoints, and token rotation.</p>
      </div>
      <div class="admin-btn-group">
        <button class="admin-action-btn" onclick="forceRefreshYouTube()">🔄 Force Refresh API</button>
        <button class="admin-warning-btn" onclick="pauseYouTubeUploads()">⏸️ Pause Uploads</button>
        <button class="admin-success-btn" onclick="resumeYouTubeUploads('all')">▶️ Resume Checkpoints</button>
      </div>
    </div>

    <!-- Active Channel Banner -->
    <div class="admin-yt-channel-card">
      <div class="yt-channel-header">
        <div class="yt-channel-icon">📺</div>
        <div class="yt-channel-info">
          <div class="yt-channel-title-row">
            <h4 class="yt-channel-name">${escapeHtml(channel.channel_title || 'TECHNICAL CLASSES')}</h4>
            <span class="admin-badge-status ${channel.status === 'ACTIVE' ? 'active' : 'warning'}">${channel.status || 'ACTIVE'}</span>
          </div>
          <p class="yt-channel-id">Channel ID: <code>${escapeHtml(channel.channel_id || 'UCa7N5SJFL5m2CLqJlby49Mw')}</code></p>
        </div>
      </div>

      <div class="yt-metrics-strip">
        <div class="yt-metric-item">
          <span class="yt-m-label">Uploads (Last 24h)</span>
          <span class="yt-m-val">${history.uploads_last_24h || 0}</span>
        </div>
        <div class="yt-metric-item">
          <span class="yt-m-label">Uploads (Last 7 Days)</span>
          <span class="yt-m-val">${history.uploads_last_7d || 0}</span>
        </div>
        <div class="yt-metric-item">
          <span class="yt-m-label">Total Uploaded Videos</span>
          <span class="yt-m-val">${history.total_recorded_uploads || 0}</span>
        </div>
        <div class="yt-metric-item">
          <span class="yt-m-label">Estimated Remaining Allowance</span>
          <span class="yt-m-val" style="color: #10b981;">~${channel.estimated_remaining_allowance || 20} videos today</span>
        </div>
      </div>
    </div>

    <!-- Multi-Account Failover Pool Cards -->
    <h4 class="admin-subsection-title">Configured YouTube Accounts (${accountsMgr.total_accounts || 1})</h4>
    <div class="admin-accounts-grid">
      ${(accountsMgr.accounts || []).map(acc => `
        <div class="admin-account-card ${acc.status === 'ACTIVE' ? 'card-active' : ''}">
          <div class="account-card-top">
            <div>
              <span class="account-priority-badge">Priority #${acc.priority}</span>
              <h5 class="account-channel-title">${escapeHtml(acc.channel_title || acc.account_name)}</h5>
            </div>
            <span class="account-status-badge ${acc.status === 'ACTIVE' ? 'st-active' : 'st-limit'}">${acc.status}</span>
          </div>
          <div class="account-card-details">
            <p><span>Channel ID:</span> <code>${acc.channel_id || 'N/A'}</code></p>
            <p><span>Uploads Today:</span> <strong>${acc.uploads_today} / ${acc.daily_limit}</strong></p>
            <p><span>Failover Auto-Switch:</span> <strong style="color: #10b981;">Enabled</strong></p>
          </div>
        </div>
      `).join('')}
    </div>

    <!-- Blocked Checkpoints Queue -->
    <div class="admin-checkpoints-card">
      <div class="chk-header">
        <h4 class="admin-subsection-title" style="margin: 0;">Preserved Video Checkpoints (${queues.blocked_checkpoints_count || 0})</h4>
        <span class="chk-policy-badge">🛡️ Zero-Data Loss Checkpoint Engine</span>
      </div>
      <p class="admin-section-desc">When YouTube's daily upload limit is hit, watermarked videos are preserved on disk and queued to auto-resume as soon as the limit resets.</p>
      
      ${(queues.blocked_checkpoints && queues.blocked_checkpoints.length > 0) ? `
        <div class="admin-table-wrap">
          <table class="admin-table">
            <thead>
              <tr>
                <th>Batch</th>
                <th>Lecture</th>
                <th>Reason</th>
                <th>File Size</th>
                <th>Preserved At</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${queues.blocked_checkpoints.map(cp => `
                <tr>
                  <td>${escapeHtml(cp.batch_name)}</td>
                  <td><strong>#${cp.lecture_index}</strong> ${escapeHtml(cp.lecture_title)}</td>
                  <td><span class="badge-tag tag-warning">${escapeHtml(cp.reason)}</span></td>
                  <td>${cp.size_mb} MB</td>
                  <td>${cp.created_at ? new Date(cp.created_at).toLocaleString() : 'Recent'}</td>
                  <td>
                    <button class="admin-sm-btn" onclick="resumeYouTubeUploads('${cp.batch_id}')">▶️ Resume</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : `
        <div class="admin-empty-box">
          <span style="font-size: 1.5rem;">🟢</span>
          <p>All queues clear! No paused or limit-blocked checkpoints.</p>
        </div>
      `}
    </div>
  `;
}

async function forceRefreshYouTube() {
  try {
    showToast('🔄 Refreshing YouTube Channel Status...');
    const resp = await fetch(`${API_BASE}/admin/youtube/refresh`, {
      method: 'POST',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Refresh failed');
    showToast('✨ YouTube Channel Status Refreshed!');
    await renderAdminYouTubeTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

async function pauseYouTubeUploads() {
  try {
    const resp = await fetch(`${API_BASE}/admin/youtube/pause`, {
      method: 'POST',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Pause failed');
    showToast('⏸️ Active video uploads paused');
    await renderAdminYouTubeTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

async function resumeYouTubeUploads(batchId) {
  try {
    showToast('▶️ Signalling video upload controllers to resume...');
    const resp = await fetch(`${API_BASE}/admin/youtube/resume/${batchId}`, {
      method: 'POST',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Resume failed');
    const data = await resp.json();
    showToast(`✨ ${data.message || 'Resumed successfully!'}`);
    await renderAdminYouTubeTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

// ==============================================================================
// TAB 6: LIVE JOBS & RETRY QUEUE
// ==============================================================================

async function renderAdminJobsTab(container) {
  container.innerHTML = `<div class="spinner-center"><div class="spinner"></div></div>`;

  const resp = await fetch(`${API_BASE}/admin/jobs`, { headers: getAdminAuthHeaders() });
  if (!resp.ok) throw new Error('Failed to fetch jobs');
  const jobs = await resp.json();

  container.innerHTML = `
    <div class="admin-toolbar-row">
      <div>
        <h3 class="admin-section-title">Background Ingestion & Processing Jobs</h3>
        <p class="admin-section-desc">Live status of video downloads, watermarking pipelines, YouTube uploads, and B2 storage synchronization.</p>
      </div>
      <button class="admin-action-btn" onclick="renderAdminJobsTab(document.getElementById('admin-tab-content'))">🔄 Refresh List</button>
    </div>

    ${jobs.length > 0 ? `
      <div class="admin-table-wrap">
        <table class="admin-table">
          <thead>
            <tr>
              <th>Job ID</th>
              <th>Provider</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Current Step</th>
              <th>Created</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${jobs.map(j => `
              <tr>
                <td><code>${j.id.slice(0, 8)}...</code></td>
                <td><span class="badge-tag tag-cyan">${escapeHtml(j.provider || 'generic')}</span></td>
                <td>
                  <span class="admin-badge-status ${j.status === 'PUBLISHED' ? 'active' : (j.status === 'FAILED' ? 'danger' : 'warning')}">
                    ${j.status}
                  </span>
                </td>
                <td style="min-width: 140px;">
                  <div class="admin-progress-bar-wrap">
                    <div class="admin-progress-bar-fill" style="width: ${Math.round(j.progress_percent || 0)}%;"></div>
                  </div>
                  <span style="font-size: 0.72rem; color: var(--text-muted);">${Math.round(j.progress_percent || 0)}%</span>
                </td>
                <td style="font-size: 0.8rem; color: var(--text-muted); max-width: 220px;">
                  ${escapeHtml(j.error_message || j.current_step || '—')}
                </td>
                <td style="font-size: 0.78rem; color: var(--text-muted);">
                  ${j.created_at ? new Date(j.created_at).toLocaleTimeString() : '—'}
                </td>
                <td>
                  ${j.status === 'FAILED' ? `
                    <button class="admin-sm-btn" onclick="retryAdminJob('${j.id}')">🔄 Retry</button>
                  ` : '—'}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    ` : `
      <div class="admin-empty-box">
        <span style="font-size: 1.5rem;">☕</span>
        <p>No active or queued jobs at this time.</p>
      </div>
    `}
  `;
}

async function retryAdminJob(jobId) {
  try {
    const resp = await fetch(`${API_BASE}/admin/jobs/${jobId}/retry`, {
      method: 'POST',
      headers: getAdminAuthHeaders()
    });
    if (!resp.ok) throw new Error('Retry failed');
    showToast(`✨ Job ${jobId.slice(0, 8)} queued for retry!`);
    await renderAdminJobsTab(document.getElementById('admin-tab-content'));
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
  }
}

// ==============================================================================
// TAB 7: WATERMARK & DRM CONFIGURATION
// ==============================================================================

async function renderAdminWatermarkTab(container) {
  container.innerHTML = `<div class="spinner-center"><div class="spinner"></div></div>`;

  const resp = await fetch(`${API_BASE}/admin/watermark`, { headers: getAdminAuthHeaders() });
  if (!resp.ok) throw new Error('Failed to fetch watermark profile');
  const prof = await resp.json();

  container.innerHTML = `
    <div class="admin-toolbar-row">
      <div>
        <h3 class="admin-section-title">Video Watermarking & DRM Branding</h3>
        <p class="admin-section-desc">Configure the dynamic moving anti-piracy watermark rendered into all processed video lectures.</p>
      </div>
    </div>

    <div class="admin-watermark-card">
      <form onsubmit="saveAdminWatermark(event)" class="admin-wm-form">
        <div class="admin-form-group">
          <label class="admin-label">Watermark Text</label>
          <div class="admin-input-wrap">
            <input type="text" id="wm-text-input" required value="${escapeHtml(prof.text || 'COURSE WALLAH')}">
          </div>
          <span class="admin-field-hint">Appears moving across student video screens to deter piracy.</span>
        </div>

        <div class="admin-form-row">
          <div class="admin-form-group">
            <label class="admin-label">Opacity Level (0.10 – 1.00)</label>
            <div class="admin-input-wrap">
              <input type="number" step="0.05" min="0.1" max="1.0" id="wm-opacity-input" value="${prof.opacity || 0.45}">
            </div>
          </div>

          <div class="admin-form-group">
            <label class="admin-label">Movement Interval (Seconds)</label>
            <div class="admin-input-wrap">
              <input type="number" min="1" max="60" id="wm-interval-input" value="${prof.movement_interval || 7}">
            </div>
          </div>

          <div class="admin-form-group">
            <label class="admin-label">Encoding Quality (CRF: 18-28)</label>
            <div class="admin-input-wrap">
              <input type="number" min="18" max="28" id="wm-crf-input" value="${prof.crf || 23}">
            </div>
          </div>
        </div>

        <div class="admin-form-group">
          <label class="admin-label" style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
            <input type="checkbox" id="wm-enabled-input" ${prof.enabled !== false ? 'checked' : ''}>
            <span>Enable Anti-Piracy Watermark on all video encodes</span>
          </label>
        </div>

        <button type="submit" class="admin-action-btn" id="btn-save-wm" style="padding: 12px 24px;">
          💾 Save Watermark Settings
        </button>
      </form>
    </div>
  `;
}

async function saveAdminWatermark(e) {
  e.preventDefault();
  const btn = document.getElementById('btn-save-wm');
  if (btn) btn.disabled = true;

  const text = document.getElementById('wm-text-input').value.trim();
  const opacity = parseFloat(document.getElementById('wm-opacity-input').value);
  const interval = parseInt(document.getElementById('wm-interval-input').value, 10);
  const crf = parseInt(document.getElementById('wm-crf-input').value, 10);
  const enabled = document.getElementById('wm-enabled-input').checked;

  try {
    const resp = await fetch(`${API_BASE}/admin/watermark`, {
      method: 'PUT',
      headers: getAdminAuthHeaders(),
      body: JSON.stringify({
        text: text,
        opacity: opacity,
        movement_interval: interval,
        crf: crf,
        enabled: enabled
      })
    });

    if (!resp.ok) throw new Error('Failed to update watermark profile');
    showToast('✨ Watermark settings saved successfully!');
    if (btn) btn.disabled = false;
  } catch (err) {
    showToast(`⚠️ Error: ${err.message}`);
    if (btn) btn.disabled = false;
  }
}


